"""
Constrained-budget resilience planner - was notebook Section 8 (Texas pilot).

Exact 0/1 knapsack via dynamic programming, not a greedy value/cost-ratio
heuristic - greedy isn't guaranteed optimal for 0/1 knapsack.

NOTE: the dollar costs and risk-reduction percentages in ACTIONS
(backend/config.py) are scenario assumptions used to demonstrate
constrained optimization, not utility-specific cost estimates or
empirically calibrated intervention effects. Surface this disclaimer
wherever a plan from this module is displayed (see frontend/app.py).
"""
from dataclasses import dataclass

import pandas as pd

from backend.config import ACTIONS


@dataclass
class ZoneActionOption:
    zone_id: str
    action: str
    cost: int
    value: float


def build_candidate_options(critical_zones: pd.DataFrame, battery_joined: pd.DataFrame) -> list[ZoneActionOption]:
    battery_zones = set(
        battery_joined.loc[battery_joined.get("n_battery_sites", 0) > 0, "zone_id"]
    ) if battery_joined is not None and not battery_joined.empty else set()

    options = []
    for _, row in critical_zones.iterrows():
        zone_id, zone_risk = row["zone_id"], row["grid_heat_risk"]
        for action_name, spec in ACTIONS.items():
            if spec["requires_battery"] and zone_id not in battery_zones:
                continue
            options.append(ZoneActionOption(
                zone_id=zone_id, action=action_name, cost=spec["cost"],
                value=spec["risk_reduction_pct"] * zone_risk / 100.0,
            ))
    return options


def optimize_plan(options: list[ZoneActionOption], budget: int) -> dict:
    n = len(options)
    dp = [[0.0] * (budget + 1) for _ in range(n + 1)]
    for i, opt in enumerate(options, start=1):
        for b in range(budget + 1):
            dp[i][b] = dp[i - 1][b]
            if opt.cost <= b:
                candidate = dp[i - 1][b - opt.cost] + opt.value
                if candidate > dp[i][b]:
                    dp[i][b] = candidate

    selected, b = [], budget
    for i in range(n, 0, -1):
        if dp[i][b] != dp[i - 1][b]:
            opt = options[i - 1]
            selected.append(opt)
            b -= opt.cost

    return {"selected": selected, "total_cost": sum(o.cost for o in selected),
            "total_value": dp[n][budget], "budget": budget}


def summarize_plan(result: dict) -> pd.DataFrame:
    rows = [{"zone_id": o.zone_id, "action": o.action, "cost": o.cost, "value": round(o.value, 2)}
            for o in result["selected"]]
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["zone_id", "action", "cost", "value"])
    return df.sort_values(["zone_id", "action"]).reset_index(drop=True)


def what_if_scenarios(critical_zones: pd.DataFrame, battery_joined: pd.DataFrame, budgets: list[int]) -> pd.DataFrame:
    options = build_candidate_options(critical_zones, battery_joined)
    baseline_risk = critical_zones["grid_heat_risk"].sum()
    rows = [{"budget": 0, "risk_reduction_achieved": 0.0, "risk_reduction_pct_of_baseline": 0.0, "n_actions": 0}]
    for budget in budgets:
        result = optimize_plan(options, budget)
        rows.append({
            "budget": budget, "risk_reduction_achieved": round(result["total_value"], 2),
            "risk_reduction_pct_of_baseline": round(result["total_value"] / baseline_risk * 100, 1) if baseline_risk else 0.0,
            "n_actions": len(result["selected"]),
        })
    return pd.DataFrame(rows)
