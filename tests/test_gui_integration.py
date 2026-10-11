"""The desktop entry point is available without changing existing commands."""
from mic_50_90.cli import build_parser


def test_gui_parser_uses_local_defaults():
    args = build_parser().parse_args(["gui"])
    assert args.port == 0
    assert args.no_browser is False
    assert args.output_root is None
    assert args.ready_file is None
    assert callable(args.handler)


def test_gui_parser_accepts_noninteractive_readiness_file(tmp_path):
    path = tmp_path / "ready.json"
    args = build_parser().parse_args(["gui", "--no-browser", "--ready-file", str(path)])
    assert args.no_browser is True
    assert args.ready_file == str(path)


def test_existing_distribution_default_is_unchanged():
    args = build_parser().parse_args(["distribution", "input.json", "--output-dir", "out"])
    assert args.population_method == "bonferroni"
