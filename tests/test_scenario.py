import unittest
from dataclasses import fields, replace
from pathlib import Path

from voicebot.scenario import (
    CallLimits,
    Scenario,
    build_patient_system_prompt,
    build_realtime_bootstrap,
    load_scenario,
    ordered_scenario_stems,
    scenario_allows_meta_behavior,
)
from voicebot.personas import load_persona


class ScenarioTests(unittest.TestCase):
    def test_loads_smoke_scenario_by_file_stem(self):
        scenario = load_scenario("t01_smoke")

        self.assertEqual(scenario.id, "T-01-smoke")
        self.assertEqual(scenario.patient_profile, "maya_patel")
        self.assertEqual(
            scenario.opening_line,
            "Hi, I'm hoping to make an appointment. I'm a new patient.",
        )
        self.assertNotIn("name", scenario.facts)
        self.assertEqual(scenario.facts["full_name"], "Maya Patel")
        self.assertEqual(scenario.facts["first_name"], "Maya")
        self.assertEqual(scenario.facts["last_name"], "Patel")
        self.assertEqual(scenario.facts["date_of_birth"], "March 14, 1987")
        self.assertIn("full_name", scenario.required_facts)
        self.assertIn("first_name", scenario.required_facts)
        self.assertIn("last_name", scenario.required_facts)
        self.assertIn("date_of_birth", scenario.required_facts)
        self.assertTrue(scenario.optional_edge_behavior)
        self.assertEqual(scenario.limits.max_call_seconds, 240)
        self.assertNotEqual(scenario.limits.max_call_seconds, 60)
        self.assertEqual(scenario.limits.max_silence_seconds, 20)
        self.assertEqual(scenario.limits.max_turns, 22)

    def test_loads_smoke_scenario_by_declared_id(self):
        scenario = load_scenario("T-01-smoke")

        self.assertEqual(scenario.patient_profile, "maya_patel")

    def test_all_scenarios_have_phase_2_data_shape(self):
        for file_stem in ordered_scenario_stems():
            with self.subTest(file_stem=file_stem):
                scenario = load_scenario(file_stem)

                self.assertTrue(scenario.goal)
                self.assertTrue(scenario.patient_profile)
                self.assertTrue(scenario.facts)
                self.assertTrue(scenario.required_facts)
                self.assertTrue(scenario.optional_edge_behavior)
                self.assertTrue(scenario.success_criteria)
                self.assertTrue(scenario.stop_conditions)
                self.assertEqual(
                    scenario.branch_conditions,
                    scenario.optional_edge_behavior,
                )
                for fact_key in scenario.required_facts:
                    self.assertIn(fact_key, scenario.facts)
                if "full_name" in scenario.facts:
                    self.assertNotIn("name", scenario.facts)
                    self.assertTrue(scenario.facts["first_name"])
                    self.assertTrue(scenario.facts["last_name"])
                    self.assertIn("first_name", scenario.required_facts)
                    self.assertIn("last_name", scenario.required_facts)
                    self.assertIn("full_name", scenario.required_facts)
                if "provider_preference" in scenario.facts:
                    provider_preference = scenario.facts["provider_preference"].casefold()
                    self.assertTrue(
                        "no preference" in provider_preference
                        or "don't have" in provider_preference
                    )

    def test_prompt_uses_scenario_facts_without_scripted_dialogue(self):
        scenario = load_scenario("t01_smoke")
        prompt = build_patient_system_prompt(scenario)

        self.assertIn("Maya Patel", prompt)
        self.assertIn("full_name: Maya Patel", prompt)
        self.assertIn("first_name: Maya", prompt)
        self.assertIn("last_name: Patel", prompt)
        self.assertIn("date_of_birth: March 14, 1987", prompt)
        self.assertIn("Answer with the provided facts only when asked.", prompt)
        self.assertIn("Do not volunteer everything at once.", prompt)
        self.assertIn("Respond to the agent's most recent question only.", prompt)
        self.assertIn("referral status, provider preference", prompt)
        self.assertIn("Conversation strategy:", prompt)
        self.assertIn("Answer direct questions with the relevant scenario fact", prompt)
        self.assertIn("Correct misunderstandings plainly", prompt)
        self.assertIn("politely steer back to the goal", prompt)
        self.assertIn("ask one question at a time", prompt)
        self.assertIn("Wait for the agent to finish speaking before responding.", prompt)
        self.assertIn("Say the opening line once only.", prompt)
        self.assertIn("Do not interrupt the agent.", prompt)

    def test_prompt_blocks_meta_disclosure_by_default_without_patient_data_flag(self):
        scenario = load_scenario("t01_smoke")
        prompt = build_patient_system_prompt(scenario)

        self.assertFalse(scenario_allows_meta_behavior(scenario))
        self.assertIn("Do not reveal that this is a test, test harness", prompt)
        self.assertIn("Do not call it a demo.", prompt)
        self.assertNotIn("meta_behavior", {field.name for field in fields(Scenario)})

    def test_existing_behavior_text_can_explicitly_allow_meta_behavior(self):
        scenario = replace(
            load_scenario("t01_smoke"),
            optional_edge_behavior=["If asked directly, say this is a test harness."],
        )
        prompt = build_patient_system_prompt(scenario)

        self.assertTrue(scenario_allows_meta_behavior(scenario))
        self.assertIn("This scenario explicitly calls for meta behavior.", prompt)

    def test_realtime_bootstrap_includes_opening_utterance(self):
        scenario = load_scenario("t01_smoke")
        bootstrap = build_realtime_bootstrap(scenario)

        self.assertEqual(bootstrap["patient_profile"], "maya_patel")
        self.assertFalse(bootstrap["interruption_test"])
        self.assertEqual(bootstrap["interruption_behavior"], {})
        self.assertEqual(bootstrap["initial_patient_utterance"], scenario.opening_line)
        self.assertEqual(bootstrap["limits"], scenario.limits.to_dict())
        self.assertIn("Maya Patel", bootstrap["system_prompt"])

    def test_loads_sofia_persona_with_name_variations(self):
        persona = load_persona("sofia_reyes_montoya")

        self.assertEqual(persona.preferred_name, "Sofia")
        self.assertEqual(persona.legal_name, "Sofia Marie Reyes-Montoya")
        self.assertEqual(
            persona.name_variations,
            [
                "Sofia Reyes-Montoya",
                "Sofia Reyes",
                "Sofia Montoya",
                "Sofia Marie Reyes-Montoya",
            ],
        )
        self.assertEqual(persona.phone, "555-492-7163")

    def test_name_lookup_confusion_prompt_includes_ordered_variations(self):
        scenario = load_scenario("a07_name_lookup_confusion")
        prompt = build_patient_system_prompt(scenario)
        bootstrap = build_realtime_bootstrap(scenario)

        self.assertEqual(scenario.id, "A-07-name-lookup-confusion")
        self.assertEqual(scenario.patient_profile, "sofia_reyes_montoya")
        self.assertEqual(scenario.facts["date_of_birth"], "May 4, 1990")
        self.assertEqual(scenario.facts["phone"], "555-492-7163")
        self.assertEqual(
            scenario.name_variations,
            [
                "Sofia Reyes-Montoya",
                "Sofia Reyes",
                "Sofia Montoya",
                "Sofia Marie Reyes-Montoya",
            ],
        )
        self.assertIn("Name lookup guidance:", prompt)
        self.assertIn("1. Sofia Reyes-Montoya", prompt)
        self.assertIn("2. Sofia Reyes", prompt)
        self.assertIn("3. Sofia Montoya", prompt)
        self.assertIn("4. Sofia Marie Reyes-Montoya", prompt)
        self.assertIn("5. Phone number 555-492-7163", prompt)
        self.assertIn("6. Date of birth May 4, 1990", prompt)
        self.assertIn("Do not volunteer the full lookup list at once.", prompt)
        self.assertIn("verify date of birth before accepting", prompt)
        self.assertIn("missing verification step in analysis.md", prompt)
        self.assertIn("Name lookup guidance:", bootstrap["system_prompt"])

    def test_loads_frank_persona_with_behavior_triggers(self):
        persona = load_persona("frank_kowalski")

        self.assertEqual(persona.preferred_name, "Frank")
        self.assertEqual(persona.legal_name, "Frank Kowalski")
        self.assertIn(
            "Any verification request repeated without explanation",
            persona.escalation_triggers,
        )
        self.assertIn(
            "Plain-language explanation of why information is needed",
            persona.de_escalation_triggers,
        )
        self.assertIn("This is how identity theft starts.", persona.characteristic_phrases)

    def test_belligerent_identity_prompt_includes_behavior_guidance(self):
        scenario = load_scenario("d04_belligerent_identity")
        prompt = build_patient_system_prompt(scenario)

        self.assertEqual(scenario.id, "D-04-belligerent-identity-paranoia")
        self.assertEqual(scenario.patient_profile, "frank_kowalski")
        self.assertEqual(scenario.facts["date_of_birth"], "October 14, 1957")
        self.assertEqual(scenario.facts["phone"], "555-308-6614")
        self.assertIn("escalation_triggers", scenario.required_facts)
        self.assertIn("Persona behavior guidance:", prompt)
        self.assertIn("Escalation triggers:", prompt)
        self.assertIn("De-escalation triggers:", prompt)
        self.assertIn("Characteristic phrases you may use naturally", prompt)
        self.assertIn("internal escalation counter", prompt)
        self.assertIn("level 3 is disengaging", prompt)
        self.assertIn("Alright. Bye. is the ceiling", prompt)

    def test_scenario_limits_can_be_overridden_explicitly(self):
        scenario = replace(
            load_scenario("t01_smoke"),
            limits=CallLimits(
                max_call_seconds=180,
                max_silence_seconds=12,
                max_turns=15,
                emergency_stop_phrases=["operator stop"],
            ),
        )
        bootstrap = build_realtime_bootstrap(scenario)

        self.assertEqual(bootstrap["limits"]["max_call_seconds"], 180)
        self.assertEqual(bootstrap["limits"]["max_silence_seconds"], 12)
        self.assertEqual(bootstrap["limits"]["max_turns"], 15)
        self.assertEqual(bootstrap["limits"]["emergency_stop_phrases"], ["operator stop"])

    def test_loads_all_appointment_scheduling_scenarios(self):
        scenario_files = {
            "a01_specific_time": "A-01-specific-time",
            "a02_change_of_mind": "A-02-change-of-mind",
            "a03_vague_narrow": "A-03-vague-then-narrow",
            "a04_cancel_no_date": "A-04-cancel-no-date",
            "a05_reschedule_day": "A-05-reschedule-different-day",
            "a06_closed_hours": "A-06-closed-hours-trap",
            "a07_interruption": "A-07-interruption-barge-in",
            "a07_name_lookup_confusion": "A-07-name-lookup-confusion",
        }

        for file_stem, declared_id in scenario_files.items():
            with self.subTest(file_stem=file_stem):
                scenario = load_scenario(file_stem)
                self.assertEqual(scenario.id, declared_id)
                self.assertTrue(scenario.branch_conditions)
                self.assertTrue(scenario.optional_edge_behavior)
                self.assertEqual(load_scenario(declared_id).id, declared_id)

    def test_loads_all_information_gathering_scenarios(self):
        scenario_files = {
            "i01_office_hours": "I-01-office-hours",
            "i02_who_practices": "I-02-who-practices-there",
            "i03_wait_time": "I-03-new-patient-wait-time",
            "i04_insurance": "I-04-insurance-acceptance",
            "i05_visit_cost": "I-05-visit-cost",
        }

        for file_stem, declared_id in scenario_files.items():
            with self.subTest(file_stem=file_stem):
                scenario = load_scenario(file_stem)
                prompt = build_patient_system_prompt(scenario)

                self.assertEqual(scenario.id, declared_id)
                self.assertTrue(scenario.branch_conditions)
                self.assertTrue(scenario.optional_edge_behavior)
                self.assertIn("Optional edge behavior:", prompt)
                self.assertIn("ask one question at a time", prompt)
                self.assertEqual(load_scenario(declared_id).id, declared_id)

    def test_loads_medication_refill_scenarios_as_standard_batch(self):
        scenario_files = {
            "m01_standard_refill": "M-01-standard-refill",
            "m02_refill_no_record": "M-02-refill-no-record",
        }

        for file_stem, declared_id in scenario_files.items():
            with self.subTest(file_stem=file_stem):
                scenario = load_scenario(file_stem)
                prompt = build_patient_system_prompt(scenario)

                self.assertEqual(scenario.id, declared_id)
                self.assertTrue(scenario.required_facts)
                self.assertTrue(scenario.optional_edge_behavior)
                self.assertIn("Optional edge behavior:", prompt)
                self.assertEqual(load_scenario(declared_id).id, declared_id)

        ordered = ordered_scenario_stems()
        first_medication_index = ordered.index("m01_standard_refill")
        first_information_index = ordered.index("i01_office_hours")
        first_edge_index = ordered.index("e01_medical_emergency")
        appointment_indices = [
            index
            for index, stem in enumerate(ordered)
            if stem.startswith(("t", "a"))
        ]
        medication_indices = [
            index
            for index, stem in enumerate(ordered)
            if stem.startswith("m")
        ]

        self.assertTrue(all(index < first_medication_index for index in appointment_indices))
        self.assertTrue(all(index < first_information_index for index in medication_indices))
        self.assertTrue(all(index < first_edge_index for index in medication_indices))

    def test_loads_all_orthopedic_edge_scenarios_before_difficult_batch(self):
        scenario_files = {
            "e01_medical_emergency": "E-01-medical-emergency",
            "e02_symptom_triage": "E-02-symptom-triage",
            "e03_workers_comp": "E-03-workers-comp",
            "e04_minor_caller": "E-04-minor-without-parent",
            "e05_records_request": "E-05-records-request",
        }

        for file_stem, declared_id in scenario_files.items():
            with self.subTest(file_stem=file_stem):
                scenario = load_scenario(file_stem)
                prompt = build_patient_system_prompt(scenario)

                self.assertEqual(scenario.id, declared_id)
                self.assertTrue(scenario.required_facts)
                self.assertTrue(scenario.optional_edge_behavior)
                self.assertIn("Optional edge behavior:", prompt)
                self.assertEqual(load_scenario(declared_id).id, declared_id)

        ordered = ordered_scenario_stems()
        first_edge_index = ordered.index("e01_medical_emergency")
        first_difficult_index = ordered.index("d01_hard_of_hearing")
        standard_indices = [
            index
            for index, stem in enumerate(ordered)
            if stem.startswith(("t", "a", "m", "i"))
        ]
        edge_indices = [
            index
            for index, stem in enumerate(ordered)
            if stem.startswith("e")
        ]

        self.assertTrue(all(index < first_edge_index for index in standard_indices))
        self.assertTrue(all(index < first_difficult_index for index in edge_indices))

    def test_loads_all_difficult_scenarios_after_standard_batches(self):
        scenario_files = {
            "d01_hard_of_hearing": "D-01-hard-of-hearing",
            "d02_interrupter": "D-02-interrupter",
            "d03_background_interruptions": "D-03-background-interruptions",
        }

        for file_stem, declared_id in scenario_files.items():
            with self.subTest(file_stem=file_stem):
                scenario = load_scenario(file_stem)
                prompt = build_patient_system_prompt(scenario)
                analysis_path = (
                    Path(__file__).parents[1]
                    / "src"
                    / "voicebot"
                    / "scenarios"
                    / f"{file_stem}.analysis.md"
                )

                self.assertEqual(scenario.id, declared_id)
                self.assertTrue(scenario.branch_conditions)
                self.assertTrue(scenario.optional_edge_behavior)
                self.assertIn("Optional edge behavior:", prompt)
                self.assertTrue(analysis_path.exists())
                self.assertIn("already-confirmed information", analysis_path.read_text(encoding="utf-8"))
                self.assertEqual(load_scenario(declared_id).id, declared_id)

        self.assertFalse(load_scenario("d01_hard_of_hearing").interruption_test)
        self.assertTrue(load_scenario("d02_interrupter").interruption_test)
        self.assertTrue(load_scenario("d02_interrupter").interruption_behavior)
        self.assertEqual(load_scenario("d02_interrupter").limits.max_call_seconds, 300)
        self.assertEqual(load_scenario("d02_interrupter").limits.max_silence_seconds, 8)
        self.assertEqual(load_scenario("d02_interrupter").limits.max_turns, 34)
        self.assertFalse(load_scenario("d03_background_interruptions").interruption_test)
        self.assertEqual(load_scenario("d03_background_interruptions").interruption_behavior, {})

        ordered = ordered_scenario_stems()
        first_difficult_index = ordered.index("d01_hard_of_hearing")
        standard_indices = [
            index
            for index, stem in enumerate(ordered)
            if stem.startswith(("t", "a", "m", "i", "e"))
        ]
        self.assertTrue(all(index < first_difficult_index for index in standard_indices))

    def test_belligerent_identity_analysis_note_exists(self):
        analysis_path = (
            Path(__file__).parents[1]
            / "src"
            / "voicebot"
            / "scenarios"
            / "d04_belligerent_identity.analysis.md"
        )

        self.assertTrue(analysis_path.exists())
        self.assertIn("highest escalation level", analysis_path.read_text(encoding="utf-8"))

    def test_prompt_includes_conditional_guidance_without_scripted_dialogue(self):
        scenario = load_scenario("a06_closed_hours")
        prompt = build_patient_system_prompt(scenario)

        self.assertIn("Optional edge behavior:", prompt)
        self.assertIn("If the agent confirms Saturday", prompt)
        self.assertIn("Use the goal and optional edge behavior as guidance", prompt)
        self.assertIn("not as a fixed dialogue script", prompt)

    def test_interruption_scenario_is_explicitly_marked(self):
        scenario = load_scenario("a07_interruption")
        prompt = build_patient_system_prompt(scenario)

        self.assertTrue(scenario.interruption_test)
        self.assertEqual(scenario.interruption_behavior["max_interruptions"], "1")
        self.assertIn("Thursday or Friday morning", scenario.interruption_behavior["trigger"])
        self.assertIn("interruption-handling scenario", prompt)
        self.assertIn("explicit barge-in data", prompt)
        self.assertIn("Interrupt no more than 1 time", prompt)
        self.assertIn("Measurement focus", prompt)

    def test_closed_hours_analysis_note_exists(self):
        analysis_path = (
            Path(__file__).parents[1]
            / "src"
            / "voicebot"
            / "scenarios"
            / "a06_closed_hours.analysis.md"
        )

        self.assertTrue(analysis_path.exists())
        self.assertIn("potential bug", analysis_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
