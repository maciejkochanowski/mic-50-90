"""Static pagination for batch reports, independent of the scientific renderer.

The callback renders the complete existing result sections.  This module only
partitions records, builds an index and supplies navigation and denominators.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import html
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Protocol
from urllib.parse import quote
from .typography import html_with_typography


@dataclass(frozen=True)
class BatchPageContext:
    """Navigation and denominators for one consecutive slice of the batch."""

    page_number: int
    page_count: int
    record_offset: int
    total_records: int
    total_accepted: int
    page_records: int
    page_accepted: int
    index_href: str
    previous_href: str | None
    next_href: str | None

    def cohort_anchor(self, local_index: int) -> str:
        """Return an ordinal anchor; cohort labels never become paths or IDs."""
        if not 0 <= local_index < self.page_records:
            raise IndexError("The cohort index is outside this report page")
        return f"cohort-{self.record_offset + local_index + 1:06d}"

    def navigation_html(self) -> str:
        links = [f'<a href="{html.escape(self.index_href, quote=True)}">All cohorts (index)</a>']
        if self.previous_href is not None:
            links.append(f'<a rel="prev" href="{html.escape(self.previous_href, quote=True)}">Previous page</a>')
        if self.next_href is not None:
            links.append(f'<a rel="next" href="{html.escape(self.next_href, quote=True)}">Next page</a>')
        return '<nav aria-label="Report pages">' + " | ".join(links) + "</nav>"

    def summary_html(self) -> str:
        return (
            '<section class="card" aria-label="Batch and page denominators">'
            f"<p>Entire batch: numerical analyses {self.total_accepted}/{self.total_records}; "
            f"refusals {self.total_records-self.total_accepted}/{self.total_records}. "
            "Refusals remain in the batch denominator.</p>"
            f"<p>This page: numerical analyses {self.page_accepted}/{self.page_records}; "
            f"refusals {self.page_records-self.page_accepted}/{self.page_records}. "
            f"Page {self.page_number} of {self.page_count}; "
            f"cohorts {self.record_offset+1} to {self.record_offset+self.page_records} "
            f"of {self.total_records}, in input order. "
            "These are cohort counts; each result states its own isolate denominator.</p></section>"
        )


class DetailRenderer(Protocol):
    def __call__(
        self,
        records: Sequence[Mapping[str, Any]],
        configuration: Mapping[str, Any],
        destination: Path,
        pagination: BatchPageContext | None,
    ) -> Path: ...


def validate_page_size(page_size: int) -> int:
    """Reject accidental truth values and rounding; zero selects one file."""
    if type(page_size) is not int or page_size < 0:
        raise ValueError("page_size must be a nonnegative integer; use 0 for a single file")
    return page_size


def _filename(page_number: int) -> str:
    return f"page-{page_number:06d}.html"


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n"


def _index_document(manifest: dict[str, Any], configuration: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> str:
    total = manifest["total_records"]
    accepted = manifest["total_accepted"]
    version = html.escape(str(configuration["version"]))
    page_rows = []
    for page in manifest["pages"]:
        href = html.escape(page["href"], quote=True)
        page_rows.append(
            f'<tr><td><a href="{href}">Page {page["number"]}</a></td>'
            f'<td>{page["record_start"]} to {page["record_end"]}</td>'
            f'<td>{page["accepted"]}/{page["records"]}</td>'
            f'<td>{page["refused"]}/{page["records"]}</td></tr>'
        )
    cohort_rows = []
    for record, entry in zip(records, manifest["cohorts"]):
        label = html.escape(str(entry["cohort_id"]))
        status = html.escape(str(entry["status"]))
        reason = "" if entry["status"] == "ok" else html.escape(str(record.get("reason", "")))
        href = html.escape(entry["href"], quote=True)
        cohort_rows.append(
            f'<tr><td>{entry["ordinal"]}</td><td><a href="{href}">{label}</a></td>'
            f'<td>{status}</td><td>{reason}</td></tr>'
        )
    # The manifest is inert data; the shared renderer adds trusted controls. Escaping prevents a
    # cohort label such as </script> from terminating that data element.
    embedded = _json_text(manifest).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    manifest_href = html.escape(manifest["manifest_href"], quote=True)
    checksums_href = html.escape(manifest["checksums_href"], quote=True)
    first_href = html.escape(manifest["pages"][0]["href"], quote=True)
    return html_with_typography(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>MIC-50-90 batch report index</title><style>'
        'body{font-family:Arial,sans-serif;margin:0;background:#f5f7fa;color:#172033;line-height:1.5}'
        'main{max-width:1050px;margin:auto;padding:32px 24px 60px}'
        'table{border-collapse:collapse;width:100%;background:white;margin:16px 0}'
        'th,td{text-align:left;border-bottom:1px solid #dce3ec;padding:9px;overflow-wrap:anywhere}'
        'th{background:#eaf0f6}a{color:#184d88}.table-scroll{overflow-x:auto}'
        '@media(max-width:760px){main{padding:18px 12px}}'
        '</style></head><body><main>'
        f'<h1>MIC-50-90 {version}</h1><h2>Batch report index</h2>'
        f'<p>Entire batch: numerical analyses {accepted}/{total}; refusals {total-accepted}/{total}. '
        'Refusals remain in the batch denominator. These are cohort counts; '
        'each detailed result states its own isolate denominator.</p>'
        f'<p>All {total} cohorts are listed below in input order. '
        f'Detailed results occupy {len(manifest["pages"])} pages, with up to '
        f'{manifest["page_size"]} cohorts per page. Every numerical result and refusal is retained. '
        'Page denominators describe only that page.</p>'
        f'<p><a href="{first_href}">Open the first detail page</a></p>'
        '<h2>Detail pages</h2><div class="table-scroll"><table><thead><tr>'
        '<th>Page</th><th>Cohort ordinals</th><th>Numerical analyses / page cohorts</th>'
        '<th>Refusals / page cohorts</th></tr></thead><tbody>'
        + "".join(page_rows)
        + '</tbody></table></div><h2>All cohorts and status</h2>'
        '<div class="table-scroll"><table><thead><tr><th>Ordinal</th><th>Cohort</th>'
        '<th>Status</th><th>Refusal reason, if any</th></tr></thead><tbody>'
        + "".join(cohort_rows)
        + '</tbody></table></div><h2>Files and reproducibility</h2>'
        '<p>Open this index and its accompanying detail folder together. All links are local; '
        'reading the report requires neither JavaScript nor a network connection. Optional export controls run locally. '
        'configuration.json, results.csv and results.json retain the batch settings and numerical outputs.</p>'
        f'<p><a href="{manifest_href}">Pagination manifest (JSON)</a> records every cohort, status, '
        f'page and detail-file SHA-256. <a href="{checksums_href}">Output checksums</a> '
        'also cover this index and the manifest.</p>'
        f'<script type="application/json" id="report-pagination-manifest">{embedded}</script>'
        '</main></body></html>'
    )


def render_paginated_batch_html(
    records: Sequence[Mapping[str, Any]],
    configuration: Mapping[str, Any],
    destination: str | Path,
    *,
    page_size: int = 50,
    render_page: DetailRenderer,
) -> Path:
    """Write a static index and complete detail pages, or use the legacy renderer.

    ``render_page`` receives ``None`` for its context when pagination is not
    needed. For paginated output it must use ``cohort_anchor(i)`` on each article,
    ``summary_html()`` for denominators and ``navigation_html()`` for navigation.
    Old detail folders are deliberately retained: a render never deletes or
    overwrites another render's files. The index is replaced only after success.
    """
    validate_page_size(page_size)
    path = Path(destination)
    if path.is_symlink():
        raise ValueError("The report destination must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    if page_size == 0 or len(records) <= page_size:
        return render_page(records, configuration, path, None)

    total = len(records)
    accepted = sum(record["status"] == "ok" for record in records)
    page_count = (total + page_size - 1) // page_size
    # A newly created directory cannot contain stale pages, symlinks or files
    # belonging to the user. Names never depend on untrusted cohort identifiers.
    detail_dir = Path(tempfile.mkdtemp(prefix="report-pages-", dir=path.parent))
    directory_href = quote(detail_dir.name, safe="")
    manifest: dict[str, Any] = {
        "schema": "mic-50-90.report-pagination.v1",
        "index": path.name,
        "page_size": page_size,
        "total_records": total,
        "total_accepted": accepted,
        "total_refused": total - accepted,
        "manifest_href": f"{directory_href}/manifest.json",
        "checksums_href": f"{directory_href}/checksums.sha256",
        "pages": [],
        "cohorts": [],
    }
    for number, offset in enumerate(range(0, total, page_size), start=1):
        batch = records[offset:offset + page_size]
        page_accepted = sum(record["status"] == "ok" for record in batch)
        context = BatchPageContext(
            page_number=number,
            page_count=page_count,
            record_offset=offset,
            total_records=total,
            total_accepted=accepted,
            page_records=len(batch),
            page_accepted=page_accepted,
            index_href="../" + quote(path.name, safe=""),
            previous_href=_filename(number - 1) if number > 1 else None,
            next_href=_filename(number + 1) if number < page_count else None,
        )
        detail_path = detail_dir / _filename(number)
        render_page(batch, configuration, detail_path, context)
        content = detail_path.read_bytes()
        href = f"{directory_href}/{detail_path.name}"
        manifest["pages"].append({
            "number": number,
            "href": href,
            "record_start": offset + 1,
            "record_end": offset + len(batch),
            "records": len(batch),
            "accepted": page_accepted,
            "refused": len(batch) - page_accepted,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        })
        for index, record in enumerate(batch):
            manifest["cohorts"].append({
                "ordinal": offset + index + 1,
                "cohort_id": record["cohort_id"],
                "status": record["status"],
                "href": href + "#" + context.cohort_anchor(index),
            })

    manifest_content = _json_text(manifest).encode("utf-8")
    (detail_dir / "manifest.json").write_bytes(manifest_content)
    index_content = _index_document(manifest, configuration, records).encode("utf-8")
    checksums = [f'{page["sha256"]}  {_filename(page["number"])}' for page in manifest["pages"]]
    checksums += [
        f'{hashlib.sha256(manifest_content).hexdigest()}  manifest.json',
        f'{hashlib.sha256(index_content).hexdigest()}  ../{path.name}',
    ]
    (detail_dir / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8", newline="\n")
    handle, staging_name = tempfile.mkstemp(prefix=".report-index-", suffix=".html", dir=path.parent)
    staging_path = Path(staging_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(index_content)
        os.replace(staging_path, path)
    finally:
        # Only the exact temporary file created above is eligible for deletion.
        staging_path.unlink(missing_ok=True)
    return path
