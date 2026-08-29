"""
LLM Decision-Explanation Layer, with guardrails (was notebook Section 9 (Texas pilot),
Cell 15 - "LLM Decision-Explanation Layer").

Turns the deterministic risk_table + critical_zones + optimizer's recommended
plan (backend/risk_engine.py and backend/optimization.py) into a
natural-language "why" explanation, using Groq's free-tier hosted inference
(an OpenAI-compatible chat API). This layer never computes or changes a risk
score or an optimization decision - it only explains a result that already
exists.

Every response is validated (see validate_explanation below) before being
returned: a self-attribution check (rejects phrasing implying the LLM
computed the score or made the funding decision) and a numeric-grounding
check (rejects any number-like figure that doesn't trace back to a real
value in the evidence packet). A failed check triggers one retry with the
failure reason appended, then falls back to a template built from the same
evidence if it fails again - never an ungrounded explanation, never a broken
dashboard.

Deployment note: unlike the Colab notebook (which read GROQ_API_KEY from
Colab Secrets via google.colab.userdata), this module reads it from the
environment / a local .env file (see backend/config.py and .env.example).
If no key is configured, get_groq_client() returns None and explain_zone/
explain_plan degrade straight to their evidence-based template - the
dashboard still renders, it just skips the LLM explanation.
"""
import json
import re

import pandas as pd

from backend.config import EXPLANATION_MODEL, GROQ_API_KEY

try:
    from groq import Groq
except ImportError:  # pragma: no cover - groq is in requirements.txt
    Groq = None


def get_groq_client():
    """Returns a Groq client if GROQ_API_KEY is configured (env var or
    .env file), else None. Callers must handle a None client by skipping
    the LLM call and falling back to the evidence-based template - see
    explain_zone/explain_plan below, both of which already do this."""
    if not GROQ_API_KEY or Groq is None:
        return None
    return Groq(api_key=GROQ_API_KEY)


def build_zone_evidence(zone_id: str, risk_table: pd.DataFrame, lines_joined: pd.DataFrame,
                         battery_joined: pd.DataFrame) -> dict:
    """Assemble the JSON 'evidence packet' for one zone - scores plus the real
    spatial assets already joined onto it (backend/graph.py). This dict is
    the ONLY input the LLM ever sees for a zone; it never has access to raw
    source data, the scoring formula, or the optimizer's code."""
    row = risk_table.loc[risk_table["zone_id"] == zone_id].iloc[0]

    n_lines = int((lines_joined["zone_id"] == zone_id).sum()) if lines_joined is not None else 0

    n_batteries = 0
    if battery_joined is not None and not battery_joined.empty:
        match = battery_joined.loc[battery_joined["zone_id"] == zone_id]
        if not match.empty:
            n_batteries = int(match["n_battery_sites"].iloc[0])

    return {
        "zone_id": zone_id,
        "grid_heat_risk": round(float(row["grid_heat_risk"]), 2),
        "heat_score": round(float(row["heat_score"]), 1),
        "demand_score": round(float(row["demand_score"]), 1),
        "infra_score": round(float(row["infra_score"]), 1),
        "outage_score": round(float(row["outage_score"]), 1),
        "vulnerability_score": round(float(row["vuln_score"]), 1),
        "nearby_transmission_lines": n_lines,
        "nearby_battery_sites": n_batteries,
    }


# ============ Guardrails ============

FORBIDDEN_SELF_ATTRIBUTION_PATTERNS = [
    r"\bi calculated\b", r"\bi computed\b", r"\bi determined the risk\b",
    r"\bi decided\b", r"\bmy calculation\b", r"\bi selected the\b",
    r"\bi chose the action\b", r"\bi optimized\b", r"\bi ran the optimization\b",
    r"\bi assigned the score\b", r"\bi ran the model\b", r"\bi allocated\b",
]


def _flatten_numeric_values(obj) -> list:
    """Recursively pull every int/float leaf out of a dict/list structure -
    handles both the flat zone-evidence dict and the nested plan payload
    (which has a list of {zone_id, action, cost, value} dicts inside it)."""
    values = []
    if isinstance(obj, dict):
        for v in obj.values():
            values.extend(_flatten_numeric_values(v))
    elif isinstance(obj, list):
        for v in obj:
            values.extend(_flatten_numeric_values(v))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        values.append(float(obj))
    return values


