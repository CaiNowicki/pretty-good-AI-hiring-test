"""Command-line entry point for Phase 1."""

from __future__ import annotations

import argparse
import os
import random
import shutil
import sys
from dataclasses import replace
from pathlib import Path

from voicebot.config import DEFAULT_ENV_FILE, load_settings
from voicebot.config import Settings
from voicebot.constants import ALLOWED_DESTINATION, DEFAULT_SCENARIO_ID
from voicebot.scenario import build_shuffled_call_set, load_scenario, ordered_scenario_stems
from voicebot.scenario_call_pipeline import (
    DEFAULT_COMPLETION_TIMEOUT_SECONDS,
    prepare_scenario_call_batch,
    run_scenario_call_batch,
    run_scenario_call,
)
from voicebot.twilio_adapter import build_call_plan


TOP_LEVEL_COMMANDS = {
    "run",
    "dry-run",
    "call",
    "scenario-call-pipeline",
    "smoke",
    "appointment",
    "appointments",
    "appointment-scheduling",
    "scheduling",
    "medication",
    "medication-refill",
    "refill",
    "informational",
    "information-gathering",
    "info",
    "orthopedic",
    "orthopedic-edge-cases",
    "edge-cases",
    "difficult",
    "difficult-call-handling",
    "list-scenarios",
    "server",
}

CATEGORY_COMMANDS = {
    "smoke": (("t",), "smoke scenarios"),
    "appointment": (("a",), "appointment scheduling scenarios"),
    "medication": (("m",), "medication refill scenarios"),
    "informational": (("i",), "informational scenarios"),
    "difficult": (("e", "d"), "difficult and edge-case scenarios"),
}

CATEGORY_ALIASES = {
    "appointment": ["appointments", "appointment-scheduling", "scheduling"],
    "medication": ["medication-refill", "refill"],
    "informational": ["information-gathering", "info"],
    "difficult": [
        "difficult-call-handling",
        "orthopedic",
        "orthopedic-edge-cases",
        "edge-cases",
    ],
}


def _add_common_call_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO_ID)
    parser.add_argument("--to", default=ALLOWED_DESTINATION)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--public-base-url", help="Override PUBLIC_BASE_URL for this run")


def _load_settings(args: argparse.Namespace) -> Settings:
    settings = load_settings(args.env_file)
    public_base_url = getattr(args, "public_base_url", None)
    if public_base_url:
        return replace(settings, public_base_url=public_base_url.strip())
    return settings


def _scenario_stems_for_prefixes(prefixes: tuple[str, ...]) -> list[str]:
    normalized = tuple(prefix.casefold() for prefix in prefixes)
    return [
        scenario_id
        for scenario_id in ordered_scenario_stems()
        if scenario_id[:1].casefold() in normalized
    ]


def _choose_random_scenario(scenario_ids: list[str], seed: str | None) -> list[str]:
    if not scenario_ids:
        return []
    rng = random.Random(seed)
    return [rng.choice(scenario_ids)]


def dry_run(args: argparse.Namespace) -> int:
    settings = _load_settings(args)
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


def _confirm_user_understands(args: argparse.Namespace, *, live: bool) -> bool:
    if args.yes:
        return True

    scenario = load_scenario(args.scenario)
    print("")
    print(f"Scenario: {args.scenario} ({scenario.id})")
    print(f"Patient profile: {scenario.patient_profile}")
    print(f"Goal: {' '.join(scenario.goal.split())}")
    print("")
    if live:
        print(f"LIVE CALL: this will call {args.to} through Twilio.")
        print("The local webhook server and PUBLIC_BASE_URL tunnel must already be reachable.")
        expected = "LIVE"
    else:
        print("DEV DRY RUN: this will not call Twilio or the assessment number.")
        print("It will only prepare the call directory, scenario copy, metadata, and event log.")
        expected = "DEV"

    answer = input(f"Type {expected} to continue: ").strip()
    if answer != expected:
        print("Aborted.")
        return False
    return True


