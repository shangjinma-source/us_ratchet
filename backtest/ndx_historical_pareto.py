"""Unranked Pareto membership for one historical replay coordinate.

The six axes match the existing capital-shortlist contract. This helper does
not select a live portfolio, pool evaluation windows, or cap holding counts.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date


PARETO_AXES = (
    ("return_p50", True), ("return_p10", True),
    ("max_drawdown_p50", False), ("max_drawdown_p90", False),
    ("target_012922_distance", False), ("turnover", False),
)


def historical_pareto_membership(rows: Sequence[Mapping]) -> list[str]:
    """Return all nondominated IDs, sorted by ID, not investment desirability.

    Callers must supply one explicit source/evaluator/track/date coordinate.
    Every row must already belong to the research eligibility set; this pure
    comparison cannot independently prove its economic replay or admission.
    Equal metric vectors remain on the frontier together.
    """
    coordinates = set()
    vectors: dict[str, tuple[float, ...]] = {}
    for row in rows:
        coordinate = tuple(row.get(key) for key in (
            "source_batch", "evaluation_semantics_sha256", "universe_track",
            "selection_date",
        ))
        if any(not isinstance(value, str) or not value.strip() for value in coordinate):
            raise ValueError("explicit historical coordinate is required")
        if (len(coordinate[1]) != 64
                or any(character not in "0123456789abcdef" for character in coordinate[1])):
            raise ValueError("evaluator hash must be a canonical SHA-256")
        try:
            parsed_date = date.fromisoformat(coordinate[3])
        except ValueError as exc:
            raise ValueError("selection date must be a canonical ISO date") from exc
        if parsed_date.isoformat() != coordinate[3]:
            raise ValueError("selection date must be a canonical ISO date")
        coordinates.add(coordinate)
        identity = row.get("portfolio_id")
        if (not isinstance(identity, str) or not identity.strip()
                or identity != identity.strip() or identity in vectors):
            raise ValueError("portfolio IDs must be nonempty and unique")
        values = []
        for key, maximize in PARETO_AXES:
            value = row.get(key)
            if isinstance(value, bool):
                raise ValueError(f"invalid Pareto metric: {key}")
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid Pareto metric: {key}") from exc
            if not math.isfinite(numeric) or (not maximize and numeric < 0):
                raise ValueError(f"invalid Pareto metric: {key}")
            values.append(numeric if maximize else -numeric)
        vectors[identity] = tuple(values)
    if len(coordinates) > 1:
        raise ValueError("cross-coordinate Pareto comparison is forbidden")
    return sorted(
        identity for identity, vector in vectors.items()
        if not any(
            all(left >= right for left, right in zip(other, vector))
            and any(left > right for left, right in zip(other, vector))
            for other_id, other in vectors.items() if other_id != identity
        )
    )
