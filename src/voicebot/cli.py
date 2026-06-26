"""Command-line entry point for the Pretty Good AI call harness."""

from __future__ import annotations

import argparse
import os
import random
import sys
from dataclasses import replace
from pathlib import Path

from voicebot.artifacts import DEFAULT_CALLS_ROOT
from voicebot.config import DEFAULT_ENV_FILE, Settings, load_settings
from voicebot.constants import ALLOWED_DESTINATION
from voicebot.scenario import build_shuffled_call_set, load_scenario, ordered_scenario_stems
from voicebot.scenario_call_pipeline import (
    DEFAULT_COMPLETION_TIMEOUT_SECONDS,
    run_scenario_call,
    run_scenario_call_batch,
)


SCENARIO_GROUPS = {
    "smoke": (("t",), "smoke"),
    "appointment-scheduling": (("a",), "appointment scheduling"),
    "medication-refill": (("m",), "medication refill"),
    "information-gathering": (("i",), "information gathering"),
    "orthopedic-edge-cases": (("e",), "orthopedic edge cases"),
    "difficult-call-handling": (("d",), "difficult call handling"),
}

GROUP_ALIASES = {
    "appointment": "appointment-scheduling",
    "appointments": "appointment-scheduling",
    "scheduling": "appointment-scheduling",
    "medication": "medication-refill",
    "refill": "medication-refill",
    "informational": "information-gathering",
    "info": "information-gathering",
    "orthopedic": "orthopedic-edge-cases",
    "edge-cases": "orthopedic-edge-cases",
    "difficult": "difficult-call-handling",
}

CONFIG_TARGETS = {"config", "server", "help"}
ALL_SCENARIOS_TARGET = "all-scenarios"


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


def _canonical_group_name(target: str) -> str | None:
    normalized = target.casefold()
    if normalized in SCENARIO_GROUPS:
        return normalized
    return GROUP_ALIASES.get(normalized)


def _print_scenario_line(scenario_id: str) -> None:
    scenario = load_scenario(scenario_id)
    print(f"  {scenario_id}: {scenario.id} [{scenario.patient_profile}]")


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


def _confirm_batch_live_user_understands(
    args: argparse.Namespace,
    scenario_ids: list[str],
    *,
    inter_call_delay_seconds: float = 0.0,
    wait_for_completion: bool = True,
) -> bool:
    if args.yes:
        return True

    print("")
    print(f"LIVE BATCH: this will start {len(scenario_ids)} Twilio calls to {args.to}.")
    print("The local webhook server and PUBLIC_BASE_URL tunnel must already be reachable.")
    if wait_for_completion and len(scenario_ids) > 1:
        print("Each next call will start after the previous call completes.")
    if inter_call_delay_seconds > 0:
        print(f"Calls will also wait {inter_call_delay_seconds:g} seconds after completion.")
    print("Calls are requested one scenario at a time in the order shown below:")
    for scenario_id in scenario_ids:
        _print_scenario_line(scenario_id)
    print("")

    answer = input("Type LIVE ALL to continue: ").strip()
    if answer != "LIVE ALL":
        print("Aborted.")
        return False
    return True