def _confirm_pipeline_user_understands(
    args: argparse.Namespace,
    scenario_ids: list[str],
    *,
    live: bool,
    inter_call_delay_seconds: float = 0.0,
    wait_for_completion: bool = True,
) -> bool:
    if args.yes:
        return True
    if not live:
        return True

    print("")
    if len(scenario_ids) == 1:
        print(f"LIVE SCENARIO: this will start 1 Twilio call to {args.to}.")
    else:
        print(f"LIVE BATCH: this will start {len(scenario_ids)} Twilio calls to {args.to}.")
    print("The local webhook server and PUBLIC_BASE_URL tunnel must already be reachable.")
    if wait_for_completion and len(scenario_ids) > 1:
        print("Each next call will start after the previous call completes.")
    if inter_call_delay_seconds > 0:
        print(f"Calls will also wait {inter_call_delay_seconds:g} seconds after completion.")
    print("Calls are requested one scenario at a time in the order shown below:")
    for scenario_id in scenario_ids:
        scenario = load_scenario(scenario_id)
        print(f"  {scenario_id}: {scenario.id} [{scenario.patient_profile}]")
    print("")
    answer = input("Type LIVE ALL to continue: ").strip()
    if answer != "LIVE ALL":
        print("Aborted.")
        return False
    return True


def _confirm_single_live_user_understands(
    args: argparse.Namespace,
    scenario_id: str,
) -> bool:
    if args.yes:
        return True

    scenario = load_scenario(scenario_id)
    print("")
    print(f"Scenario: {scenario_id} ({scenario.id})")
    print(f"Patient profile: {scenario.patient_profile}")
    print(f"Goal: {' '.join(scenario.goal.split())}")
    print("")
    print(f"LIVE CALL: this will call {args.to} through Twilio.")
    print("The local webhook server and PUBLIC_BASE_URL tunnel must already be reachable.")

    answer = input("Type LIVE to continue: ").strip()
    if answer != "LIVE":
        print("Aborted.")
        return False
    return True


def _path_is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _cleanup_dev_artifacts_if_requested(args: argparse.Namespace, call_dir: Path) -> None:
    if args.yes:
        print("Dev artifact cleanup skipped because --yes was used.")
        return
    if not _path_is_inside(call_dir, Path(args.calls_root)):
        print(f"Dev artifact cleanup skipped; unexpected artifact path: {call_dir}")
        return

    print("")
    print("DEV CLEANUP: this demo created scaffold files only.")
    print(f"Delete this dev artifact directory now? {call_dir}")
    answer = input("Type DELETE to remove it, or press Enter to keep it: ").strip()
    if answer != "DELETE":
        print(f"Keeping dev artifacts: {call_dir}")
        return

    shutil.rmtree(call_dir)
    print(f"Deleted dev artifacts: {call_dir}")


def run_one_scenario(args: argparse.Namespace) -> int:
    live = args.mode != "dev"
    if not _confirm_user_understands(args, live=live):
        return 1

    settings = _load_settings(args)
    prepared = run_scenario_call(
        settings,
        args.scenario,
        live=live,
        to_number=args.to,
        calls_root=Path(args.calls_root),
    )
    if live:
        print(f"Started live scenario call: {prepared.call_id}")
        print(f"Artifacts: {prepared.call_dir}")
        print("Recording and transcript artifacts will be written by the webhook callbacks.")
    else:
        print(f"Prepared dev scenario call without placing a live call: {prepared.call_id}")
        print(f"Artifacts: {prepared.call_dir}")
        _cleanup_dev_artifacts_if_requested(args, prepared.call_dir)
    return 0


def call(args: argparse.Namespace) -> int:
    args.mode = ""
    args.calls_root = "artifacts/calls"
    return run_one_scenario(args)


