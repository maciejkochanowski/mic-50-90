"""Generate or check the public option reference against the delivered parser."""
import argparse
from pathlib import Path

from mic_50_90.cli import build_parser


def reference():
    root = build_parser()
    groups = [("mic-50-90", root)]
    for action in root._actions:
        if isinstance(action, argparse._SubParsersAction):
            groups.extend(("mic-50-90 " + name, parser) for name, parser in action.choices.items())
    lines = ["# MIC-50-90 1.0.0: command and option reference", "",
             "Generated from the installed command parser. GUI_GUIDE.md and PUBLIC_FUNCTIONS.md map tasks to Windows and CLI.",
             "Values shown as None mean the option is omitted, not a numerical zero.", ""]
    for name, parser in groups:
        lines += ["## " + name, "", "| Argument | Meaning | Default or requirement |", "|---|---|---|"]
        exclusive = {}
        for group in parser._mutually_exclusive_groups:
            for action in group._group_actions:
                exclusive[action] = [other.option_strings[0] for other in group._group_actions if other is not action]
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction) or action.help == argparse.SUPPRESS:
                continue
            label = ", ".join(action.option_strings) or action.dest
            explanation = str(action.help or "").replace("|", r"\|").replace("\n", " ")
            if action.choices is not None:
                explanation += "; choices: " + ", ".join(map(str, action.choices))
            if exclusive.get(action):
                explanation += "; cannot be combined with " + ", ".join(f"`{name}`" for name in exclusive[action])
            default = ("—" if action.default == argparse.SUPPRESS else
                       "required" if action.required else str(action.default))
            lines.append(f"| `{label}` | {explanation} | {default} |")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "docs/CLI_REFERENCE.md")
    args = parser.parse_args()
    text = reference()
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != text:
            raise SystemExit("Command reference differs from the current public parser: " + str(args.output))
        print("Command reference matches the current public parser.")
    else:
        args.output.write_text(text, encoding="utf-8")
