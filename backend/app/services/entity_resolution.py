"""
Entity Resolution — evidence-based multi-signal candidate matching.

Purpose
-------
Decide whether a discovered public-web candidate (search result, LinkedIn
profile, directory listing, registry record) actually refers to the same
real-world entity already modeled for a case.

Hard rules
----------
- A candidate is NEVER matched to a person solely because the names are
  identical. Name overlap alone caps the match at "unverified".
- "verified" requires the government record itself, or at least two
  independent corroborating signal categories (location, organization,
  property, case reference, role, domain, contact).
- Conflicting evidence (e.g. a clearly different organization tied to the
  candidate) downgrades the match to "ambiguous".
- Ties between distinct plausible candidates produce "ambiguous" rather
  than a silent arbitrary pick.

Every result carries: match_status, match_confidence, match_reasons,
matched/conflicting signals, and the source reference.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from backend.app.services.entity_intelligence import (
    CANDIDATE_KINDS,
    MATCH_STATUSES,
    EntityMatch,
    EntityRecord,
    SourceRef,
    classify_source,
    normalize_org_name,
    normalize_person_name,
)

_NAME_STOP_TOKENS = {
    "llc", "inc", "corp", "ltd", "lc", "lp", "plc", "pc", "pllc",
    "company", "holdings", "group", "the", "and", "of",
}

# Tokens too generic to act as identity corroboration anywhere.
_LOCATION_NOISE = {"city", "county", "state", "north", "south", "east", "west"}

_ROLE_KEYWORDS = (
    "owner", "principal", "president", "ceo", "founder", "partner",
    "developer", "architect", "engineer", "attorney", "agent", "manager",
    "director", "contractor", "realtor", "broker",
)


def _tokens(name: Optional[str]) -> set[str]:
    return {
        t for t in normalize_person_name(name).split()
        if len(t) > 1 and t not in _NAME_STOP_TOKENS
    }


def _org_tokens(name: Optional[str]) -> set[str]:
    normalized = normalize_org_name(name)
    return {t for t in normalized.split() if len(t) > 2}


def _name_similarity(entity_name: str, candidate_name: Optional[str]) -> float:
    """Token-Jaccard similarity with an exact-normalized-match shortcut."""
    a = _tokens(entity_name)
    b = _tokens(candidate_name or "")
    if not a or not b:
        return 0.0
    if normalize_person_name(entity_name) == normalize_person_name(candidate_name):
        return 1.0
    overlap = a & b
    if not overlap:
        return 0.0
    jaccard = len(overlap) / len(a | b)
    # A candidate whose *title* contains the full ordered name is stronger.
    joined = " ".join(sorted(a))
    cand_joined = " ".join(sorted(b))
    if a <= b or joined in cand_joined:
        return max(jaccard, 0.85)
    return jaccard


def _text_has_all(text: str, tokens: set[str]) -> bool:
    lowered = text.lower()
    return all(t in lowered for t in tokens) if tokens else False


def _text_token_hits(text: str, tokens: set[str]) -> int:
    lowered = text.lower()
    return sum(1 for t in tokens if t in lowered)


def score_candidate(
    entity: EntityRecord,
    candidate: dict[str, Any],
) -> tuple[float, list[str], list[str], list[str]]:
    """
    Score one candidate against one entity.

    Returns (score, matched_signals, conflicting_signals, reasons).
    Signal names double as independent corroboration categories:
    'name', 'location', 'organization', 'property', 'case',
    'role', 'domain', 'contact'.
    """
    candidate_text = " ".join(
        str(candidate.get(k) or "")
        for k in ("name", "text", "url", "domain")
    ).lower()

    matched: list[str] = []
    conflicts: list[str] = []
    reasons: list[str] = []

    # --- name signal -------------------------------------------------
    sim = _name_similarity(
        entity.canonical_name, candidate.get("name") or ""
    )
    if sim <= 0.0:
        sim = min(_text_token_hits(candidate_text, _tokens(entity.canonical_name)) / max(len(_tokens(entity.canonical_name)), 1), 0.6)
    name_score = 0.0
    if sim >= 0.99:
        name_score = 0.45
        matched.append("name")
        reasons.append("Candidate title exactly matches the entity name")
    elif sim >= 0.60:
        name_score = 0.30
        matched.append("name")
        reasons.append("Candidate title substantially overlaps the entity name")
    elif sim > 0.0:
        name_score = round(0.15 * sim / 0.6, 3)
        if name_score >= 0.08:
            matched.append("name")
            reasons.append("Entity name tokens appear in candidate content")

    # --- location signal ---------------------------------------------
    location = str(entity.attributes.get("location") or "")
    location_tokens = {
        t for t in normalize_person_name(location).split()
        if len(t) > 3 and t not in _LOCATION_NOISE
    }
    if location_tokens and _text_token_hits(candidate_text, location_tokens):
        matched.append("location")
        reasons.append(f"Candidate references the entity location ({location})")

    # --- organization signal -----------------------------------------
    org_name = str(entity.attributes.get("organization") or entity.attributes.get("company_name") or "")
    org_toks = _org_tokens(org_name)
    if org_toks:
        hits = _text_token_hits(candidate_text, org_toks)
        if hits == len(org_toks):
            matched.append("organization")
            reasons.append(f"Candidate references the affiliated organization ({org_name})")

    # --- property/address signal --------------------------------------
    address = str(entity.attributes.get("address") or entity.attributes.get("project_address") or "")
    addr_tokens = {
        t for t in normalize_person_name(address).split() if len(t) > 2
    }
    if addr_tokens and _text_token_hits(candidate_text, addr_tokens) >= 2:
        matched.append("property")
        reasons.append("Candidate references the associated property address")

    # --- case/application reference signal ----------------------------
    app_number = str(entity.attributes.get("application_number") or "")
    if app_number and app_number.lower() in candidate_text:
        matched.append("case")
        reasons.append(f"Candidate explicitly cites case {app_number}")

    # --- professional role signal --------------------------------------
    role = str(entity.attributes.get("role") or "").lower()
    if role:
        first = role.split()[0] if role.split() else ""
        if first and re.search(rf"\b{re.escape(first)}\b", candidate_text):
            matched.append("role")
            reasons.append(f"Candidate mentions the entity role ({role})")
    elif not any(m in matched for m in ("organization", "case")):
        for kw in _ROLE_KEYWORDS:
            if re.search(rf"\b{kw}\b", candidate_text):
                break  # generic role words alone are not attached as a signal

    # --- website/domain signal -----------------------------------------
    website = str(entity.attributes.get("website") or entity.attributes.get("company_website") or "")
    website_domain = None
    m = re.search(r"(?:https?://)?([a-z0-9.-]+\.[a-z]{2,})", website.lower())
    if m:
        website_domain = m.group(1)
    candidate_domain = str(candidate.get("domain") or "").lower().removeprefix("www.")
    if (
        website_domain
        and candidate_domain
        and candidate_domain != "linkedin.com"
        and (candidate_domain == website_domain.removeprefix("www.")
             or candidate_domain.endswith("." + website_domain.removeprefix("www.")))
    ):
        matched.append("domain")
        reasons.append(f"Candidate is on the entity's own web domain ({website_domain})")

    # --- contact signal --------------------------------------------------
    for claim_key, label in (("email", "email"), ("phone", "phone")):
        claim_value = None
        for c in entity.attributes.get("claims", []):
            if c.get("claim") == claim_key and c.get("value"):
                claim_value = str(c["value"]).lower()
                break
        if claim_value and claim_value in candidate_text:
            matched.append("contact")
            reasons.append(f"Candidate repeats the entity's public {label}")

    # --- conflicting signals ----------------------------------------------
    entity_org = org_name.strip()
    if entity_type_is_person(entity) and entity_org:
        cand_org = str(candidate.get("organization") or "")
        if cand_org:
            etoks = _org_tokens(entity_org)
            ctoks = _org_tokens(cand_org)
            if etoks and ctoks and not (etoks & ctoks):
                conflicts.append("organization")
                reasons.append(
                    f"Candidate is tied to a different organization ({cand_org})"
                )

    score = name_score + 0.18 * sum(
        1 for s in matched if s != "name"
    )
    if "case" in matched:
        score += 0.10
    if "contact" in matched:
        score += 0.07
    if "domain" in matched:
        score += 0.10
    score = round(min(score, 1.0), 4)

    return score, matched, conflicts, reasons


def entity_type_is_person(entity: EntityRecord) -> bool:
    return entity.entity_type in ("person", "government_staff", "professional")


def decide_match_status(
    score: float,
    matched_signals: list[str],
    conflicting_signals: list[str],
    corroboration_categories: int,
    tied_candidates: int = 1,
    source_is_government: bool = False,
) -> str:
    """
    Map score + signals onto the match-status vocabulary.

    - Government-record backing verifies -- but only when the source
      actually names the entity; a government domain mentioning a
      different person never verifies an identity.
    - verified: high score AND >= 2 independent corroboration categories
      (or government record), no conflicts, single winner.
    - probable: moderate score with name plus >= 1 corroboration category;
      exact ties between multiple distinct candidates stay unresolved
      ("ambiguous") until one candidate clearly outranks the other.
    - ambiguous: conflicts, or several equally-plausible distinct candidates.
    - unverified: name-only (never promoted regardless of raw score).
    """
    if conflicting_signals:
        return "ambiguous"

    if source_is_government and "name" in (matched_signals or []):
        return "verified"

    name_only = [s for s in matched_signals if s != "name"] == []
    if name_only:
        return "unverified"

    if score >= 0.75 and corroboration_categories >= 2 and tied_candidates <= 1:
        return "verified"

    if score >= 0.45 and corroboration_categories >= 1:
        if tied_candidates > 1:
            return "ambiguous"
        return "probable"

    if tied_candidates > 1 and score >= 0.30:
        return "ambiguous"

    return "unverified"


def _sig_tokens(value: Any) -> frozenset:
    """Lowercased alphanumeric token signature of a free-text value."""
    import re as _re
    if not value:
        return frozenset()
    return frozenset(_re.findall(r"[a-z0-9]+", str(value).lower()))


def _candidates_equivalent(a: dict, b: dict) -> bool:
    """
    True when two tied candidates are actually the SAME identity described
    twice (identical corroborating signals and content), rather than two
    different people/organizations that happen to score alike.
    """
    if sorted(a.get("matched_signals") or []) != sorted(b.get("matched_signals") or []):
        return False
    if (a.get("email") or "").lower() != (b.get("email") or "").lower():
        return False
    if (a.get("phone") or "") != (b.get("phone") or ""):
        return False
    org_a, org_b = a.get("organization"), b.get("organization")
    if bool(org_a) != bool(org_b):
        return False
    if org_a and not (_sig_tokens(org_a) & _sig_tokens(org_b)):
        return False
    loc_a, loc_b = a.get("location"), b.get("location")
    if bool(loc_a) != bool(loc_b):
        return False
    if loc_a and not (_sig_tokens(loc_a) & _sig_tokens(loc_b)):
        return False
    # Snippet-level candidates carry identity only in free text: require
    # substantial textual overlap before calling two hits the same
    # identity. Two pages that merely share a city are NOT the same.
    ta, tb = _sig_tokens(a.get("text")), _sig_tokens(b.get("text"))
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return overlap >= 0.7


def resolve_entity(
    entity: EntityRecord,
    candidates: list[dict[str, Any]],
) -> list[EntityMatch]:
    """
    Resolve one entity against a list of candidate contexts.

    Returns EntityMatch objects sorted by confidence (best first). The
    caller decides whether to attach the best match to the entity; this
    function also annotates each match with its decided status so that
    e.g. LinkedIn profiles are stored even when ambiguous/unverified.
    """
    if not candidates:
        empty = EntityMatch(
            entity_key=entity.entity_key,
            candidate_kind="web_result",
            candidate_name=None,
            candidate_url=None,
            match_status="not_found",
        )
        return [empty]

    scored: list[tuple[float, list[str], list[str], list[str], dict]] = []
    for candidate in candidates:
        score, matched, conflicts, reasons = score_candidate(entity, candidate)
        scored.append((score, matched, conflicts, reasons, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_matched, best_conflicts, best_reasons, best_candidate = scored[0]

    ties = [
        item for item in scored
        if abs(item[0] - best_score) <= 0.03
        and (item[4].get("url") or "") != (best_candidate.get("url") or "")
        and item[4].get("url")
        and best_candidate.get("url")
        # Two sources describing the SAME identity (identical signals and
        # content) are agreement, not competition; only genuinely different
        # candidate identities count as ties.
        and not _candidates_equivalent(
            {**item[4], "matched_signals": item[1]},
            {**best_candidate, "matched_signals": best_matched},
        )
    ]

    gov_backed = str(best_candidate.get("kind") or "") == "government_record"
    corroboration = len({s for s in best_matched if s != "name"})
    competitors = 1 + len(ties)

    status = decide_match_status(
        score=best_score,
        matched_signals=best_matched,
        conflicting_signals=best_conflicts,
        corroboration_categories=corroboration,
        tied_candidates=competitors,
        source_is_government=gov_backed,
    )

    # A single corroborating signal (usually just shared geography) from a
    # LOW-hierarchy source such as a people-search directory is not enough
    # to call an identity even "probable" -- downgrade to unverified so it
    # stays visible as an attempt without asserting identity.
    if status == "probable" and corroboration == 1:
        _, best_rank = classify_source(str(best_candidate.get("url") or ""))
        if best_rank >= 6:
            status = "unverified"

    matches: list[EntityMatch] = [
        EntityMatch(
            entity_key=entity.entity_key,
            candidate_kind=_candidate_kind(best_candidate),
            candidate_name=best_candidate.get("name"),
            candidate_url=best_candidate.get("url"),
            match_status=status,
            match_confidence=best_score,
            matched_signals=best_matched,
            conflicting_signals=best_conflicts,
            match_reasons=best_reasons,
            source=SourceRef(url=best_candidate.get("url")),
        )
    ]

    for score, matched, conflicts, reasons, candidate in scored[1:]:
        if not candidate.get("url"):
            continue
        sub_status = decide_match_status(
            score=score,
            matched_signals=matched,
            conflicting_signals=conflicts,
            corroboration_categories=len({s for s in matched if s != "name"}),
        )
        matches.append(
            EntityMatch(
                entity_key=entity.entity_key,
                candidate_kind=_candidate_kind(candidate),
                candidate_name=candidate.get("name"),
                candidate_url=candidate.get("url"),
                match_status=sub_status,
                match_confidence=score,
                matched_signals=matched,
                conflicting_signals=conflicts,
                match_reasons=reasons,
                source=SourceRef(url=candidate.get("url")),
            )
        )

    return matches


def _candidate_kind(candidate: dict[str, Any]) -> str:
    kind = str(candidate.get("kind") or "web_result")
    return kind if kind in CANDIDATE_KINDS else "web_result"


def match_linkedin_profile(
    entity: EntityRecord,
    search_results: list[dict[str, Any]],
) -> Optional[EntityMatch]:
    """
    Attempt LinkedIn discovery for one entity.

    LinkedIn profiles found via search are DISCOVERY evidence, never
    automatic identity proof: the returned EntityMatch carries the
    profile URL, its decided match_status, confidence and reasons, and
    callers attach it to the entity only per their own policy.
    """
    profiles = []
    for r in search_results:
        url = str(r.get("link") or r.get("url") or "")
        if "linkedin.com" not in url.lower():
            continue
        profiles.append({
            "name": r.get("title"),
            "url": url,
            "text": r.get("snippet") or "",
            "domain": "linkedin.com",
            "kind": "linkedin_profile",
        })

    resolved = resolve_entity(entity, profiles)
    if resolved and resolved[0].match_status == "not_found":
        return None
    return resolved[0] if resolved else None


__all__ = [
    "score_candidate",
    "decide_match_status",
    "resolve_entity",
    "match_linkedin_profile",
]
