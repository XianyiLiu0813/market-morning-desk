#!/usr/bin/env python3
"""Market Morning Desk - CLI entry point (Section 36).

Usage:
    python main.py morning [--mock] [--date YYYY-MM-DD] [--no-email]
    python main.py collect [--date YYYY-MM-DD]
    python main.py analyze [--date YYYY-MM-DD]
    python main.py render  [--date YYYY-MM-DD]
    python main.py send    [--date YYYY-MM-DD]

`morning` runs the full pipeline end-to-end (the primary command).
`collect` / `analyze` / `render` / `send` are provided for staged manual
debugging; in this V1 they delegate to the same pipeline function with
different side-effect flags, since the pipeline is fast enough in
MOCK_MODE to always run in full - see README for notes on decomposing
further if you introduce genuinely expensive/paid API calls you want to
cache between stages.
"""
from __future__ import annotations

import argparse
import os
import sys

from src.utils.time import parse_run_date


def _apply_mock_flag(mock: bool) -> None:
    if mock:
        os.environ["MOCK_MODE"] = "true"


def cmd_morning(args: argparse.Namespace) -> int:
    _apply_mock_flag(args.mock)
    from src.pipeline import run_morning_pipeline
    from src.utils.config import get_settings

    settings = get_settings(force_reload=True)
    for w in settings.validate():
        print(f"[config warning] {w}")

    run_date = parse_run_date(args.date)
    result = run_morning_pipeline(run_date=run_date, settings=settings, send_email=not args.no_email)

    print(f"Run ID: {result['run_id']}")
    print(f"Report date: {run_date}")
    print(f"Providers used: {result['providers_used']}")
    print(f"Email status: {result['email_status']}")
    if result["email_path"]:
        print(f"Email/report HTML saved to: {result['email_path']}")
    print(f"Data quality degraded_mode: {result['report'].data_quality.degraded_mode}")
    return 0


def cmd_staged(args: argparse.Namespace) -> int:
    """collect/analyze/render/send all currently run the full pipeline in
    MOCK_MODE-friendly fashion; kept as distinct subcommands per Section 36
    so the CLI surface matches the spec even though V1 doesn't yet cache
    intermediate stages to disk between separate invocations."""
    print(
        f"NOTE: '{args.command}' currently runs the full pipeline (collection through "
        "rendering) in one pass; use 'morning --no-email' to generate a report without "
        "sending, or see README for how to extend staged caching."
    )
    args.mock = args.mock
    args.no_email = args.command != "send"
    return cmd_morning(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="Market Morning Desk CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--mock", action="store_true", help="Force MOCK_MODE=true for this run")
        p.add_argument("--date", type=str, default=None, help="Run date YYYY-MM-DD (default: today, Asia/Singapore)")

    p_morning = sub.add_parser("morning", help="Run the full morning pipeline and send the email")
    add_common(p_morning)
    p_morning.add_argument("--no-email", action="store_true", help="Generate the report but do not send email")
    p_morning.set_defaults(func=cmd_morning)

    for name, help_text in [
        ("collect", "Run data collection (market+news+macro) as part of a full pass"),
        ("analyze", "Run analysis stages as part of a full pass"),
        ("render", "Render the HTML report as part of a full pass"),
        ("send", "Run the full pipeline and send the email"),
    ]:
        p = sub.add_parser(name, help=help_text)
        add_common(p)
        p.set_defaults(func=cmd_staged, command=name)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
