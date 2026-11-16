"""Write an sdist manifest from the completed archive, including generated metadata.

An archive cannot contain its own final digest. Its final SHA-256 belongs in an
external delivery receipt; this manifest covers each regular member except itself.
The wheel keeps its standard wheel RECORD and is not changed by this hook.
"""
from __future__ import annotations

import gzip
import hashlib
from io import BytesIO
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def finalize(self, version, build_data, artifact_path):
        if self.target_name != "sdist":
            return
        add_sdist_manifest(Path(artifact_path))


def add_sdist_manifest(archive_path: Path) -> None:
    """Atomically replace a built sdist by the same payload plus its manifest."""
    records = []
    selected = []
    roots = set()
    seen = set()
    with tarfile.open(archive_path, "r:gz") as source:
        for member in source.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or path.as_posix() != member.name:
                raise ValueError(f"Unsafe sdist member: {member.name}")
            if not path.parts or (len(path.parts) < 2 and not member.isdir()):
                raise ValueError(f"Missing sdist root: {member.name}")
            roots.add(path.parts[0])
            if member.name in seen:
                raise ValueError(f"Duplicate sdist member: {member.name}")
            seen.add(member.name)
            if not member.isfile() and not member.isdir():
                raise ValueError(f"Unsupported linked or special sdist member: {member.name}")
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if relative in {"MANIFEST.sha256", "PACKAGE_MANIFEST.sha256"}:
                continue
            selected.append(member)
            if member.isfile():
                digest = hashlib.sha256()
                stream = source.extractfile(member)
                if stream is None:
                    raise ValueError(f"Cannot read sdist member: {member.name}")
                with stream:
                    for block in iter(lambda: stream.read(1 << 20), b""):
                        digest.update(block)
                records.append((relative, digest.hexdigest()))
    if len(roots) != 1 or not records:
        raise ValueError("An sdist must contain one nonempty package root")
    root = roots.pop()
    manifest = "".join(f"{digest}  {name}\n" for name, digest in sorted(records)).encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".mic-sdist-", suffix=".tar.gz", dir=archive_path.parent,
                                         delete=False) as destination:
            temporary = Path(destination.name)
            with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as output:
                    with tarfile.open(archive_path, "r:gz") as source:
                        for member in selected:
                            stream = source.extractfile(member) if member.isfile() else None
                            try:
                                output.addfile(member, stream)
                            finally:
                                if stream is not None:
                                    stream.close()
                    info = tarfile.TarInfo(f"{root}/MANIFEST.sha256")
                    info.size = len(manifest)
                    info.mode = 0o644
                    info.mtime = selected[0].mtime
                    output.addfile(info, BytesIO(manifest))
        os.replace(temporary, archive_path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
