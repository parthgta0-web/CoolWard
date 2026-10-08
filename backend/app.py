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
    """Choose sites greedily by newly covered heat-priority score per lakh."""
    cells = {cell["id"]: cell for cell in data["cells"]}
    covered = {cell["id"] for cell in data["cells"] if cell["covered_now"]}
    selected = []
    spent = 0
    remaining = list(data["sites"])

    while remaining:
        viable = [site for site in remaining if spent + site["cost_lakh"] <= budget_lakh]
        if not viable:
            break

        def value(site):
            new_score = sum(cells[cell_id]["priority"] for cell_id in site["covers"] if cell_id not in covered)
            return new_score / site["cost_lakh"]

        best = max(viable, key=value)
        gain = sum(cells[cell_id]["priority"] for cell_id in best["covers"] if cell_id not in covered)
        if gain == 0:
            break
        selected.append({**best, "new_priority_covered": gain})
        covered.update(best["covers"])
        spent += best["cost_lakh"]
        remaining.remove(best)

    total_priority = sum(cell["priority"] for cell in data["cells"])
    baseline_priority = sum(cell["priority"] for cell in data["cells"] if cell["covered_now"])
    return {
        "budget_lakh": budget_lakh,
        "spent_lakh": spent,
        "selected_sites": selected,
        "baseline_coverage_percent": round(100 * baseline_priority / total_priority, 1),
        "after_coverage_percent": round(100 * sum(cells[cell_id]["priority"] for cell_id in covered) / total_priority, 1),
        "new_priority_covered": sum(site["new_priority_covered"] for site in selected),
        "study_area": data["study_area"],
        "disclaimer": data["disclaimer"],
    }


@logger.inject_lambda_context
def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        budget_lakh = int(body.get("budget_lakh", 20))
        if budget_lakh < 5 or budget_lakh > 50:
            raise ValueError("Budget must be between ₹5 lakh and ₹50 lakh.")
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