def prepare_pipeline(args: argparse.Namespace) -> int:
    settings = _load_settings(args)
    category_prefixes = getattr(args, "category_prefixes", None)
    category_mode = category_prefixes is not None
    single_category_call = category_mode and not args.batch
    if category_mode:
        scenario_ids = _scenario_stems_for_prefixes(category_prefixes)
        if args.limit is not None:
            scenario_ids = scenario_ids[: args.limit]
        if single_category_call:
            scenario_ids = _choose_random_scenario(scenario_ids, args.shuffle_seed)
        scenario_ids = build_shuffled_call_set(scenario_ids, seed=args.shuffle_seed)
    elif args.all_scenarios:
        scenario_ids = ordered_scenario_stems()
        if args.limit is not None:
            scenario_ids = scenario_ids[: args.limit]
        if args.shuffle_fungible:
            scenario_ids = build_shuffled_call_set(scenario_ids, seed=args.shuffle_seed)
    else:
        scenario_ids = args.scenario or [DEFAULT_SCENARIO_ID]
        if args.limit is not None:
            scenario_ids = scenario_ids[: args.limit]
        if args.shuffle_fungible:
            scenario_ids = build_shuffled_call_set(scenario_ids, seed=args.shuffle_seed)

    wait_for_completion = args.live and not args.no_wait_for_completion
    inter_call_delay_seconds = args.inter_call_delay_seconds

    if single_category_call:
        if not scenario_ids:
            print("No scenarios matched this category.")
            return 1
        scenario_id = scenario_ids[0]
        if args.live and not _confirm_single_live_user_understands(args, scenario_id):
            return 1

        prepared_call = run_scenario_call(
            settings,
            scenario_id,
            live=args.live,
            to_number=args.to,
            calls_root=Path(args.calls_root),
        )
        if args.live:
            print(f"Started live scenario call: {prepared_call.call_id}")
            print(f"Artifacts: {prepared_call.call_dir}")
            print(f"Runtime scenario: {prepared_call.runtime_scenario_id}")
            print("Recording and transcript artifacts will be written by the webhook callbacks.")
        else:
            print("Prepared scenario call artifact without placing a live call:")
            print(
                f"  {prepared_call.call_id}: "
                f"{prepared_call.call_dir} [{prepared_call.runtime_scenario_id}]"
            )
        return 0

    if not _confirm_pipeline_user_understands(
        args,
        scenario_ids,
        live=args.live,
        inter_call_delay_seconds=inter_call_delay_seconds,
        wait_for_completion=wait_for_completion,
    ):
        return 1

    if args.live:
        prepared = run_scenario_call_batch(
            settings,
            scenario_ids,
            live=True,
            to_number=args.to,
            calls_root=Path(args.calls_root),
            inter_call_delay_seconds=inter_call_delay_seconds,
            wait_for_completion=wait_for_completion,
            completion_timeout_seconds=args.completion_timeout_seconds,
        )
        print("Started scenario-call pipeline through Twilio:")
    else:
        prepared = prepare_scenario_call_batch(
            settings,
            scenario_ids,
            to_number=args.to,
            calls_root=Path(args.calls_root),
        )
        print("Prepared scenario-call pipeline artifacts without placing calls:")
    for item in prepared:
        print(f"  {item.call_id}: {item.call_dir} [{item.runtime_scenario_id}]")
    return 0


def _add_batch_args(
    parser: argparse.ArgumentParser,
    *,
    include_selection: bool,
    include_batch_modifier: bool = False,
) -> None:
    if include_selection:
        parser.add_argument("--scenario", action="append")
        parser.add_argument("--all-scenarios", action="store_true")
    if include_batch_modifier:
        parser.add_argument(
            "--batch",
            action="store_true",
            help="Run one shuffled call for every scenario in this category",
        )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--shuffle-fungible",
        action="store_true",
        help="Pair fungible scenario templates with shuffled patient profiles",
    )
    parser.add_argument(
        "--shuffle-seed",
        help="Seed for reproducible fungible scenario/patient shuffles",
    )
    parser.add_argument("--live", action="store_true", help="Originate Twilio calls")
    parser.add_argument(
        "--inter-call-delay-seconds",
        type=float,
        default=0.0,
        help="Extra pause after a live call completes before requesting the next call",
    )
    parser.add_argument(
        "--completion-timeout-seconds",
        type=float,
        default=DEFAULT_COMPLETION_TIMEOUT_SECONDS,
        help="Maximum time to wait for a live call completion event before aborting the batch",
    )
    parser.add_argument(
        "--no-wait-for-completion",
        action="store_true",
        help="Request live batch calls without waiting for each previous call to complete",
    )
    parser.add_argument("--to", default=ALLOWED_DESTINATION)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--public-base-url", help="Override PUBLIC_BASE_URL for this run")
    parser.add_argument("--calls-root", default="artifacts/calls")
    parser.add_argument("--yes", action="store_true", help="Skip the typed confirmation")


