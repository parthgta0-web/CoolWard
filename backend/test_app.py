"""Regression checks for local verification-first replanning."""

import json
import unittest

from app import build_plan, handler, load_data


class LocalLambdaContext:
    function_name = "OptimiseFunction"
    function_version = "$LATEST"
    invoked_function_arn = "arn:aws:lambda:local:0:function:OptimiseFunction"
    memory_limit_in_mb = 256
    aws_request_id = "local-test-request"

    def get_remaining_time_in_millis(self):
        return 9000


class ReplanningTests(unittest.TestCase):
    def setUp(self):
        self.data = load_data()

    def test_default_400m_results_match_the_validated_primary_scenario(self):
        expected = {
            5: (58.1852, ["candidate_019"], 5, 0),
            10: (85.6141, ["candidate_019", "candidate_046"], 10, 0),
            15: (94.3440, ["candidate_019", "candidate_046", "candidate_025"], 15, 0),
            20: (97.9120, ["candidate_019", "candidate_046", "candidate_025", "candidate_045"], 20, 0),
            25: (97.9120, ["candidate_019", "candidate_046", "candidate_025", "candidate_045"], 20, 5),
            30: (97.9120, ["candidate_019", "candidate_046", "candidate_025", "candidate_045"], 20, 10),
            35: (97.9120, ["candidate_019", "candidate_046", "candidate_025", "candidate_045"], 20, 15),
        }
        for budget, (coverage, identifiers, spent, unallocated) in expected.items():
            plan = build_plan(self.data, budget)
            self.assertEqual(plan["modelled_priority_coverage_percent"], coverage)
            self.assertEqual([site["candidate_id"] for site in plan["selected_sites"]], identifiers)
            self.assertEqual(plan["spent_lakh"], spent)
            self.assertEqual(plan["unallocated_lakh"], unallocated)

    def test_each_supported_threshold_replans_from_exported_network_coverage(self):
        expected = {
            300: (38.1159, 89.7410),
            400: (58.1852, 97.9120),
            500: (78.8755, 97.9120),
        }
        for threshold, (five_lakh_coverage, twenty_lakh_coverage) in expected.items():
            with self.subTest(threshold=threshold):
                self.assertEqual(build_plan(self.data, 5, threshold)["modelled_priority_coverage_percent"], five_lakh_coverage)
                self.assertEqual(build_plan(self.data, 20, threshold)["modelled_priority_coverage_percent"], twenty_lakh_coverage)

    def test_exclusion_is_deterministic_and_never_increases_coverage(self):
        baseline = build_plan(self.data, 20, 400)
        excluded_id = baseline["selected_sites"][0]["candidate_id"]
        first = build_plan(self.data, 20, 400, [excluded_id])
        second = build_plan(self.data, 20, 400, [excluded_id])
        self.assertEqual(first["selected_sites"], second["selected_sites"])
        self.assertEqual(first["covered_demand_cell_ids"], second["covered_demand_cell_ids"])
        self.assertEqual(first["excluded_candidate_ids"], [excluded_id])
        self.assertLessEqual(first["modelled_priority_coverage_percent"], baseline["modelled_priority_coverage_percent"])

    def test_default_400m_site_one_is_replaceable_and_site_two_replans_to_94_3_percent(self):
        baseline = build_plan(self.data, 20, 400)
        site_one, site_two = baseline["selected_sites"][:2]
        self.assertEqual(site_one["verification_insight"]["classification"], "replaceable")
        self.assertEqual(build_plan(self.data, 20, 400, [site_one["candidate_id"]])["modelled_priority_coverage_percent"], 97.9120)
        self.assertEqual(site_two["candidate_id"], "candidate_046")
        self.assertEqual(build_plan(self.data, 20, 400, [site_two["candidate_id"]])["modelled_priority_coverage_percent"], 94.3440)

    def test_every_selected_site_has_a_verification_backup_insight(self):
        plan = build_plan(self.data, 20, 400)
        for site in plan["selected_sites"]:
            with self.subTest(candidate_id=site["candidate_id"]):
                insight = site["verification_insight"]
                self.assertIn(insight["classification"], {"critical", "replaceable"})
                self.assertIn("best_available_backup_plan", insight)
                self.assertLessEqual(insight["best_available_backup_plan"]["modelled_priority_coverage_percent"], plan["modelled_priority_coverage_percent"])

    def test_lambda_handler_accepts_replanning_request(self):
        response = handler({"body": json.dumps({"budget_lakh": 20, "threshold_m": 300, "excluded_candidate_ids": ["candidate_019"]})}, LocalLambdaContext())
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["threshold_m"], 300)
        self.assertEqual(body["excluded_candidate_ids"], ["candidate_019"])
        self.assertIn("Simulation only", body["explanation"])

    def test_lambda_handler_rejects_malformed_requests(self):
        invalid_bodies = [[], "not an object", None, {"threshold_m": 350}, {"excluded_candidate_ids": "candidate_019"}, {"excluded_candidate_ids": ["not-a-candidate"]}]
        for invalid_body in invalid_bodies:
            with self.subTest(invalid_body=invalid_body):
                response = handler({"body": json.dumps(invalid_body)}, LocalLambdaContext())
                self.assertEqual(response["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
