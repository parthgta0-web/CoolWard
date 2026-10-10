"""Deterministic regression checks for the primary 400 m local API data."""

import json
import unittest

from app import handler, load_data, optimise


class LocalLambdaContext:
    function_name = "OptimiseFunction"
    function_version = "$LATEST"
    invoked_function_arn = "arn:aws:lambda:local:0:function:OptimiseFunction"
    memory_limit_in_mb = 256
    aws_request_id = "local-test-request"

    def get_remaining_time_in_millis(self):
        return 9000


class PrimaryScenarioTests(unittest.TestCase):
    def test_every_budget_matches_validated_coverage_and_site_count(self):
        expected = {
            5: (58.1852, 1, 5, 0), 10: (85.6141, 2, 10, 0),
            15: (94.3440, 3, 15, 0), 20: (97.9120, 4, 20, 0),
            25: (97.9120, 4, 20, 5), 30: (97.9120, 4, 20, 10), 35: (97.9120, 4, 20, 15),
        }
        data = load_data()
        for budget, (coverage, count, spent, unallocated) in expected.items():
            plan = optimise(data, budget)
            self.assertEqual(plan["modelled_priority_coverage_percent"], coverage)
            self.assertEqual(len(plan["selected_sites"]), count)
            self.assertEqual(plan["spent_lakh"], spent)
            self.assertEqual(plan["unallocated_lakh"], unallocated)

    def test_coverage_never_decreases_as_budget_increases(self):
        data = load_data()
        coverage = [optimise(data, budget)["modelled_priority_coverage_percent"] for budget in (5, 10, 15, 20, 25, 30, 35)]
        self.assertEqual(coverage, sorted(coverage))

    def test_lambda_handler_returns_plateau_and_map_layers(self):
        response = handler({"body": json.dumps({"budget_lakh": 35})}, LocalLambdaContext())
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["unallocated_lakh"], 15)
        self.assertEqual(len(body["selected_sites"]), 4)
        self.assertIn("heat_priority_demand_cells", body["layers"])


if __name__ == "__main__":
    unittest.main()