def _extract_candidate_numbers(text: str) -> list:
    """Numbers worth grounding-checking: anything with a decimal point, a
    dollar sign, a K/M suffix, or a bare value >= 10. Bare small integers
    (2, 3, 4, 5...) are almost always sentence structure ("the five
    components", "3-5 sentences") rather than a claimed score or dollar
    figure, and checking those causes constant false positives without
    catching real hallucination. K/M suffixes ("50K", "1.2M") are expanded
    to their full value before comparison - otherwise "$50K" for a real
    $50,000 evidence figure gets parsed as the bare number 50 and wrongly
    flagged as ungrounded. The leading negative lookbehind blocks matches
    starting mid-token - without it, a zone ID like "Z00010" gets its
    digit run misread as the standalone number 10 (or 0010 -> 10), which
    is never in the evidence and would be wrongly flagged as hallucinated."""
    matches = re.findall(r"(?<![A-Za-z0-9])\$?\d[\d,]*\.?\d*\s?[kKmM]?\b", text)
    numbers = []
    for m in matches:
        m = m.strip()
        multiplier = 1
        if m and m[-1] in "kK":
            multiplier = 1_000
            m = m[:-1].strip()
        elif m and m[-1] in "mM":
            multiplier = 1_000_000
            m = m[:-1].strip()
        cleaned = m.replace("$", "").replace(",", "")
        try:
            value = float(cleaned) * multiplier
        except ValueError:
            continue
        if multiplier > 1 or "." in cleaned or m.startswith("$") or value >= 10:
            numbers.append(value)
    return numbers


def _is_grounded(value: float, evidence_numbers: list, rel_tol: float = 0.02, abs_tol: float = 0.6) -> bool:
    return any(abs(value - ev) <= max(abs_tol, abs(ev) * rel_tol) for ev in evidence_numbers)


def validate_explanation(text: str, evidence: dict) -> tuple:
    """Returns (is_valid, reason). Three checks: no markdown formatting (the
    UI renders this as plain text, so literal "**bold**" markers would show
    up as raw asterisks), no self-attribution language implying the LLM
    computed a score or made the funding decision, and every number-like
    figure mentioned traces back to a real value in the evidence packet the
    LLM was actually given."""
    if re.search(r"\*\*|__|^#{1,6}\s|^[-*]\s", text, re.MULTILINE):
        return False, "response contains markdown formatting (bold/headers/bullets)"

    lowered = text.lower()
    for pattern in FORBIDDEN_SELF_ATTRIBUTION_PATTERNS:
        if re.search(pattern, lowered):
            return False, f"forbidden self-attribution phrase matched ('{pattern}')"

    evidence_numbers = _flatten_numeric_values(evidence)
    for value in _extract_candidate_numbers(text):
        if not _is_grounded(value, evidence_numbers):
            return False, f"ungrounded number in explanation: {value}"

    return True, "ok"


def _call_llm(client, system_prompt: str, payload: dict, correction: str = None,
              model: str = EXPLANATION_MODEL, max_tokens: int = 600) -> str:
    """openai/gpt-oss-120b (the current EXPLANATION_MODEL) is a REASONING
    model on Groq - by default (reasoning_effort="medium") it spends part
    of max_tokens on a hidden chain-of-thought before writing the actual
    answer. With a low max_tokens budget (e.g. 300/350), the reasoning
    alone can consume the whole budget, leaving the final answer truncated
    to a few words or empty. reasoning_effort="low" keeps that internal
    reasoning minimal, and max_tokens is set generously above what a 2-5
    sentence answer needs, so there's still room left for the actual
    explanation even if some reasoning tokens are spent."""
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload)}]
    if correction:
        messages.append({"role": "user", "content": correction})
    response = client.chat.completions.create(
        model=model, max_tokens=max_tokens, reasoning_effort="low", messages=messages,
    )
    text = response.choices[0].message.content
    if not text or not text.strip():
        raise ValueError("Empty response from LLM (likely reasoning tokens consumed the "
                          "whole max_tokens budget before any answer text was written)")
    return text


ZONE_SYSTEM_PROMPT = """You are explaining the output of a deterministic grid-\
heat risk model to a non-technical stakeholder. You are given a JSON evidence \
packet for one zone (its risk score, its five component scores 0-100, and the \
real grid assets nearby). Write 2-4 plain-language sentences on why this zone \
was flagged, grounded ONLY in the numbers given. Do not invent data, do not \
state a precise cause-and-effect the numbers don't fully support, and do not \
imply you performed any calculation yourself - the scores were computed by a \
separate deterministic engine before you saw them. If a component score is 0 \
or notably low, say so plainly rather than guessing at a reason. Do not \
compute or state any new number that isn't already in the JSON (no averages, \
percentages, sums, or rounded-off shorthand like "50K") - reference the given \
figures directly, in full digit form. Write in plain text only - no markdown \
(no **bold**, no *italics*, no bullet points, no headers). Put each sentence \
on its own line, with a blank line between sentences, so the answer reads as \
short standalone lines rather than one dense paragraph."""