def list_scenarios(args: argparse.Namespace) -> int:
    for scenario_id in ordered_scenario_stems():
        scenario = load_scenario(scenario_id)
        print(f"{scenario_id}: {scenario.id} [{scenario.patient_profile}]")
    return 0


def _normalize_argv(argv: list[str] | None) -> list[str]:
    normalized = list(sys.argv[1:] if argv is None else argv)
    if normalized and normalized[0] not in TOP_LEVEL_COMMANDS and not normalized[0].startswith("-"):
        return ["run", *normalized]
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pretty Good AI voice-bot harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Run one scenario; add positional 'dev' to prepare artifacts without calling",
    )
    run_parser.add_argument("scenario", help="Scenario file stem, such as a01_specific_time")
    run_parser.add_argument(
        "mode",
        nargs="?",
        choices=["dev"],
        help="Use 'dev' to avoid placing a live call",
    )
    run_parser.add_argument("--to", default=ALLOWED_DESTINATION)
    run_parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    run_parser.add_argument("--public-base-url", help="Override PUBLIC_BASE_URL for this run")
    run_parser.add_argument("--calls-root", default="artifacts/calls")
    run_parser.add_argument("--yes", action="store_true", help="Skip the typed confirmation")
    run_parser.set_defaults(func=run_one_scenario)

    dry_run_parser = subparsers.add_parser("dry-run", help="Print the safe call plan")
    _add_common_call_args(dry_run_parser)
    dry_run_parser.set_defaults(func=dry_run)

    call_parser = subparsers.add_parser("call", help="Place one allowlisted call")
    _add_common_call_args(call_parser)
    call_parser.add_argument("--yes", action="store_true", help="Skip the typed confirmation")
    call_parser.set_defaults(func=call)

    pipeline_parser = subparsers.add_parser(
        "scenario-call-pipeline",
        help="Prepare grouped call artifacts without placing calls",
    )
    _add_batch_args(pipeline_parser, include_selection=True)
    pipeline_parser.set_defaults(func=prepare_pipeline)

    for command, (prefixes, description) in CATEGORY_COMMANDS.items():
        category_parser = subparsers.add_parser(
            command,
            aliases=CATEGORY_ALIASES.get(command, []),
            help=f"Run a shuffled {description[:-1] if description.endswith('s') else description}",
        )
        _add_batch_args(
            category_parser,
            include_selection=False,
            include_batch_modifier=True,
        )
        category_parser.set_defaults(func=prepare_pipeline, category_prefixes=prefixes)

    list_parser = subparsers.add_parser("list-scenarios", help="List runnable scenario codes")
    list_parser.set_defaults(func=list_scenarios)

    server_parser = subparsers.add_parser("server", help="Run the Twilio webhook server")
    server_parser.add_argument("--host", default="0.0.0.0")
    server_parser.add_argument("--port", default=8000, type=int)
    server_parser.add_argument("--public-base-url", help="Override PUBLIC_BASE_URL for this server")

    def run_server(server_args: argparse.Namespace) -> int:
        try:
            import uvicorn
        except ImportError as exc:
            raise RuntimeError("Install project dependencies before running the server.") from exc
        if server_args.public_base_url:
            os.environ["PUBLIC_BASE_URL"] = server_args.public_base_url.strip()
        uvicorn.run("voicebot.server:app", host=server_args.host, port=server_args.port, reload=False)
        return 0

    server_parser.set_defaults(func=run_server)

    args = parser.parse_args(_normalize_argv(argv))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
