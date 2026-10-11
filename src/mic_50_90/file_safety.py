"""Reject destructive path aliases before a command writes any output."""
from pathlib import Path


def check_output_paths(inputs, outputs):
    """Check resolved paths and existing hard links; allow replacing old outputs."""
    sources = [Path(value) for value in inputs if value is not None]
    destinations = [Path(value) for value in outputs if value is not None]
    for index, destination in enumerate(destinations):
        for other in sources + destinations[:index]:
            same = destination.resolve() == other.resolve()
            if not same and destination.exists() and other.exists():
                same = destination.samefile(other)
            if same:
                raise ValueError(f"Output path {destination} collides with input or another output {other}; choose a separate output path")
