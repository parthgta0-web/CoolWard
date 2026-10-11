"""Regression checks for local verification-first replanning."""

import json
import unittest

from app import (
    PREFERRED_PRIMARY_400M_IDS,
    SUPPORTED_BUDGETS,
    build_all_plans,
    build_plan,
    exact_solution_bruteforce,
    handler,
    load_data,
    ordered_selected_sites,
    score,
)


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

    def test_bitmask_all_tier_solutions_match_the_legacy_bruteforce_oracle(self):
        inputs = self.data["replanning_inputs"]
        weights = {identifier: float(value) for identifier, value in inputs["demand_weights"].items()}
        candidate_features = {
            feature["properties"]["candidate_id"]: feature
            for feature in self.data["layers"]["possible_candidate_sites"]["features"]
        }
        for threshold in (300, 400, 500):
            with self.subTest(threshold=threshold):
                plans = {plan["budget_lakh"]: plan for plan in build_all_plans(self.data, threshold, (), 20)}
                candidate_sets = {
                    identifier: set(demand_ids)
                    for identifier, demand_ids in inputs["candidate_coverage"][str(threshold)].items()
                }
                preferred_ids = PREFERRED_PRIMARY_400M_IDS if threshold == 400 else ()
                for budget in sorted(SUPPORTED_BUDGETS):
                    selected_ids, covered_ids = exact_solution_bruteforce(
                        candidate_sets,
                        weights,
                        budget // inputs["standard_unit_cost_lakh"],
                        preferred_ids,
                    )
                    expected_order = [
                        site["candidate_id"]
                        for site in ordered_selected_sites(selected_ids, candidate_sets, weights, candidate_features, inputs)
                    ]
                    self.assertEqual(
                        [site["candidate_id"] for site in plans[budget]["selected_sites"]],
                        expected_order,
                    )
                    self.assertEqual(
                        plans[budget]["covered_demand_cell_ids"],
                        sorted(covered_ids),
                    )
                    self.assertEqual(
                        plans[budget]["modelled_priority_coverage_percent"],
                        round(100 * score(covered_ids, weights) / score(weights, weights), 4),
                    )

    def test_bulk_response_calculates_verification_insights_only_for_active_budget(self):
        plans = {plan["budget_lakh"]: plan for plan in build_all_plans(self.data, 400, (), 20)}
        self.assertIn("verification_insight", plans[20]["selected_sites"][0])
        self.assertNotIn("verification_insight", plans[5]["selected_sites"][0])

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

    def test_lambda_handler_returns_all_budget_tiers_without_repeating_map_layers(self):
        response = handler({"body": json.dumps({"threshold_m": 400})}, LocalLambdaContext())
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual([plan["budget_lakh"] for plan in body["plans"]], sorted(SUPPORTED_BUDGETS))
        self.assertEqual(body["plans"][0]["modelled_priority_coverage_percent"], 58.1852)
        self.assertEqual(body["plans"][3]["modelled_priority_coverage_percent"], 97.9120)
        self.assertNotIn("layers", body)
        self.assertGreaterEqual(body["recomputed_local_ms"], 0)

    def test_lambda_handler_returns_static_layers_only_when_requested(self):
        response = handler({"body": json.dumps({"threshold_m": 400, "include_layers": True})}, LocalLambdaContext())
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("layers", body)
        self.assertIn("heat_priority_demand_cells", body["layers"])

    def test_lambda_handler_rejects_malformed_requests(self):
        invalid_bodies = [[], "not an object", None, {"threshold_m": 350}, {"excluded_candidate_ids": "candidate_019"}, {"excluded_candidate_ids": ["not-a-candidate"]}, {"include_layers": "yes"}]
        for invalid_body in invalid_bodies:
            with self.subTest(invalid_body=invalid_body):
                response = handler({"body": json.dumps(invalid_body)}, LocalLambdaContext())
                self.assertEqual(response["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
