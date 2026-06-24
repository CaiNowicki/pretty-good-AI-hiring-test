import unittest
from pathlib import Path

from voicebot.scenario import (
    build_patient_system_prompt,
    build_realtime_bootstrap,
    load_scenario,
    ordered_scenario_stems,
)


class ScenarioTests(unittest.TestCase):
    def test_loads_smoke_scenario_by_file_stem(self):
        scenario = load_scenario("t01_smoke")

        self.assertEqual(scenario.id, "T-01-smoke")
        self.assertEqual(scenario.patient_profile, "james_carter")
        self.assertEqual(
            scenario.opening_line,
            "Hi, I'm hoping to make an appointment. I'm a new patient.",
        )
        self.assertEqual(scenario.facts["name"], "James Carter")
        self.assertEqual(scenario.facts["date_of_birth"], "March 14, 1987")
        self.assertIn("date_of_birth", scenario.required_facts)
        self.assertTrue(scenario.optional_edge_behavior)

    def test_loads_smoke_scenario_by_declared_id(self):
        scenario = load_scenario("T-01-smoke")

        self.assertEqual(scenario.patient_profile, "james_carter")

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

    def test_prompt_uses_scenario_facts_without_scripted_dialogue(self):
        scenario = load_scenario("t01_smoke")
        prompt = build_patient_system_prompt(scenario)

        self.assertIn("James Carter", prompt)
        self.assertIn("date_of_birth: March 14, 1987", prompt)
        self.assertIn("Answer with the provided facts only when asked.", prompt)
        self.assertIn("Do not volunteer everything at once.", prompt)
        self.assertIn("Respond to the agent's most recent question only.", prompt)
        self.assertIn("referral status, provider preference", prompt)
        self.assertIn("ask one question at a time", prompt)
        self.assertIn("Wait for the agent to finish speaking before responding.", prompt)
        self.assertIn("Say the opening line once only.", prompt)
        self.assertIn("Do not interrupt the agent.", prompt)

    def test_realtime_bootstrap_includes_opening_utterance(self):
        scenario = load_scenario("t01_smoke")
        bootstrap = build_realtime_bootstrap(scenario)

        self.assertEqual(bootstrap["patient_profile"], "james_carter")
        self.assertEqual(bootstrap["initial_patient_utterance"], scenario.opening_line)
        self.assertIn("James Carter", bootstrap["system_prompt"])

    def test_loads_all_appointment_scheduling_scenarios(self):
        scenario_files = {
            "a01_specific_time": "A-01-specific-time",
            "a02_change_of_mind": "A-02-change-of-mind",
            "a03_vague_narrow": "A-03-vague-then-narrow",
            "a04_cancel_no_date": "A-04-cancel-no-date",
            "a05_reschedule_day": "A-05-reschedule-different-day",
            "a06_closed_hours": "A-06-closed-hours-trap",
            "a07_interruption": "A-07-interruption-barge-in",
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
        self.assertFalse(load_scenario("d03_background_interruptions").interruption_test)

        ordered = ordered_scenario_stems()
        first_difficult_index = ordered.index("d01_hard_of_hearing")
        standard_indices = [
            index
            for index, stem in enumerate(ordered)
            if stem.startswith(("t", "a", "i"))
        ]
        self.assertTrue(all(index < first_difficult_index for index in standard_indices))

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
        self.assertIn("interruption-handling scenario", prompt)
        self.assertIn("interrupt the agent once", prompt)

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
