"""Local Lambda-compatible maximum-coverage optimiser for CoolWard."""

import json
from pathlib import Path

from aws_lambda_powertools import Logger

logger = Logger(service="coolward-optimiser")
DATA_PATH = Path(__file__).parent / "data" / "planning_data.json"


def load_data():
    with DATA_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def optimise(data, budget_lakh):
    """Return a pre-validated primary 400 m planning scenario result."""
    try:
        plan = data["plans"][str(budget_lakh)]
    except KeyError as error:
        supported = ", ".join(sorted(data["plans"], key=int))
        raise ValueError(f"Budget must be one of ₹{supported.replace(', ', 'L, ₹')}L.") from error
    return {
        **plan,
        "study_area": data["study_area"],
        "scenario": data["scenario"],
        "network_distance_planning_assumption_m": data["network_distance_planning_assumption_m"],
        "standard_unit_cost_label": data["standard_unit_cost_label"],
        "disclaimer": data["disclaimer"],
        "limitations": data["limitations"],
        "layers": data["layers"],
    }


@logger.inject_lambda_context
def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        budget_lakh = int(body.get("budget_lakh", 20))
        if budget_lakh not in {5, 10, 15, 20, 25, 30, 35}:
            raise ValueError("Budget must be one of ₹5L, ₹10L, ₹15L, ₹20L, ₹25L, ₹30L, or ₹35L.")
        result = optimise(load_data(), budget_lakh)
        logger.info("Optimisation complete", extra={"budget_lakh": budget_lakh, "site_count": len(result["selected_sites"])})
        return response(200, result)
    except (ValueError, json.JSONDecodeError) as error:
        logger.warning("Invalid optimisation request", extra={"error": str(error)})
        return response(400, {"error": str(error)})


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