def explain_zone(client, evidence: dict, model: str = EXPLANATION_MODEL, max_attempts: int = 2) -> str:
    if client is None:
        return _zone_template(evidence, reason="no LLM client configured (GROQ_API_KEY not set)")

    correction = None
    for attempt in range(1, max_attempts + 1):
        try:
            text = _call_llm(client, ZONE_SYSTEM_PROMPT, evidence, correction, model, max_tokens=500)
        except Exception as e:
            print(f"[guardrail] zone explanation attempt {attempt} call failed: {e.__class__.__name__}: {e}")
            break
        is_valid, reason = validate_explanation(text, evidence)
        if is_valid:
            return text
        print(f"[guardrail] zone explanation attempt {attempt} rejected: {reason}")
        print(f"[guardrail] rejected text was: {text!r}")
        correction = (f"Your previous answer was rejected: {reason}. Rewrite it using ONLY "
                      f"the numbers already in the evidence JSON above (in full digit form, "
                      f"no rounding, no shorthand like '50K', no new averages or percentages), "
                      f"and do not claim you performed any calculation or made any decision yourself.")

    # Never let a dashboard render fail because the LLM call or guardrail did -
    # degrade to a template built from the same evidence packet.
    return _zone_template(evidence, reason="LLM explanation unavailable after guardrail checks")


def _zone_template(evidence: dict, reason: str) -> str:
    return (
        f"Zone {evidence['zone_id']} scored {evidence['grid_heat_risk']} on the "
        f"grid heat risk scale (heat {evidence['heat_score']}, demand "
        f"{evidence['demand_score']}, infrastructure {evidence['infra_score']}, "
        f"outage history {evidence['outage_score']}, vulnerability "
        f"{evidence['vulnerability_score']}), with {evidence['nearby_transmission_lines']} "
        f"transmission line(s) and {evidence['nearby_battery_sites']} battery site(s) nearby.\n"
        f"[{reason} - showing evidence-based summary instead.]"
    )


PLAN_SYSTEM_PROMPT = """You are explaining a resource-allocation plan chosen \
by an exact 0/1 knapsack optimizer, not by you. You are given the optimizer's \
selected (zone, action) pairs, their MODELED costs and risk-reduction values, \
and the total budget. Explain in 3-5 plain-language sentences why this \
combination was selected, in terms of maximizing total modeled risk-reduction \
under the budget constraint. Explicitly state that action costs and risk-\
reduction percentages are modeling assumptions for this demonstration, not \
empirically validated operational figures. Do not claim any selection method \
other than exact optimization under the stated budget, and do not take credit \
for making the selection yourself - you are explaining a decision that was \
already made mathematically before you saw it. Do not compute or state any \
new number that isn't already in the JSON (no averages across actions, no \
percentages of the budget, no rounded-off shorthand like "50K") - reference \
the given dollar and value figures directly, in full digit form (e.g. "$50,000", \
not "$50K" or "50 grand"). Write in plain text only - no markdown (no **bold**, \
no *italics*, no bullet points, no headers). Put each sentence on its own \
line, with a blank line between sentences, so the answer reads as short \
standalone lines rather than one dense paragraph."""


def explain_plan(client, plan_df: pd.DataFrame, total_cost: float, total_value: float,
                  budget: int, model: str = EXPLANATION_MODEL, max_attempts: int = 2) -> str:
    payload = {
        "budget": budget,
        "total_cost": total_cost,
        "total_modeled_risk_reduction_value": round(total_value, 2),
        "selected_actions": plan_df.to_dict(orient="records"),
    }

    if client is None:
        return _plan_template(plan_df, total_cost, total_value, budget,
                               reason="no LLM client configured (GROQ_API_KEY not set)")

    correction = None
    for attempt in range(1, max_attempts + 1):
        try:
            text = _call_llm(client, PLAN_SYSTEM_PROMPT, payload, correction, model, max_tokens=600)
        except Exception as e:
            print(f"[guardrail] plan explanation attempt {attempt} call failed: {e.__class__.__name__}: {e}")
            break
        is_valid, reason = validate_explanation(text, payload)
        if is_valid:
            return text
        print(f"[guardrail] plan explanation attempt {attempt} rejected: {reason}")
        print(f"[guardrail] rejected text was: {text!r}")
        correction = (f"Your previous answer was rejected: {reason}. Rewrite it using ONLY "
                      f"the numbers already in the JSON above (in full digit form, no rounding, "
                      f"no shorthand like '50K', no new averages or percentages), and do not "
                      f"claim you performed any calculation or made the selection yourself.")

    return _plan_template(plan_df, total_cost, total_value, budget,
                           reason="LLM explanation unavailable after guardrail checks")


def _plan_template(plan_df: pd.DataFrame, total_cost: float, total_value: float,
                    budget: int, reason: str) -> str:
    return (
        f"Under a ${budget:,} budget, the optimizer selected {len(plan_df)} "
        f"action(s) totaling ${total_cost:,.0f}, for a modeled risk-reduction "
        f"value of {total_value:.2f}. Action costs and risk-reduction percentages "
        f"are modeling assumptions, not empirically validated figures.\n"
        f"[{reason} - showing evidence-based summary instead.]"
    )
