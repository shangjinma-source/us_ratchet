"""Conditional date-label bound for research, not historical availability proof."""

from datetime import date, datetime, time, timedelta, timezone


def bound(
    publication_date: str,
    next_open: str,
    processing_seconds: int,
    *,
    confirmed_publication_date_label: bool = False,
) -> dict[str, object]:
    """Bound a confirmed publication-date label using the latest civil offset."""
    if confirmed_publication_date_label is not True:
        raise ValueError("CONFIRMED_PUBLICATION_DATE_LABEL_REQUIRED")
    if not isinstance(publication_date, str):
        raise ValueError("PUBLICATION_DATE_REQUIRED")

    try:
        publication_day = date.fromisoformat(publication_date)
    except (ValueError, TypeError):
        raise ValueError("CANONICAL_PUBLICATION_DATE_REQUIRED") from None
    if publication_day.isoformat() != publication_date:
        raise ValueError("CANONICAL_PUBLICATION_DATE_REQUIRED")

    if type(processing_seconds) is not int or processing_seconds < 0:
        raise ValueError("NONNEGATIVE_INTEGER_PROCESSING_SECONDS_REQUIRED")

    try:
        opening_time = datetime.fromisoformat(next_open.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("AWARE_NEXT_OPEN_REQUIRED") from None
    if opening_time.tzinfo is None or opening_time.utcoffset() is None:
        raise ValueError("AWARE_NEXT_OPEN_REQUIRED")

    # Among civil offsets UTC-12..UTC+14, UTC-12 reaches the next calendar
    # midnight last. Use that exclusive endpoint as the conservative bound.
    upper_bound = datetime.combine(
        publication_day + timedelta(days=1),
        time(),
        tzinfo=timezone(timedelta(hours=-12)),
    ).astimezone(timezone.utc)
    eligible_upper_bound = upper_bound + timedelta(seconds=processing_seconds)

    return {
        "publication_date": publication_date,
        "upper_bound_utc": upper_bound.isoformat(),
        "eligible_upper_bound_utc": eligible_upper_bound.isoformat(),
        "next_open_utc": opening_time.astimezone(timezone.utc).isoformat(),
        "processing_seconds": processing_seconds,
        "executable": eligible_upper_bound < opening_time,
        "quality": "DATE_ONLY_CONSERVATIVE_GLOBAL_BOUND_CONDITIONAL",
        "confirmed_publication_date_label": True,
        "limitations": [
            "Assumes the displayed publication date corresponds to original "
            "publication in some civil offset UTC-12..UTC+14.",
            "Current archive date is not immutable historical first-publication evidence.",
            "Report-period dates, SEC acceptance proxies and date inference are not admitted.",
            "Bound equality with open is rejected; no same-day availability is inferred.",
        ],
    }
