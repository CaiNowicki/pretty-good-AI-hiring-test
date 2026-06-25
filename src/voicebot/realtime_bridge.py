"""Bridge Twilio Media Streams to the OpenAI Realtime API."""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import websockets
from starlette.websockets import WebSocket

from voicebot.artifacts import append_jsonl, scenario_type_for_id, utc_now_iso
from voicebot.config import Settings
from voicebot.conversation_classifier import (
    AGENT_SERVICE_OPENING_PHRASES,
    INTAKE_BEFORE_GOAL_PHRASES,
    NON_CONVERSATIONAL_PHRASES,
    build_agent_turn_key,
    evaluate_scenario_completion,
    transcript_asks_about_assumed_patient,
    transcript_asks_about_meta_behavior,
    transcript_is_confusing_or_out_of_turn,
    transcript_is_ignorable_before_opening,
    transcript_is_intake_before_goal,
    transcript_is_service_opening,
    transcript_needs_more_agent_context,
    transcript_requests_emergency_stop,
    _looks_like_garbled_transcript,
)
from voicebot.openai_builders import (
    build_input_audio_append,
    build_openai_realtime_url,
    build_response_cancel,
    build_session_update as build_openai_session_update,
)
from voicebot.patient_response_builders import (
    REPEATED_INFO_TEMPLATES,
    build_assumed_patient_identity_guidance,
    build_confusion_reply,
    build_confusion_response,
    build_completion_closing_response,
    build_exact_fact_answer,
    build_fact_confirmation_answer,
    build_meta_guardrail_answer,
    build_opening_response,
    build_pre_goal_response,
    build_repeated_info_answer,
    build_turn_response,
    completion_closing_options,
    repeated_info_probability,
    requested_info_key,
    should_point_out_repeated_info,
)
from voicebot.scenario_loader import Scenario
from voicebot.scenario_prompts import build_patient_system_prompt
from voicebot.twilio_builders import (
    build_twilio_clear,
    build_twilio_mark,
    build_twilio_media,
)


__all__ = [
    "AGENT_SERVICE_OPENING_PHRASES",
    "BridgeState",
    "EMERGENCY_STOP_DTMF_DIGITS",
    "INTAKE_BEFORE_GOAL_PHRASES",
    "NON_CONVERSATIONAL_PHRASES",
    "RealtimeBridge",
    "_looks_like_garbled_transcript",
    "build_agent_turn_key",
    "build_assumed_patient_identity_guidance",
    "build_confusion_reply",
    "build_confusion_response",
    "build_completion_closing_response",
    "build_exact_fact_answer",
    "build_fact_confirmation_answer",
    "build_input_audio_append",
    "build_meta_guardrail_answer",
    "build_opening_response",
    "build_openai_realtime_url",
    "build_pre_goal_response",
    "build_repeated_info_answer",
    "build_response_cancel",
    "build_session_update",
    "build_turn_response",
    "build_twilio_clear",
    "build_twilio_mark",
    "build_twilio_media",
    "completion_closing_options",
    "evaluate_scenario_completion",
    "repeated_info_probability",
    "requested_info_key",
    "should_point_out_repeated_info",
    "transcript_asks_about_assumed_patient",
    "transcript_asks_about_meta_behavior",
    "transcript_is_confusing_or_out_of_turn",
    "transcript_is_ignorable_before_opening",
    "transcript_is_intake_before_goal",
    "transcript_is_service_opening",
    "transcript_needs_more_agent_context",
    "transcript_requests_emergency_stop",
]


DEFAULT_RESPONSE_DELAY_SECONDS = 0.0
POST_VAD_SILENCE_CONFIRMATION_SECONDS = 0.05
POST_RESPONSE_COOLDOWN_SECONDS = 0.25
LIMIT_WATCH_INTERVAL_SECONDS = 1.0
MIN_COMPLETION_CHECK_SECONDS = 45.0
POST_FINAL_GOODBYE_SILENCE_SECONDS = 5.0
INTERRUPTION_RESPONSE_DELAY_SECONDS = 0.25
EMERGENCY_STOP_DTMF_DIGITS = {"9"}
MAX_STORED_CONVERSATION_TURNS = 24