def _selected_scenarios_for_target(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> tuple[list[str], bool]:
    """Return selected scenario ids and whether they should run as a batch."""

    target = args.target
    if target == ALL_SCENARIOS_TARGET:
        scenario_ids = ordered_scenario_stems()
        if args.limit is not None:
            scenario_ids = scenario_ids[: args.limit]
        return scenario_ids, True

    group_name = _canonical_group_name(target)
    if group_name is not None:
        prefixes, _description = SCENARIO_GROUPS[group_name]
        scenario_ids = _scenario_stems_for_prefixes(prefixes)
        if args.limit is not None:
            scenario_ids = scenario_ids[: args.limit]
        if not scenario_ids:
            parser.error(f"No scenarios matched group '{target}'.")
        if args.batch:
            return build_shuffled_call_set(scenario_ids, seed=args.shuffle_seed), True
        selected = _choose_random_scenario(scenario_ids, args.shuffle_seed)
        return build_shuffled_call_set(selected, seed=args.shuffle_seed), False

    if args.batch:
        parser.error("--batch is only valid for scenario groups and all-scenarios.")

    try:
        load_scenario(target)
    except Exception as exc:
        parser.error(str(exc))
    return [target], False


def run_call_target(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if not args.live:
        parser.error("Call targets require --live. Use 'pgai-call config' for setup checks.")

    scenario_ids, is_batch = _selected_scenarios_for_target(parser, args)
    settings = _load_settings(args)
    calls_root = Path(args.calls_root)

    if is_batch:
        wait_for_completion = not args.no_wait_for_completion
        inter_call_delay_seconds = args.inter_call_delay_seconds
        if not _confirm_batch_live_user_understands(
            args,
            scenario_ids,
            inter_call_delay_seconds=inter_call_delay_seconds,
            wait_for_completion=wait_for_completion,
        ):
            return 1

        def print_batch_progress(event: str, prepared_call, index: int, total: int) -> None:
            ordinal = f"{index + 1}/{total}"
            if event == "started":
                print(
                    f"Started {ordinal}: {prepared_call.call_id} "
                    f"[{prepared_call.runtime_scenario_id}]"
                )
                print(f"  Artifacts: {prepared_call.call_dir}")
            elif event == "waiting":
                print(
                    "Waiting for completion before starting the next call: "
                    f"{prepared_call.call_id}"
                )
            elif event == "completed":
                print(f"Completion observed: {prepared_call.call_id}")
            elif event == "timeout":
                print(f"Completion wait timed out: {prepared_call.call_id}")
            elif event == "delay":
                print(f"Waiting {inter_call_delay_seconds:g} seconds before the next call.")

        try:
            prepared = run_scenario_call_batch(
                settings,
                scenario_ids,
                live=True,
                to_number=args.to,
                calls_root=calls_root,
                inter_call_delay_seconds=inter_call_delay_seconds,
                wait_for_completion=wait_for_completion,
                completion_timeout_seconds=args.completion_timeout_seconds,
                progress_callback=print_batch_progress,
                continue_on_completion_timeout=args.continue_on_completion_timeout,
            )
        except TimeoutError as exc:
            print("")
            print(f"Scenario batch stopped while waiting for completion: {exc}")
            print(
                "Use --completion-timeout-seconds to change the wait, "
                "--continue-on-completion-timeout to keep going after a timeout, "
                "or --no-wait-for-completion to request every call without blocking."
            )
            return 1

        print("Started live scenario batch through Twilio:")
        for item in prepared:
            print(f"  {item.call_id}: {item.call_dir} [{item.runtime_scenario_id}]")
        return 0

    scenario_id = scenario_ids[0]
    if not _confirm_single_live_user_understands(args, scenario_id):
        return 1

    prepared_call = run_scenario_call(
        settings,
        scenario_id,
        live=True,
        to_number=args.to,
        calls_root=calls_root,
    )
    print(f"Started live scenario call: {prepared_call.call_id}")
    print(f"Artifacts: {prepared_call.call_dir}")
    print(f"Runtime scenario: {prepared_call.runtime_scenario_id}")
    print("Recording and transcript artifacts will be written by the webhook callbacks.")
    return 0


def config_check(args: argparse.Namespace) -> int:
    settings = _load_settings(args)
    missing = settings.missing_twilio_call_values()
    if not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")

    print("Configuration check:")
    print(f"  Env file: {Path(args.env_file)}")
    print(f"  Destination: {ALLOWED_DESTINATION}")
    print(f"  Public base URL: {settings.public_base_url or '(missing)'}")
    print(f"  Realtime model: {settings.realtime_model}")
    print(f"  Transcription model: {settings.transcription_model}")
    print("")

    if missing:
        print("Missing values:")
        for name in missing:
            print(f"  {name}")
    else:
        print("Ready for live calls.")

    print("")
    print("Scenario groups:")
    for group_name, (prefixes, description) in SCENARIO_GROUPS.items():
        count = len(_scenario_stems_for_prefixes(prefixes))
        print(f"  {group_name}: {count} {description} scenario(s)")
    print(f"  {ALL_SCENARIOS_TARGET}: {len(ordered_scenario_stems())} total scenario(s)")

    if args.list_scenarios:
        print("")
        print("Scenarios:")
        for scenario_id in ordered_scenario_stems():
            _print_scenario_line(scenario_id)

    return 0 if not missing else 1


def run_server(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install project dependencies before running the server.") from exc
    if args.public_base_url:
        os.environ["PUBLIC_BASE_URL"] = args.public_base_url.strip()
    uvicorn.run("voicebot.server:app", host=args.host, port=args.port, reload=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    examples = "\n".join(
        [
            "examples:",
            "  pgai-call a01_specific_time --live",
            "  pgai-call appointment-scheduling --live",
            "  pgai-call appointment-scheduling --batch --live",
            "  pgai-call all-scenarios --live",
            "  pgai-call server --port 8000",
            "  pgai-call config --list-scenarios",
            "  pgai-call help",
        ]
    )
    parser = argparse.ArgumentParser(
        prog="pgai-call",
        description="Pretty Good AI scenario caller",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "target",
        nargs="?",
        help=(
            "Scenario name, scenario group, all-scenarios, server, config, or help"
        ),
    )
    parser.add_argument("--live", action="store_true", help="Originate Twilio call(s)")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="For a scenario group, run every scenario in that group",
    )
    parser.add_argument(
        "--shuffle-seed",
        help="Seed for reproducible group scenario and patient-profile selection",
    )
    parser.add_argument("--limit", type=int, help="Limit selected scenarios for a batch")
    parser.add_argument(
        "--inter-call-delay-seconds",
        type=float,
        default=0.0,
        help="Extra pause after a live batch call completes before requesting the next call",
    )
    parser.add_argument(
        "--completion-timeout-seconds",
        type=float,
        default=DEFAULT_COMPLETION_TIMEOUT_SECONDS,
        help="Maximum time to wait for a live call completion event before aborting a batch",
    )
    parser.add_argument(
        "--no-wait-for-completion",
        action="store_true",
        help="Request live batch calls without waiting for each previous call to complete",
    )
    parser.add_argument(
        "--continue-on-completion-timeout",
        action="store_true",
        help="Continue a live batch after a call completion wait times out",
    )
    parser.add_argument("--to", default=ALLOWED_DESTINATION)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--public-base-url", help="Override PUBLIC_BASE_URL for this run")
    parser.add_argument("--calls-root", default=str(DEFAULT_CALLS_ROOT))
    parser.add_argument("--yes", action="store_true", help="Skip the typed confirmation")
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="With config, print every runnable scenario",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Server bind host")
    parser.add_argument("--port", default=8000, type=int, help="Server bind port")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    normalized = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(normalized)

    if args.target is None or args.target == "help":
        parser.print_help()
        return 0
    if args.target == "config":
        return config_check(args)
    if args.target == "server":
        return run_server(args)
    if args.target in CONFIG_TARGETS:
        parser.error(f"Unknown config target '{args.target}'.")

    return run_call_target(parser, args)


if __name__ == "__main__":
    raise SystemExit(main())
