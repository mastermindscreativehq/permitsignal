"""
PermitSignal Deterministic Pricing Engine

The AI never invents prices — this module computes them.

The LLM outputs pricing_inputs (service_level, project_value_low/high,
stakeholder_complexity, documentation_complexity, friction_score, has_denial,
has_hearing). This engine determines fee_low, fee_high, recommended_fee,
and deposit_percent.

Government fees are separate (not included).
Third-party professional fees are separate unless explicitly scoped.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

__all__ = [
    "calculate_pricing",
    "apply_pricing_to_opportunity",
    "SERVICE_TIERS",
    "STAKEHOLDER_MULTIPLIERS",
    "DOCUMENTATION_MULTIPLIERS",
    "FRICTION_MULTIPLIERS",
    "DENIAL_MULTIPLIER",
    "HEARING_MULTIPLIER",
]

# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

SERVICE_TIERS: Dict[str, Dict[str, Any]] = {
    "MONITORING": {
        "label": "Monitoring",
        "fee_low": 150.0,
        "fee_high": 300.0,
        "deposit_percent": 50,
    },
    "APPROVAL DIAGNOSTIC": {
        "label": "Approval Diagnostic",
        "fee_low": 500.0,
        "fee_high": 1500.0,
        "deposit_percent": 50,
    },
    "APPROVAL ASSISTANCE": {
        "label": "Approval Assistance",
        "fee_low": 2000.0,
        "fee_high": 5000.0,
        "deposit_percent": 33,
    },
    "PROJECT SUPPORT": {
        "label": "Project Support",
        "fee_low": 2000.0,
        "fee_high": 5000.0,
        "deposit_percent": 33,
    },
    "APPROVAL STRATEGY": {
        "label": "Approval Strategy",
        "fee_low": 5000.0,
        "fee_high": 15000.0,
        "deposit_percent": 25,
    },
}

# Canonical aliases that map input strings to tier keys
_TIER_ALIASES: Dict[str, str] = {
    "MONITORING": "MONITORING",
    "MONITOR": "MONITORING",
    "APPROVAL DIAGNOSTIC": "APPROVAL DIAGNOSTIC",
    "DIAGNOSTIC": "APPROVAL DIAGNOSTIC",
    "RISK ASSESSMENT": "APPROVAL DIAGNOSTIC",
    "APPROVAL ASSISTANCE": "APPROVAL ASSISTANCE",
    "ASSISTANCE": "APPROVAL ASSISTANCE",
    "PROJECT SUPPORT": "PROJECT SUPPORT",
    "SUPPORT": "PROJECT SUPPORT",
    "APPLICATION REVIEW": "APPROVAL ASSISTANCE",
    "HEARING PREP": "APPROVAL ASSISTANCE",
    "APPROVAL STRATEGY": "APPROVAL STRATEGY",
    "STRATEGY": "APPROVAL STRATEGY",
    "DENIAL RESPONSE": "APPROVAL STRATEGY",
    "FULL STRATEGY": "APPROVAL STRATEGY",
    "STAFF ENGAGEMENT": "APPROVAL STRATEGY",
}

# ---------------------------------------------------------------------------
# Complexity multipliers
# ---------------------------------------------------------------------------

STAKEHOLDER_MULTIPLIERS: Dict[str, float] = {
    "low": 1.0,
    "medium": 1.2,
    "high": 1.5,
}

DOCUMENTATION_MULTIPLIERS: Dict[str, float] = {
    "low": 1.0,
    "medium": 1.2,
    "high": 1.5,
}

FRICTION_MULTIPLIERS: Dict[str, tuple] = [
    # (upper_bound, multiplier)  — checked in order; first match wins
    (0, 1.0),
    (39, 1.1),
    (69, 1.3),
    (float("inf"), 1.5),
]

DENIAL_MULTIPLIER: float = 1.5
HEARING_MULTIPLIER: float = 1.1

# Minimum recommended fee (floor)
_MIN_RECOMMENDED_FEE: float = 75.0

# Valid service level strings for validation
_VALID_SERVICE_LEVELS: List[str] = list(_TIER_ALIASES.keys())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_tier(service_level: str) -> Dict[str, Any]:
    """Resolve a free-form service level string to a canonical tier dict.

    Raises ``ValueError`` if the service level cannot be recognised.
    """
    normalised = service_level.strip().upper()
    key = _TIER_ALIASES.get(normalised)
    if key is None:
        raise ValueError(
            f"Unrecognised service_level: {service_level!r}. "
            f"Valid values: {sorted(set(_TIER_ALIASES.values()))}"
        )
    return SERVICE_TIERS[key]


def _resolve_tier_key(service_level: str) -> str:
    """Return the canonical tier key string for a given service level."""
    normalised = service_level.strip().upper()
    key = _TIER_ALIASES.get(normalised)
    if key is None:
        raise ValueError(
            f"Unrecognised service_level: {service_level!r}. "
            f"Valid values: {sorted(set(_TIER_ALIASES.values()))}"
        )
    return key


def _friction_multiplier(friction_score: int | float) -> float:
    """Return the multiplier for a given friction score."""
    score = max(0, int(friction_score))
    for upper, mult in FRICTION_MULTIPLIERS:
        if score <= upper:
            return mult
    # Should never reach here because of inf sentinel, but guard anyway
    return FRICTION_MULTIPLIERS[-1][1]


def _complexity_label(value: Any) -> str:
    """Normalise a complexity value to a lowercase label."""
    if isinstance(value, str):
        v = value.strip().lower()
    else:
        v = str(value).strip().lower()
    if v in ("low", "1", "l"):
        return "low"
    if v in ("medium", "med", "m", "2"):
        return "medium"
    if v in ("high", "h", "3"):
        return "high"
    # Default to medium if ambiguous
    return "medium"


def _round_fee(value: float) -> float:
    """Round a fee to the nearest whole dollar."""
    return float(round(value))


def _build_rationale(
    tier_key: str,
    base_low: float,
    base_high: float,
    stakeholder_mult: float,
    documentation_mult: float,
    friction_mult: float,
    denial_mult: float,
    hearing_mult: float,
    project_value_low: Optional[float],
    project_value_high: Optional[float],
    final_low: float,
    final_high: float,
    recommended: float,
    deposit_percent: int,
    deposit_amount: float,
) -> List[str]:
    """Build a human-readable pricing rationale."""
    parts: List[str] = []

    tier_label = SERVICE_TIERS[tier_key]["label"]
    parts.append(f"Service tier: {tier_label}")

    parts.append(
        f"Base fee range: ${_round_fee(base_low):,.0f} – ${_round_fee(base_high):,.0f}"
    )

    multipliers_applied: List[str] = []
    if stakeholder_mult != 1.0:
        multipliers_applied.append(f"stakeholder {stakeholder_mult:.1f}x")
    if documentation_mult != 1.0:
        multipliers_applied.append(f"documentation {documentation_mult:.1f}x")
    if friction_mult != 1.0:
        multipliers_applied.append(f"friction {friction_mult:.1f}x")
    if denial_mult != 1.0:
        multipliers_applied.append(f"denial {denial_mult:.1f}x")
    if hearing_mult != 1.0:
        multipliers_applied.append(f"hearing {hearing_mult:.1f}x")

    if multipliers_applied:
        parts.append("Complexity multipliers applied: " + ", ".join(multipliers_applied))
    else:
        parts.append("No complexity multipliers applied")

    if project_value_low is not None and project_value_high is not None:
        parts.append(
            f"Project value range: ${project_value_low:,.0f} – ${project_value_high:,.0f}"
        )

    parts.append(
        f"Final fee range: ${_round_fee(final_low):,.0f} – ${_round_fee(final_high):,.0f}"
    )
    parts.append(f"Recommended fee: ${_round_fee(recommended):,.0f}")
    parts.append(f"Deposit: {deposit_percent}% (${_round_fee(deposit_amount):,.0f})")

    return parts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_pricing(pricing_inputs: dict) -> dict:
    """Calculate pricing from LLM-produced pricing inputs.

    Parameters
    ----------
    pricing_inputs : dict
        Must contain at least ``service_level``.  Recognised keys:

        - ``service_level`` (str) — one of the known tiers (required)
        - ``project_value_low`` (float|None) — low estimate of project value
        - ``project_value_high`` (float|None) — high estimate of project value
        - ``stakeholder_complexity`` (str) — "low" | "medium" | "high"
        - ``documentation_complexity`` (str) — "low" | "medium" | "high"
        - ``friction_score`` (int|float) — 0-100 friction score
        - ``has_denial`` (bool) — whether the project has a prior denial
        - ``has_hearing`` (bool) — whether a public hearing is required

    Returns
    -------
    dict
        ``fee_low``, ``fee_high``, ``recommended_fee``, ``deposit_percent``,
        ``deposit_amount``, ``pricing_rationale`` (list of str).
    """
    service_level = pricing_inputs.get("service_level", "")
    if not service_level:
        raise ValueError("pricing_inputs must include a non-empty 'service_level'")

    tier = _resolve_tier(service_level)
    tier_key = _resolve_tier_key(service_level)

    base_low = tier["fee_low"]
    base_high = tier["fee_high"]
    deposit_percent = tier["deposit_percent"]

    project_value_low = pricing_inputs.get("project_value_low")
    project_value_high = pricing_inputs.get("project_value_high")

    stakeholder_complexity = _complexity_label(
        pricing_inputs.get("stakeholder_complexity", "medium")
    )
    documentation_complexity = _complexity_label(
        pricing_inputs.get("documentation_complexity", "medium")
    )
    friction_score = int(pricing_inputs.get("friction_score", 0))
    has_denial = bool(pricing_inputs.get("has_denial", False))
    has_hearing = bool(pricing_inputs.get("has_hearing", False))

    stakeholder_mult = STAKEHOLDER_MULTIPLIERS[stakeholder_complexity]
    documentation_mult = DOCUMENTATION_MULTIPLIERS[documentation_complexity]
    friction_mult = _friction_multiplier(friction_score)
    denial_mult = DENIAL_MULTIPLIER if has_denial else 1.0
    hearing_mult = HEARING_MULTIPLIER if has_hearing else 1.0

    combined_mult = (
        stakeholder_mult
        * documentation_mult
        * friction_mult
        * denial_mult
        * hearing_mult
    )

    fee_low = _round_fee(base_low * combined_mult)
    fee_high = _round_fee(base_high * combined_mult)

    # Recommended fee is the midpoint of the adjusted range, floored at minimum
    recommended_fee = _round_fee(max((fee_low + fee_high) / 2.0, _MIN_RECOMMENDED_FEE))
    # Also ensure recommended is at least fee_low
    recommended_fee = max(recommended_fee, fee_low)

    deposit_amount = _round_fee(recommended_fee * deposit_percent / 100.0)

    rationale = _build_rationale(
        tier_key=tier_key,
        base_low=base_low,
        base_high=base_high,
        stakeholder_mult=stakeholder_mult,
        documentation_mult=documentation_mult,
        friction_mult=friction_mult,
        denial_mult=denial_mult,
        hearing_mult=hearing_mult,
        project_value_low=project_value_low,
        project_value_high=project_value_high,
        final_low=fee_low,
        final_high=fee_high,
        recommended=recommended_fee,
        deposit_percent=deposit_percent,
        deposit_amount=deposit_amount,
    )

    return {
        "fee_low": fee_low,
        "fee_high": fee_high,
        "recommended_fee": recommended_fee,
        "deposit_percent": deposit_percent,
        "deposit_amount": deposit_amount,
        "pricing_rationale": rationale,
    }


def apply_pricing_to_opportunity(opportunity: dict) -> dict:
    """Merge computed pricing fields onto an opportunity/lead record.

    The opportunity dict is expected to contain a ``pricing_inputs`` key with
    the data needed by :func:`calculate_pricing`.  If ``pricing_inputs`` is
    missing or empty the opportunity is returned unchanged (with a note in
    ``pricing_status``).

    Returns a new dict — the original is not mutated.
    """
    result = dict(opportunity)

    pricing_inputs = result.get("pricing_inputs")
    if not pricing_inputs or not isinstance(pricing_inputs, dict):
        result["pricing_status"] = "no_pricing_inputs"
        return result

    try:
        pricing = calculate_pricing(pricing_inputs)
    except (ValueError, KeyError, TypeError) as exc:
        result["pricing_status"] = f"error: {exc}"
        return result

    result["fee_low"] = pricing["fee_low"]
    result["fee_high"] = pricing["fee_high"]
    result["recommended_fee"] = pricing["recommended_fee"]
    result["deposit_percent"] = pricing["deposit_percent"]
    result["deposit_amount"] = pricing["deposit_amount"]
    result["pricing_rationale"] = pricing["pricing_rationale"]
    result["pricing_status"] = "computed"

    return result
