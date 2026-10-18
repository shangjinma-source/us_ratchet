"""Deterministic beam-width convergence diagnostics for cardinality search.

This module measures approximation recall against exact enumeration on the
same small, point-in-time-safe fixture.  It does not promote a search result
and it does not turn the heuristic beam into mathematical branch-and-bound.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from backtest.ndx_cardinality_discovery import (
    NdxCardinalityDiscoveryError,
    issuer_dedup_feasible_count,
    search_synthetic_cardinality,
)


OBJECTIVE_TAGS = ("RETURN", "BAD_TAIL", "DRAWDOWN", "012922_DISTANCE")


def _identity(frame: pd.DataFrame) -> pd.Series:
    return frame["tickers"].astype(str) + "|" + frame["weight_spec"].astype(str)


def _tagged_identities(frame: pd.DataFrame, tag: str) -> set[str]:
    mask = frame["frontier_tags"].fillna("").astype(str).str.split(";").map(
        lambda values: tag in values
    )
    return set(_identity(frame.loc[mask]))


def audit_beam_width_convergence(
    universe: pd.DataFrame,
    returns: pd.DataFrame,
    target: pd.Series,
    incumbent: list[str],
    *,
    holding_count: int,
    beam_widths: Sequence[int],
    search_kwargs: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compare bounded candidate/frontier recall with exact enumeration."""
    widths = [int(value) for value in beam_widths]
    if not widths or widths != sorted(set(widths)) or any(value <= 0 for value in widths):
        raise NdxCardinalityDiscoveryError(
            "beam widths must be positive, unique, and ascending"
        )
    feasible = issuer_dedup_feasible_count(universe, int(holding_count))
    if feasible <= 1:
        raise NdxCardinalityDiscoveryError("beam convergence requires more than one feasible set")
    common = dict(search_kwargs)
    common.pop("exact_limit", None)
    common.pop("beam_width", None)
    exact, exact_audit = search_synthetic_cardinality(
        universe,
        returns,
        target,
        incumbent,
        holding_count=int(holding_count),
        exact_limit=feasible,
        beam_width=max(widths),
        **common,
    )
    if not bool(exact_audit["search_exhaustive"]):
        raise NdxCardinalityDiscoveryError("exact convergence reference is not exhaustive")
    exact_identities = set(_identity(exact))
    exact_frontier = set(_identity(exact.loc[exact["frontier_tags"].ne("")]))
    exact_pareto = _tagged_identities(exact, "PARETO")
    exact_objectives = {
        tag: _tagged_identities(exact, tag) for tag in OBJECTIVE_TAGS
    }
    rows: list[dict[str, Any]] = []
    for width in widths:
        bounded, audit = search_synthetic_cardinality(
            universe,
            returns,
            target,
            incumbent,
            holding_count=int(holding_count),
            exact_limit=1,
            beam_width=width,
            **common,
        )
        identities = set(_identity(bounded))
        recalled_frontier = exact_frontier & identities
        recalled_pareto = exact_pareto & identities
        row: dict[str, Any] = {
            "holding_count": int(holding_count),
            "beam_width": width,
            "feasible_security_sets": feasible,
            "evaluated_security_sets": int(audit["evaluated_security_sets"]),
            "candidate_set_recall": len(identities & exact_identities) / len(exact_identities),
            "exact_frontier_recall": (
                len(recalled_frontier) / len(exact_frontier) if exact_frontier else 1.0
            ),
            "exact_pareto_recall": (
                len(recalled_pareto) / len(exact_pareto) if exact_pareto else 1.0
            ),
            "candidate_set_equals_exact": identities == exact_identities,
            "search_reported_exhaustive": bool(audit["search_exhaustive"]),
            "optimality_claim_allowed": bool(audit["optimality_claim_allowed"]),
            "mathematical_bound_certificate_available": bool(
                audit["mathematical_bound_certificate_available"]
            ),
        }
        for tag in OBJECTIVE_TAGS:
            winners = exact_objectives[tag]
            row[f"{tag.lower()}_winner_recalled"] = winners.issubset(identities)
        row["all_four_objective_winners_recalled"] = all(
            bool(row[f"{tag.lower()}_winner_recalled"]) for tag in OBJECTIVE_TAGS
        )
        rows.append(row)
    result = pd.DataFrame(rows)
    audit = {
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "diagnostic_role": "SYNTHETIC_BEAM_WIDTH_CONVERGENCE_ONLY",
        "heuristic_search_label": "MULTIOBJECTIVE_DETERMINISTIC_BEAM_APPROXIMATION",
        "mathematical_bound_certificate_available": False,
        "holding_count": int(holding_count),
        "feasible_security_sets": feasible,
        "exact_evaluation_rows": len(exact),
        "exact_frontier_identity_count": len(exact_frontier),
        "exact_pareto_identity_count": len(exact_pareto),
        "first_width_recalling_all_objective_winners": next(
            (
                int(row["beam_width"])
                for row in rows
                if bool(row["all_four_objective_winners_recalled"])
            ),
            None,
        ),
        "first_width_equal_to_exact_candidate_set": next(
            (
                int(row["beam_width"])
                for row in rows
                if bool(row["candidate_set_equals_exact"])
            ),
            None,
        ),
        "promotion_allowed": False,
    }
    return result, audit
