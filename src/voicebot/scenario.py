"""Compatibility shim for scenario loading and prompt builders."""

from voicebot.scenario_loader import (  # noqa: F401
    SCENARIO_ROOT,
    SCENARIO_RUN_PREFIXES,
    META_BEHAVIOR_ALLOW_PHRASES,
    DEFAULT_EMERGENCY_STOP_PHRASES,
    CallLimits,
    Scenario,
    ScenarioNotFoundError,
    load_scenario,
    scenario_path_for_id,
    ordered_scenario_stems,
)
from voicebot.scenario_prompts import (  # noqa: F401
    scenario_allows_meta_behavior,
    build_scheduling_turn_guidance,
    build_patient_system_prompt,
    build_realtime_bootstrap,
)
