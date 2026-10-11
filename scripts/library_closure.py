"""Which library modules a campaign actually runs, found by reading the code, not the imports it declares.

A receipt that hashes only its driver script cannot notice that the library computing the
result changed underneath it. Listing the library by hand is no better: the list is right
on the day it is written and silently wrong afterwards, which is the failure mode a receipt
exists to prevent.

So the list is derived. `modules_reached` parses the driver with `ast`, collects every
module of the package it imports, and follows those modules' own imports until nothing new
appears. Importing any submodule executes the package `__init__`, so `__init__` and
everything it pulls in are part of the closure whether the driver names them or not; that
is why the closure is usually most of the package rather than the two files the driver
mentions.

Static, so it never runs the code it is describing, and it sees a figure or report script
that no test exercises exactly as well as one that is tested.
"""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "mic_50_90"
PACKAGE_DIR = ROOT / "src" / PACKAGE


def _imported_modules(source: str, *, inside_package: bool, package_context=None) -> set[str]:
    """Conservative static imports, including nested and literal dynamic imports."""
    found: set[str] = set()
    context = package_context or (PACKAGE if inside_package else None)
    def add(name):
        if name == PACKAGE:
            found.add('__init__')
        elif name.startswith(PACKAGE+'.'):
            found.add('__init__')
            parts = name[len(PACKAGE)+1:].split('.')
            found.update('.'.join(parts[:i]) for i in range(1,len(parts)+1))
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if context is None:continue
                name = resolve_name('.'*node.level+(node.module or ''), context)
            else:
                name = node.module or ''
            add(name)
            for alias in node.names:
                if alias.name != '*':add(name+'.'+alias.name)
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0],ast.Constant):
            callee = node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
            name = node.args[0].value
            if callee in {'import_module','__import__'} and isinstance(name,str):
                if name.startswith('.'):
                    if context is None:continue
                    name = resolve_name(name,context)
                add(name)
    return found


def modules_reached(*relative_scripts: str) -> list[str]:
    """Repository-relative paths of every package module these scripts can reach."""
    pending: set[str] = set()
    for relative in relative_scripts:
        path = ROOT / relative
        if path.is_file():
            pending |= _imported_modules(path.read_text(encoding="utf-8"), inside_package=False)

    seen: set[str] = set()
    reached: set[str] = set()
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        relative = Path(*module.split('.'))
        path = PACKAGE_DIR / relative.with_suffix('.py')
        if not path.is_file():
            path = PACKAGE_DIR / relative / '__init__.py'
        if path.is_file():
            reached.add(path.relative_to(ROOT).as_posix())
            package = path.parent.relative_to(PACKAGE_DIR).parts
            context = '.'.join((PACKAGE,*package))
            pending |= _imported_modules(path.read_text(encoding="utf-8"), inside_package=True,package_context=context)
    return sorted(reached)


if __name__ == "__main__":
    import sys

    for relative in sys.argv[1:]:
        reached = modules_reached(relative)
        print(f"{relative}: {len(reached)} modules")
        for entry in reached:
            print(f"  {entry}")