def build_session_update(settings: Settings, scenario: Scenario) -> dict[str, Any]:
    system_prompt = build_patient_system_prompt(scenario)
    return build_openai_session_update(settings, scenario, system_prompt)


@dataclass
class BridgeState:
    stream_sid: str
    scenario: Scenario
    events_path: Path
    call_id: str = ""
    call_type: str = ""


class RealtimeBridge:
    def __init__(self, settings: Settings, state: BridgeState):
        self.settings = settings
        self.state = state
        self._openai_ws: Any | None = None
        self._openai_to_twilio_task: asyncio.Task[None] | None = None
        self._pending_response_task: asyncio.Task[None] | None = None
        self._limit_watch_task: asyncio.Task[None] | None = None
        self._final_goodbye_watch_task: asyncio.Task[None] | None = None
        self._pending_transcript_event: dict[str, Any] | None = None
        self._agent_speech_in_progress = False
        self._last_agent_speech_stopped_at = 0.0
        self._call_started_at = 0.0
        self._last_conversation_activity_at = 0.0
        self._goal_introduced = False
        self._bot_audio_in_progress = False
        self._patient_response_in_progress = False
        self._cooldown_until = 0.0
        self._stop_requested = False
        self._agent_turn_count = 0
        self._counted_agent_turns: set[str] = set()
        self._responded_agent_turns: set[str] = set()
        self._provided_info_counts: dict[str, int] = {}
        self._last_repeated_info_template_index: dict[str, int] = {}
        self._conversation_turns: list[dict[str, str]] = []
        self._completion_closing_requested = False
        self._pending_polite_end_mark_name = ""
        self._pending_polite_end_details: dict[str, Any] = {}
        self._agent_spoke_after_final_close = False
        self._call_boundary_end_logged = False
        self._random = random.Random()

    async def start(self, twilio_ws: WebSocket) -> None:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for the realtime bridge.")

        self._openai_ws = await websockets.connect(
            build_openai_realtime_url(self.settings),
            additional_headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "OpenAI-Safety-Identifier": "pretty-good-ai-hiring-test",
            },
        )
        await self._send_openai(build_session_update(self.settings, self.state.scenario))
        loop_time = asyncio.get_running_loop().time()
        self._call_started_at = loop_time
        self._last_conversation_activity_at = loop_time
        self._openai_to_twilio_task = asyncio.create_task(self._pipe_openai_to_twilio(twilio_ws))
        self._limit_watch_task = asyncio.create_task(self._watch_deterministic_limits(twilio_ws))
        self._log_call_boundary("start", {"stream_sid": self.state.stream_sid})
        self._log(
            {
                "event": "realtime.started",
                "scenario_id": self.state.scenario.id,
                "stream_sid": self.state.stream_sid,
                "limits": self.state.scenario.limits.to_dict(),
            }
        )

    async def forward_twilio_media(self, payload: str) -> None:
        if self._stop_requested or self._openai_ws is None or not payload:
            return
        await self._send_openai(build_input_audio_append(payload))

    async def request_emergency_stop(self, twilio_ws: WebSocket, reason: str) -> None:
        await self._terminate_call(twilio_ws, "emergency_stop", {"reason": reason})

    async def handle_twilio_mark(self, twilio_ws: WebSocket, mark_name: str) -> bool:
        if not self._pending_polite_end_mark_name:
            return False
        if mark_name != self._pending_polite_end_mark_name:
            return False

        await self._terminate_call(
            twilio_ws,
            "scenario_goal_met",
            self._pending_polite_end_details,
            clear_twilio=False,
        )
        return True

    async def close(self) -> None:
        if self._limit_watch_task is not None:
            task = self._limit_watch_task
            self._limit_watch_task = None
            if task is not asyncio.current_task():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if self._final_goodbye_watch_task is not None:
            task = self._final_goodbye_watch_task
            self._final_goodbye_watch_task = None
            if task is not asyncio.current_task():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if self._openai_to_twilio_task is not None:
            self._openai_to_twilio_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._openai_to_twilio_task
        if self._pending_response_task is not None:
            self._pending_response_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pending_response_task
        if self._openai_ws is not None:
            await self._openai_ws.close()
            self._openai_ws = None
        self._log_call_boundary_end("websocket_closed", {"stream_sid": self.state.stream_sid})
        self._log({"event": "realtime.closed", "stream_sid": self.state.stream_sid})

    async def _send_openai(self, event: dict[str, Any]) -> None:
        if self._openai_ws is None:
            raise RuntimeError("Realtime WebSocket is not connected.")
        await self._openai_ws.send(json.dumps(event))

    async def _pipe_openai_to_twilio(self, twilio_ws: WebSocket) -> None:
        from fastapi import WebSocketDisconnect

        assert self._openai_ws is not None
        async for raw_message in self._openai_ws:
            if self._stop_requested:
                break
            try:
                event = json.loads(raw_message)
                event_type = event.get("type", "unknown")

                if event_type == "response.output_audio.delta":
                    self._mark_conversation_activity()
                    self._bot_audio_in_progress = True
                    await twilio_ws.send_json(build_twilio_media(self.state.stream_sid, event["delta"]))
                    continue

                if event_type == "response.output_audio.done":
                    self._bot_audio_in_progress = False
                    self._finish_patient_response_cooldown()
                    mark_name = f"audio-{event.get('response_id', 'done')}"
                    await twilio_ws.send_json(
                        build_twilio_mark(
                            self.state.stream_sid,
                            mark_name,
                        )
                    )
                    if self._completion_closing_requested and not self._pending_polite_end_mark_name:
                        self._pending_polite_end_mark_name = mark_name
                        self._log(
                            {
                                "event": "call.polite_end_waiting_for_mark",
                                "mark": mark_name,
                                "details": self._pending_polite_end_details,
                            }
                        )
                        self._start_final_goodbye_watchdog(twilio_ws, mark_name)

                if event_type == "response.done" and self._patient_response_in_progress:
                    self._finish_patient_response_cooldown()

                if event_type == "response.output_audio_transcript.done":
                    transcript = str(event.get("transcript", "")).strip()
                    if transcript:
                        self._record_conversation_turn("patient", transcript)

                if event_type == "conversation.item.input_audio_transcription.completed":
                    if await self._stop_if_transcript_hits_hard_limit(twilio_ws, event):
                        break
                    self._schedule_patient_response(event)

                if event_type == "input_audio_buffer.speech_started":
                    self._mark_conversation_activity()
                    await self._handle_agent_speech_started(twilio_ws)

                if event_type == "input_audio_buffer.speech_stopped":
                    self._handle_agent_speech_stopped()

                if event_type in {
                    "error",
                    "session.created",
                    "session.updated",
                    "response.done",
                    "response.output_audio_transcript.done",
                    "response.output_audio_transcript.delta",
                    "conversation.item.input_audio_transcription.completed",
                    "input_audio_buffer.speech_started",
                    "input_audio_buffer.speech_stopped",
                    "input_audio_buffer.timeout_triggered",
                }:
                    self._log({"event": "openai", "payload": event})
            except (WebSocketDisconnect, RuntimeError):
                self._stop_requested = True
                break

    def _log(self, payload: dict[str, Any]) -> None:
        append_jsonl(self.state.events_path, {"time": utc_now_iso(), **payload})

    def _call_type(self) -> str:
        return self.state.call_type or scenario_type_for_id(self.state.scenario.id)

    def _call_id(self) -> str:
        if self.state.call_id:
            return self.state.call_id
        call_type = self._call_type()
        call_dir_name = self.state.events_path.parent.name
        if call_dir_name.startswith("call-"):
            return f"{call_type}-{call_dir_name}"
        return "unassigned"

    def _log_call_boundary(
        self,
        boundary: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._log(
            {
                "event": "call.boundary",
                "boundary": boundary,
                "call_id": self._call_id(),
                "scenario_id": self.state.scenario.id,
                "call_type": self._call_type(),
                "details": details or {},
            }
        )

    def _log_call_boundary_end(
        self,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._call_boundary_end_logged:
            return
        self._call_boundary_end_logged = True
        self._log_call_boundary(
            "end",
            {
                "reason": reason,
                **(details or {}),
            },
        )

    def _mark_conversation_activity(self) -> None:
        self._last_conversation_activity_at = asyncio.get_running_loop().time()

    async def _watch_deterministic_limits(self, twilio_ws: WebSocket) -> None:
        while not self._stop_requested:
            await asyncio.sleep(LIMIT_WATCH_INTERVAL_SECONDS)
            if self._call_started_at <= 0.0 or self._last_conversation_activity_at <= 0.0:
                continue

            now = asyncio.get_running_loop().time()
            limits = self.state.scenario.limits
            elapsed = now - self._call_started_at
            silence = now - self._last_conversation_activity_at
            if elapsed >= limits.max_call_seconds:
                await self._terminate_call(
                    twilio_ws,
                    "max_call_duration",
                    {
                        "elapsed_seconds": round(elapsed, 3),
                        "max_call_seconds": limits.max_call_seconds,
                    },
                )
                return
            if silence >= limits.max_silence_seconds:
                await self._terminate_call(
                    twilio_ws,
                    "max_silence",
                    {
                        "silence_seconds": round(silence, 3),
                        "max_silence_seconds": limits.max_silence_seconds,
                    },
                )
                return

    def _start_final_goodbye_watchdog(self, twilio_ws: WebSocket, mark_name: str) -> None:
        if self._final_goodbye_watch_task is not None:
            self._final_goodbye_watch_task.cancel()
        self._final_goodbye_watch_task = asyncio.create_task(
            self._watch_final_goodbye_silence(
                twilio_ws,
                mark_name,
                POST_FINAL_GOODBYE_SILENCE_SECONDS,
            )
        )

    async def _watch_final_goodbye_silence(
        self,
        twilio_ws: WebSocket,
        mark_name: str,
        delay_seconds: float,
    ) -> None:
        try:
            await asyncio.sleep(delay_seconds)
            if self._stop_requested:
                return
            await self._terminate_call(
                twilio_ws,
                "post_final_goodbye_silence",
                {
                    **self._pending_polite_end_details,
                    "mark": mark_name,
                    "silence_seconds": delay_seconds,
                    "agent_spoke_after_final_close": self._agent_spoke_after_final_close,
                },
                clear_twilio=False,
            )
        except asyncio.CancelledError:
            raise

    async def _stop_if_transcript_hits_hard_limit(
        self,
        twilio_ws: WebSocket,
        event: dict[str, Any],
    ) -> bool:
        self._mark_conversation_activity()
        transcript = str(event.get("transcript", "")).strip()
        if self._completion_closing_requested:
            self._agent_spoke_after_final_close = True
            if self._bot_audio_in_progress:
                self._log(
                    {
                        "event": "call.agent_spoke_after_final_close",
                        "action": "preserve_final_audio",
                        "trigger": transcript,
                    }
                )
                return False
            await self._terminate_call(
                twilio_ws,
                "agent_spoke_after_final_close",
                {"trigger": transcript, **self._pending_polite_end_details},
                clear_twilio=False,
            )
            return True
        if transcript_requests_emergency_stop(
            transcript,
            self.state.scenario.limits.emergency_stop_phrases,
        ):
            await self._terminate_call(
                twilio_ws,
                "emergency_stop_phrase",
                {"trigger": transcript},
            )
            return True

        turn_key = build_agent_turn_key(event)
        if turn_key in self._counted_agent_turns:
            return False
        self._counted_agent_turns.add(turn_key)
        self._agent_turn_count += 1
        if self._agent_turn_count <= self.state.scenario.limits.max_turns:
            return False

        await self._terminate_call(
            twilio_ws,
            "max_turns",
            {
                "turn_count": self._agent_turn_count,
                "max_turns": self.state.scenario.limits.max_turns,
            },
        )
        return True

    async def _terminate_call(
        self,
        twilio_ws: WebSocket | None,
        reason: str,
        details: dict[str, Any] | None = None,
        *,
        clear_twilio: bool = True,
    ) -> None:
        if self._stop_requested:
            return
        self._stop_requested = True
        self._log(
            {
                "event": "call.stop_requested",
                "reason": reason,
                "details": details or {},
                "limits": self.state.scenario.limits.to_dict(),
            }
        )
        self._log_call_boundary_end(reason, details or {})
        if self._pending_response_task is not None:
            self._pending_response_task.cancel()
            self._pending_response_task = None
        if self._final_goodbye_watch_task is not None:
            task = self._final_goodbye_watch_task
            self._final_goodbye_watch_task = None
            if task is not asyncio.current_task():
                task.cancel()
        self._pending_transcript_event = None
        self._patient_response_in_progress = False
        self._bot_audio_in_progress = False

        if self._openai_ws is not None:
            with contextlib.suppress(Exception):
                await self._send_openai(build_response_cancel())
            with contextlib.suppress(Exception):
                await self._openai_ws.close()
            self._openai_ws = None

        if twilio_ws is not None:
            if clear_twilio:
                with contextlib.suppress(Exception):
                    await twilio_ws.send_json(build_twilio_clear(self.state.stream_sid))
            with contextlib.suppress(Exception):
                await twilio_ws.close(code=1000)

    def _schedule_patient_response(self, event: dict[str, Any]) -> None:
        if self._stop_requested:
            return
        self._pending_transcript_event = dict(event)
        if self._agent_speech_in_progress and not self.state.scenario.interruption_test:
            self._log(
                {
                    "event": "patient_response.held",
                    "reason": "agent_speech_in_progress",
                    "trigger": str(event.get("transcript", "")),
                }
            )
            return
        self._schedule_pending_patient_response()

    def _schedule_pending_patient_response(self) -> None:
        if self._stop_requested:
            return
        if self._pending_transcript_event is None:
            return

        if self._pending_response_task is not None:
            self._pending_response_task.cancel()
        loop_time = asyncio.get_running_loop().time()
        cooldown_delay = max(0.0, self._cooldown_until - loop_time)
        vad_delay = 0.0
        if (
            not self.state.scenario.interruption_test
            and self._last_agent_speech_stopped_at > 0.0
        ):
            elapsed_since_speech_stopped = loop_time - self._last_agent_speech_stopped_at
            vad_delay = max(
                0.0,
                POST_VAD_SILENCE_CONFIRMATION_SECONDS - elapsed_since_speech_stopped,
            )
        delay = (
            INTERRUPTION_RESPONSE_DELAY_SECONDS
            if self.state.scenario.interruption_test
            else DEFAULT_RESPONSE_DELAY_SECONDS
        )
        event = self._pending_transcript_event
        self._pending_transcript_event = None
        self._pending_response_task = asyncio.create_task(
            self._delayed_patient_response(event, max(delay, cooldown_delay, vad_delay))
        )

    async def _delayed_patient_response(self, event: dict[str, Any], delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            if self._stop_requested:
                return
            await self._maybe_create_patient_response(event)
        except asyncio.CancelledError:
            self._log({"event": "patient_response.cancelled", "reason": "agent_continued"})
            raise

    async def _handle_agent_speech_started(self, twilio_ws: WebSocket) -> None:
        if self._stop_requested:
            return
        self._agent_speech_in_progress = True
        self._pending_transcript_event = None
        if self._pending_response_task is not None:
            self._pending_response_task.cancel()
            self._pending_response_task = None

        if self._completion_closing_requested:
            self._agent_spoke_after_final_close = True
            if self._bot_audio_in_progress:
                self._log(
                    {
                        "event": "agent_speech_after_final_close",
                        "action": "preserve_final_audio",
                    }
                )
                return
            await self._terminate_call(
                twilio_ws,
                "agent_spoke_after_final_close",
                self._pending_polite_end_details,
                clear_twilio=False,
            )
            return

        if not self._bot_audio_in_progress:
            return

        if self.state.scenario.interruption_test:
            self._log({"event": "agent_speech_during_bot_audio", "action": "allowed_for_test"})
            return

        self._bot_audio_in_progress = False
        self._patient_response_in_progress = False
        self._log({"event": "agent_speech_during_bot_audio", "action": "yielded"})
        await self._send_openai(build_response_cancel())
        await twilio_ws.send_json(build_twilio_clear(self.state.stream_sid))

    def _handle_agent_speech_stopped(self) -> None:
        if self._stop_requested:
            return
        self._agent_speech_in_progress = False
        self._last_agent_speech_stopped_at = asyncio.get_running_loop().time()
        self._schedule_pending_patient_response()

    async def _maybe_create_patient_response(self, event: dict[str, Any]) -> None:
        if self._stop_requested:
            return
        transcript = str(event.get("transcript", "")).strip()
        if not transcript:
            self._log({"event": "patient_response.skipped", "reason": "empty_transcript"})
            return
        if self._already_responded_or_busy(event):
            return

        self._record_conversation_turn("agent", transcript)

        if self._completion_closing_requested:
            self._agent_spoke_after_final_close = True
            self._log(
                {
                    "event": "patient_response.skipped",
                    "reason": "final_close_already_requested",
                    "trigger": transcript,
                }
            )
            return

        if not self._goal_introduced:
            if transcript_is_service_opening(transcript):
                self._goal_introduced = True
                await self._create_patient_response(
                    event,
                    build_opening_response(self.state.scenario, transcript),
                    {"event": "patient_response.goal_opening", "trigger": transcript},
                )
                return

            if transcript_is_ignorable_before_opening(transcript):
                self._log({"event": "patient_response.skipped", "reason": "pre_opening_ivr"})
                return

            if transcript_needs_more_agent_context(transcript):
                self._log({"event": "patient_response.skipped", "reason": "partial_agent_turn"})
                return

            if transcript_is_confusing_or_out_of_turn(self.state.scenario, transcript):
                await self._create_patient_response(
                    event,
                    build_confusion_response(self.state.scenario, transcript),
                    {"event": "patient_response.confusion", "trigger": transcript},
                )
                return

            if transcript_is_intake_before_goal(transcript):
                await self._create_patient_response(
                    event,
                    self._build_stateful_patient_response(event, pre_goal=True),
                    {"event": "patient_response.pre_goal", "trigger": transcript},
                )
                return

            await self._create_patient_response(
                event,
                self._build_stateful_patient_response(event, pre_goal=True),
                {"event": "patient_response.pre_goal", "trigger": transcript},
            )
            return

        if transcript_needs_more_agent_context(transcript):
            self._log({"event": "patient_response.skipped", "reason": "partial_agent_turn"})
            return

        if transcript_is_confusing_or_out_of_turn(self.state.scenario, transcript):
            await self._create_patient_response(
                event,
                build_confusion_response(self.state.scenario, transcript),
                {"event": "patient_response.confusion", "trigger": transcript},
            )
            return

        completion = self._completion_verdict_if_ready(transcript)
        if completion is not None:
            closing_options = completion_closing_options(self.state.scenario, transcript)
            closing_variant_index = self._random.randrange(len(closing_options))
            self._completion_closing_requested = True
            self._pending_polite_end_details = {
                **completion,
                "closing_variant_index": closing_variant_index,
            }
            await self._create_patient_response(
                event,
                build_completion_closing_response(
                    self.state.scenario,
                    transcript,
                    str(completion["reason"]),
                    closing_variant_index,
                ),
                {
                    "event": "patient_response.completion_closing",
                    "trigger": transcript,
                    "completion": self._pending_polite_end_details,
                },
            )
            return

        await self._create_patient_response(
            event,
            self._build_stateful_patient_response(event, pre_goal=False),
            {"event": "patient_response.turn", "trigger": transcript},
        )

    def _completion_verdict_if_ready(self, latest_agent_transcript: str) -> dict[str, Any] | None:
        if self._completion_closing_requested:
            return None
        if not self._goal_introduced:
            return None
        if self._call_started_at <= 0.0:
            return None

        elapsed = asyncio.get_running_loop().time() - self._call_started_at
        if elapsed < MIN_COMPLETION_CHECK_SECONDS:
            return None

        verdict = evaluate_scenario_completion(
            self.state.scenario,
            self._conversation_turns,
            latest_agent_transcript,
        )
        if verdict is None:
            return None

        return {
            **verdict,
            "elapsed_seconds": round(elapsed, 3),
            "min_completion_check_seconds": MIN_COMPLETION_CHECK_SECONDS,
            "success_criteria": self.state.scenario.success_criteria,
        }

    def _build_stateful_patient_response(
        self,
        event: dict[str, Any],
        *,
        pre_goal: bool,
    ) -> dict[str, Any]:
        transcript = str(event.get("transcript", "")).strip()
        meta_answer = build_meta_guardrail_answer(self.state.scenario, transcript)
        if meta_answer:
            if pre_goal:
                return build_pre_goal_response(self.state.scenario, transcript)
            return build_turn_response(self.state.scenario, transcript)

        info_key = requested_info_key(self.state.scenario, transcript)
        exact_answer = build_exact_fact_answer(self.state.scenario, transcript)
        if info_key and exact_answer:
            repeat_count = self._provided_info_counts.get(info_key, 0)
            answer = exact_answer
            if should_point_out_repeated_info(repeat_count, self._random.random()):
                answer = self._build_repeated_info_answer(info_key, exact_answer)
            self._provided_info_counts[info_key] = repeat_count + 1
            return {
                "type": "response.create",
                "response": {"instructions": f"Say only this exact patient answer: {answer}"},
            }

        if pre_goal:
            return build_pre_goal_response(self.state.scenario, transcript)
        return build_turn_response(self.state.scenario, transcript)

    def _build_repeated_info_answer(self, info_key: str, exact_answer: str) -> str:
        previous_index = self._last_repeated_info_template_index.get(info_key)
        template_count = len(REPEATED_INFO_TEMPLATES)
        template_index = self._random.randrange(template_count)
        if previous_index is not None and template_count > 1:
            offset = self._random.randrange(template_count - 1)
            template_index = (previous_index + 1 + offset) % template_count
        self._last_repeated_info_template_index[info_key] = template_index
        return build_repeated_info_answer(info_key, exact_answer, template_index)

    def _record_conversation_turn(self, speaker: str, text: str) -> None:
        cleaned = " ".join(text.split())
        if not cleaned:
            return
        if self._conversation_turns and self._conversation_turns[-1] == {
            "speaker": speaker,
            "text": cleaned,
        }:
            return
        self._conversation_turns.append({"speaker": speaker, "text": cleaned})
        if len(self._conversation_turns) > MAX_STORED_CONVERSATION_TURNS:
            self._conversation_turns = self._conversation_turns[-MAX_STORED_CONVERSATION_TURNS:]

    def _already_responded_or_busy(self, event: dict[str, Any]) -> bool:
        turn_key = build_agent_turn_key(event)
        if turn_key in self._responded_agent_turns:
            self._log({"event": "patient_response.skipped", "reason": "turn_already_answered"})
            return True
        if self._patient_response_in_progress:
            self._log({"event": "patient_response.skipped", "reason": "response_in_progress"})
            return True
        return False

    async def _create_patient_response(
        self,
        event: dict[str, Any],
        response: dict[str, Any],
        log_payload: dict[str, Any],
    ) -> None:
        if self._stop_requested:
            return
        turn_key = build_agent_turn_key(event)
        if turn_key in self._responded_agent_turns:
            self._log({"event": "patient_response.skipped", "reason": "turn_already_answered"})
            return
        if self._patient_response_in_progress:
            self._log({"event": "patient_response.skipped", "reason": "response_in_progress"})
            return

        self._responded_agent_turns.add(turn_key)
        self._patient_response_in_progress = True
        self._log(log_payload)
        await self._send_openai(response)

    def _finish_patient_response_cooldown(self) -> None:
        self._patient_response_in_progress = False
        self._cooldown_until = (
            asyncio.get_running_loop().time() + POST_RESPONSE_COOLDOWN_SECONDS
        )
