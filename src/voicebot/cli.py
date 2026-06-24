"""Command-line entry point for Phase 1."""

from __future__ import annotations

import argparse
from pathlib import Path

from voicebot.artifacts import next_call_dir, utc_now_iso, write_json
from voicebot.config import load_settings
from voicebot.constants import ALLOWED_DESTINATION, DEFAULT_SCENARIO_ID
from voicebot.twilio_adapter import build_call_plan, create_outbound_call


def _add_common_call_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO_ID)
    parser.add_argument("--to", default=ALLOWED_DESTINATION)
    parser.add_argument("--env-file", default=".env")


def dry_run(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    plan = build_call_plan(settings, args.to, args.scenario)
    print("Dry run call plan:")
    for key, value in plan.items():
        print(f"  {key}: {value}")
    missing = settings.missing_twilio_call_values()
    if missing:
        print("")
        print("Missing configuration before a real call:")
        for name in missing:
            print(f"  {name}")
    return 0


def call(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    call_dir = next_call_dir()
    result = create_outbound_call(settings, args.to, args.scenario)
    write_json(
        call_dir / "metadata.json",
        {
            "created_at": utc_now_iso(),
            "scenario_id": args.scenario,
            "twilio_call": result,
        },
    )
    print(f"Started call {result['sid']} with status {result['status']}")
    print(f"Artifacts: {call_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pretty Good AI voice-bot harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run_parser = subparsers.add_parser("dry-run", help="Print the safe call plan")
    _add_common_call_args(dry_run_parser)
    dry_run_parser.set_defaults(func=dry_run)

    call_parser = subparsers.add_parser("call", help="Place one allowlisted call")
    _add_common_call_args(call_parser)
    call_parser.set_defaults(func=call)

    server_parser = subparsers.add_parser("server", help="Run the Twilio webhook server")
    server_parser.add_argument("--host", default="0.0.0.0")
    server_parser.add_argument("--port", default=8000, type=int)

    def run_server(server_args: argparse.Namespace) -> int:
        try:
            import uvicorn
        except ImportError as exc:
            raise RuntimeError("Install project dependencies before running the server.") from exc
        uvicorn.run("voicebot.server:app", host=server_args.host, port=server_args.port, reload=False)
        return 0

    server_parser.set_defaults(func=run_server)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
