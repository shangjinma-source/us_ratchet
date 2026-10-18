"""Build a review-only evidence pack from fetched SEC filing documents.

This module deliberately extracts document provenance and business-section
candidates only.  It never assigns a risk chain, never uses prices/returns,
and treats filings without a standardized business section as pending manual
review.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

import pandas as pd
from lxml import html as lxml_html


REVIEW_SCHEMA_VERSION = 1
MAX_EXCERPT_CHARS = 6000
MIN_BUSINESS_SECTION_CHARS = 500

REVIEW_DOCUMENT_COLUMNS = [
    "job_id",
    "issuer_id",
    "cik",
    "accession_number",
    "form",
    "security_ids",
    "tickers",
    "selection_date_start",
    "selection_date_end",
    "evidence_required_from",
    "source_available_date",
    "document_url",
    "raw_path",
    "raw_manifest_path",
    "raw_sha256",
    "raw_manifest_sha256",
    "raw_manifest_verified",
    "document_title",
    "document_text_chars",
    "document_text_sha256",
    "extraction_status",
    "section_label",
    "section_text_chars",
    "section_text_sha256",
    "business_excerpt",
    "business_excerpt_sha256",
    "business_excerpt_truncated",
    "review_status",
    "review_note",
]

REVIEW_TEMPLATE_COLUMNS = [
    "evidence_id",
    "security_id",
    "issuer_id",
    "ticker",
    "risk_chain",
    "effective_from",
    "effective_to",
    "evidence_source_type",
    "evidence_source",
    "evidence_locator",
    "evidence_available_date",
    "accession_number",
    "evidence_excerpt",
    "confidence",
    "status",
    "notes",
]

REVIEW_GAP_COLUMNS = [
    "gap_id",
    "security_id",
    "issuer_id",
    "ticker",
    "cik",
    "cusip",
    "observation_from",
    "evidence_required_from",
    "plan_status",
    "issue_type",
    "sec_submissions_url",
    "source_policy",
    "classification_allowed",
    "future_data_guard",
    "next_action",
]


class TaxonomyReviewError(ValueError):
    """Raised when a review pack cannot be built without guessing."""


def _normalise_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _classification_excerpt(section_text: str, form: str) -> str:
    """Choose the most classification-relevant part of a reviewed section.

    For a 20-F, the issuer's primary business description is usually under
    ``B. Business Overview`` after the historical narrative.  The review
    artifact should expose that text first so a later decision references a
    business statement rather than an arbitrary first page of Item 4.
    """
    text = str(section_text or "").strip()
    if not text:
        return ""
    if str(form or "").upper().replace("/A", "") == "20-F":
        # Some 20-Fs place the actual business definition in an incorporated
        # annual-report narrative instead of repeating it immediately after
        # the Item 4 heading.  Prefer an explicit biopharmaceutical business
        # definition when present; this is still source text, not a semantic
        # classification made by the extractor.
        biopharma = re.search(
            r"\b[A-Z][A-Za-z& .'-]{1,40}\bis a global,\s+innovation-driven\s+biopharmaceutical\s+business\b",
            text,
            flags=re.IGNORECASE,
        )
        if biopharma:
            text = text[max(0, biopharma.start() - 220):]
        markers = list(re.finditer(
            r"\bB\s*[.\-:—–]?\s*BUSINESS\s+OVERVIEW\b",
            text,
            flags=re.IGNORECASE,
        ))
        scored = []
        for marker in markers:
            suffix = text[marker.end(): marker.end() + 320]
            prefix = text[max(0, marker.start() - 180): marker.start()]
            score = 0
            if not re.match(r"\s*[\-—–]", suffix):
                score += 3
            if re.match(
                r"\s*(OUR|WE|THE|OVERVIEW|A\s+LEADING|OUR\s+MISSION|THE\s+INFORMATION)",
                suffix,
                flags=re.IGNORECASE,
            ):
                score += 2
            if re.search(r"\bREGULATION\b|\bREGULATIONS\b", suffix[:180], re.IGNORECASE):
                score -= 3
            if re.search(r"\bSEE\s+[\"“]?ITEM\b", prefix, re.IGNORECASE):
                score -= 1
            scored.append((score, -marker.start(), marker))
        if scored:
            marker = max(scored, key=lambda item: (item[0], item[1]))[2]
            text = text[marker.start():]
    return text[:MAX_EXCERPT_CHARS]


def _remove_non_document_nodes(root) -> None:
    for node in root.xpath(
        "//head|//script|//style|//*[local-name()='header']|"
        "//*[local-name()='resources']|//*[local-name()='hidden']"
    ):
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)


def _section_rules(form: str) -> tuple[str, list[str], list[str]] | None:
    normalized = str(form or "").upper().replace("/A", "")
    if normalized in {"10-K", "40-F"}:
        return (
            "Item 1 Business",
            [
                r"\bITEM\s+1\s*[.\-:—–]?\s*B\s*U\s*S\s*I\s*N\s*E\s*S\s*S\b",
                r"\bITEMS?\s+1\s+AND\s+2\s*[.\-:—–]?\s*BUSINESS(?:\s+AND\s+PROPERTIES)?\b",
            ],
            [
                r"\bITEM\s+1A\s*[.\-:—–]?\s*R\s*I\s*S\s*K\s+FACTORS\b",
                r"\bITEM\s+2\s*[.\-:—–]?\s*PROPERTIES\b",
            ],
        )
    if normalized == "20-F":
        return (
            "Item 4 Information on the Company",
            [
                r"\bITEM\s+4\s*[.\-:—–]?\s*INFORMATION\s+(?:ON|OF)\s+THE\s+COMPANY\b",
                # Some otherwise standard 20-Fs replace the generic Form
                # heading with the registrant's legal name. Keep explicit
                # variants narrow: a broad INFORMATION ON pattern also
                # captures risk-factor cross references.
                r"\bTABLE\s+OF\s+CONTENTS\s+ITEM\s+4\s*[.\-:—–]?\s*"
                r"INFORMATION\s+ON\s+CHECK\s+POINT\b",
            ],
            [
                r"\bITEM\s+4A\s*[.\-:—–]?\s*UNRESOLVED\s+STAFF\s+COMMENTS\b",
                r"\bITEM\s+5\s*[.\-:—–]?\s*OPERATING\s+AND\s+FINANCIAL\s+REVIEW\b",
                r"\bITEM\s+5\s*[.\-:—–]?\s*OPERATING\b",
            ],
        )
    return None


_BUSINESS_INTRO_PATTERN = re.compile(
    r"\b(?:OVERVIEW|GENERAL|COMPANY\s+OVERVIEW|OUR\s+COMPANY|OUR\s+BUSINESS|"
    r"DESCRIPTION\s+OF\s+BUSINESS|ABOUT\s+[A-Z][A-Z &.-]{2,40})\b"
    r"|\b(?:WE|OUR|THE\s+COMPANY|[A-Z][A-Za-z& .'-]{1,80})\s+"
    r"(?:ARE|IS|PROVIDE|DESIGN|DEVELOP|OPERATE|MANUFACTURE|DELIVER|BUILD)\b",
    flags=re.IGNORECASE,
)


def _section_candidate_score(text: str, start: re.Match, end: re.Match) -> int:
    """Score a bounded heading occurrence without interpreting its business.

    SEC HTML repeats Item headings in tables of contents, cross-references and
    risk sections.  Length alone therefore selects the wrong text surprisingly
    often.  This score only detects document structure; it never maps a phrase
    to a risk chain.
    """
    prefix = text[max(0, start.start() - 260): start.start()]
    window = text[start.end(): min(len(text), start.end() + 900)]
    score = 0
    if _BUSINESS_INTRO_PATTERN.search(window[:700]):
        score += 8
    if re.search(
        r"\b(?:TABLE\s+OF\s+CONTENTS|INDEX)\b",
        prefix[-180:] + window[:500],
        re.IGNORECASE,
    ):
        score -= 12
    if re.search(r"\b(?:ITEM\s+1A|ITEM\s+2|ITEM\s+3)\b", window[:500], re.IGNORECASE):
        score -= 8
    if re.search(
        r"\b(?:OF|IN)\s+THIS\s+(?:REPORT|ANNUAL\s+REPORT)\b|"
        r"\bFOR\s+ADDITIONAL\s+INFORMATION\b|"
        r"\bSEE\s+(?:ITEM|PART)\b|\bBUSINESS\s*[\u002d\u2013\u2014]\s*COMPETITION\b",
        window[:650],
        re.IGNORECASE,
    ):
        score -= 10
    if re.match(r"\s*[\u002d\u2013\u2014]", window) or re.match(
        r"\s*(?:[\W_]{0,3})(?:ABOVE(?:\s+FOR)?|OF|IN|FOR)\s+"
        r"(?:THIS|ADDITIONAL|INFORMATION)\b|"
        r"\s*(?:REIMBURSEMENT|MARKETING|GOVERNMENT|MANUFACTURING|"
        r"HUMAN\s+CAPITAL|BUSINESS\s+RELATIONSHIPS|INFORMATION\s+ABOUT)",
        window,
        re.IGNORECASE,
    ):
        score -= 8
    if re.search(r"\bPART\s+I\b", prefix[-300:], re.IGNORECASE):
        score += 2
    if end.start() - start.start() < MIN_BUSINESS_SECTION_CHARS:
        score -= 5
    return score


def _section_candidate_reliable(text: str, start: int, end: int) -> bool:
    """Reject obvious contents/cross-reference occurrences."""
    window = text[start + 0: min(len(text), start + 900)]
    if re.search(r"\b(?:TABLE\s+OF\s+CONTENTS|INDEX)\b", window[:500], re.IGNORECASE):
        return False
    if re.match(
        r"\s*(?:[\u002d\u2013\u2014]|[\W_]{0,3}(?:ABOVE(?:\s+FOR)?|OF|IN|FOR)\s+"
        r"(?:THIS|ADDITIONAL|INFORMATION)\b)",
        window,
        re.IGNORECASE,
    ):
        return False
    if re.match(
        r"\s*(?:REIMBURSEMENT|MARKETING|GOVERNMENT|MANUFACTURING|"
        r"HUMAN\s+CAPITAL|BUSINESS\s+RELATIONSHIPS)\b",
        window,
        re.IGNORECASE,
    ):
        return False
    return end - start >= MIN_BUSINESS_SECTION_CHARS


def extract_business_section(content: bytes | str, form: str) -> dict:
    """Extract a review candidate without interpreting its business.

    The longest bounded standardized section is selected to avoid treating a
    table-of-contents occurrence as the actual Item 1/Item 4 section.  A
    section that is absent or too short remains non-accepted.
    """
    rules = _section_rules(form)
    if rules is None:
        return {
            "extraction_status": "no_standardized_business_section",
            "section_label": "",
            "section_text": "",
            "document_title": "",
            "document_text_chars": 0,
            "document_text_sha256": "",
        }
    try:
        raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        root = lxml_html.fromstring(raw)
        title_values = root.xpath("//title//text()")
        title = _normalise_text(" ".join(title_values))
        _remove_non_document_nodes(root)
        # SEC inline-XBRL HTML often places adjacent headings in separate
        # elements without a literal whitespace node (for example ``I`` +
        # ``ITEM 1``).  Joining text nodes prevents false section misses.
        text = _normalise_text(" ".join(str(part) for part in root.itertext()))
    except Exception as exc:  # pragma: no cover - parser-specific failures
        return {
            "extraction_status": "document_parse_failed",
            "section_label": "",
            "section_text": "",
            "document_title": "",
            "document_text_chars": 0,
            "document_text_sha256": "",
            "extraction_error": f"{type(exc).__name__}: {exc}",
        }

    label, start_patterns, end_patterns = rules
    starts = [
        match
        for pattern in start_patterns
        for match in re.finditer(pattern, text, flags=re.IGNORECASE)
    ]
    # A 20-F often repeats ``Item 4. Information on the Company`` in
    # cross-references and in the table of contents.  The actual section
    # heading is normally followed by ``A. History and Development of the
    # Company``.  Prefer those candidates before applying the length
    # heuristic; otherwise a later cross-reference can swallow the real
    # business section and leave an apparently valid, but unusable excerpt.
    if str(form or "").upper().replace("/A", "") == "20-F":
        primary_starts = []
        history_pattern = (
            r"\bA\s*[.\-:]?\s*HISTORY\s+AND\s+DEVELOPMENT\s+OF\s+THE\s+COMPANY\b"
        )
        for start in starts:
            window = text[start.end(): start.end() + 900]
            if re.search(
                history_pattern
                + r"|\bOUR\s+HISTORY\s+AND\s+STRUCTURE\b"
                + r"|\bBUSINESS\s+OVERVIEW\s+OF\s+THE\s+COMPANY\b",
                window,
                flags=re.IGNORECASE,
            ):
                primary_starts.append(start)
        if primary_starts:
            starts = primary_starts
    ends = [
        match
        for pattern in end_patterns
        for match in re.finditer(pattern, text, flags=re.IGNORECASE)
    ]
    candidates = []
    for start in starts:
        following = [end for end in ends if end.start() > start.end()]
        if not following:
            continue
        end = min(following, key=lambda match: match.start())
        section_text = text[start.start():end.start()].strip()
        candidates.append((
            _section_candidate_score(text, start, end),
            len(section_text),
            start.start(),
            end.start(),
            section_text,
        ))

    used_fallback = False
    substantive_candidates = [
        candidate for candidate in candidates
        if candidate[1] >= MIN_BUSINESS_SECTION_CHARS
    ]
    # A subset of foreign private issuer 20-F filings incorporates the
    # business narrative from an issuer annual report instead of repeating a
    # literal ``Item 4`` section in the filed HTML.  The source is still the
    # SEC-hosted filing; this fallback only exposes a bounded source-text
    # candidate for review and never assigns a taxonomy label.
    if not substantive_candidates and str(form or "").upper().replace("/A", "") in {"10-K", "40-F"}:
        # Some issuers put the substantive Item 1 text under ``Overview`` or
        # ``Description of Business`` without repeating a parseable Item 1
        # heading.  Only accept a marker when it is immediately followed by a
        # business-style introduction; a table-of-contents ``Overview 3`` is
        # deliberately excluded.
        fallback_patterns = [
            r"\bDESCRIPTION\s+OF\s+BUSINESS\b",
            r"\bOVERVIEW\s*:?[\s\-–—]+(?:WE|[A-Z][A-Za-z& .'-]{1,70})\s+(?:ARE|IS)\b",
        ]
        fallback_matches = [
            match
            for pattern in fallback_patterns
            for match in re.finditer(pattern, text, flags=re.IGNORECASE)
            if match.start() > 10000
        ]
        if fallback_matches:
            marker = min(fallback_matches, key=lambda match: match.start())
            following = [end for end in ends if end.start() > marker.end()]
            fallback_end = min(
                (end.start() for end in following),
                default=min(len(text), marker.start() + MAX_EXCERPT_CHARS * 2),
            )
            section_text = text[marker.start():fallback_end].strip()
            if len(section_text) >= MIN_BUSINESS_SECTION_CHARS:
                candidates.append((
                    1,
                    len(section_text),
                    marker.start(),
                    fallback_end,
                    section_text,
                ))
                used_fallback = True

    if not substantive_candidates and str(form or "").upper().replace("/A", "") == "20-F":
        fallback_patterns = [
            r"\bOur main customer groups are\b",
            r"\bOur principal activities include\b",
            r"\bWe are a leading supplier\b",
            r"\bOur business consists of\b",
            r"\b[A-Z][A-Za-z& .'-]{1,80}\s+is\s+(?:a|an|the)\s+"
            r"(?:leading|global|independent|major|international|commercial-stage)\b",
        ]
        fallback_matches = [
            match
            for pattern in fallback_patterns
            for match in re.finditer(pattern, text, flags=re.IGNORECASE)
        ]
        if fallback_matches:
            marker = min(fallback_matches, key=lambda match: match.start())
            fallback_end = min(len(text), marker.start() + MAX_EXCERPT_CHARS * 2)
            section_text = text[marker.start():fallback_end].strip()
            if len(section_text) >= MIN_BUSINESS_SECTION_CHARS:
                candidates.append((
                    1,
                    len(section_text),
                    marker.start(),
                    fallback_end,
                    section_text,
                ))
                used_fallback = True
    base = {
        "extraction_status": "no_bounded_business_section",
        "section_label": label,
        "section_text": "",
        "document_title": title,
        "document_text_chars": len(text),
        "document_text_sha256": _sha256_text(text),
    }
    if not candidates:
        return base
    preferred = [
        candidate for candidate in substantive_candidates
        if _section_candidate_reliable(text, candidate[2], candidate[3])
    ]
    normalized_form = str(form or "").upper().replace("/A", "")
    if preferred and normalized_form == "20-F":
        # A 20-F can contain an early financial-table cross-reference whose
        # text repeats both Item 4 and the History heading. Prefer the bounded
        # candidate with the strongest business-introduction score, then the
        # more substantive section, instead of blindly taking the first one.
        selected = max(preferred, key=lambda item: (item[0], item[1], -item[2]))
    elif preferred:
        selected = min(preferred, key=lambda item: item[2])
    else:
        selected = max(candidates, key=lambda item: (item[0], item[1], -item[2]))
    _, _, start_position, end_position, section_text = selected
    if len(section_text) < MIN_BUSINESS_SECTION_CHARS:
        base.update({
            "extraction_status": "business_section_candidate_too_short",
            "section_text": section_text,
            "section_start": start_position,
            "section_end": end_position,
        })
        return base
    base.update({
        "extraction_status": (
            "business_text_fallback_candidate"
            if used_fallback
            else "business_section_extracted"
        ),
        "section_text": section_text,
        "section_start": start_position,
        "section_end": end_position,
    })
    return base


def _joined_unique(values: Iterable[object]) -> str:
    return ";".join(sorted({str(value).strip() for value in values if str(value).strip()}))


def _safe_relative(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _manifest_verified(path: Path) -> tuple[bool, str, str]:
    sidecar = Path(f"{path}.manifest.json")
    if not path.exists() or not sidecar.exists():
        return False, "", sidecar.as_posix()
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sidecar_digest = hashlib.sha256(sidecar.read_bytes()).hexdigest()
        verified = str(payload.get("content_sha256") or "") == digest
        return verified, digest, sidecar.as_posix()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False, "", sidecar.as_posix()


def build_review_documents(
    plan: pd.DataFrame,
    attempts: pd.DataFrame,
    *,
    raw_root: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build document provenance rows and pending evidence rows."""
    required_plan = {
        "job_id", "security_id", "issuer_id", "ticker", "cik", "observation_from",
        "evidence_required_from", "source_available_date", "accession_number", "form",
    }
    required_attempts = {
        "job_id", "issuer_id", "cik", "accession_number", "status", "document_url",
        "raw_path", "content_sha256",
    }
    missing_plan = sorted(required_plan - set(plan.columns))
    missing_attempts = sorted(required_attempts - set(attempts.columns))
    if missing_plan or missing_attempts:
        raise TaxonomyReviewError(
            f"review inputs missing: plan={missing_plan}, attempts={missing_attempts}"
        )
    raw_base = Path(raw_root).resolve()
    plan_groups = {str(key): group for key, group in plan.groupby("job_id", sort=False)}
    documents = []
    templates = []
    fetched = attempts[attempts["status"].astype(str).eq("fetched")].copy()
    for row in fetched.itertuples(index=False):
        job_id = str(row.job_id)
        plan_rows = plan_groups.get(job_id)
        if plan_rows is None or plan_rows.empty:
            raise TaxonomyReviewError(f"fetched SEC job is absent from evidence plan: {job_id}")
        form = str(plan_rows["form"].iloc[0])
        raw_path = Path(str(row.raw_path))
        if not _safe_relative(raw_path, raw_base):
            raise TaxonomyReviewError(f"raw SEC path escapes raw root: {raw_path}")
        manifest_ok, actual_sha, raw_manifest_path = _manifest_verified(raw_path)
        expected_sha = str(row.content_sha256 or "")
        if expected_sha and actual_sha and expected_sha != actual_sha:
            raise TaxonomyReviewError(f"raw SEC hash mismatch for job {job_id}")
        extraction = extract_business_section(raw_path.read_bytes(), form)
        section_text = str(extraction.get("section_text") or "")
        excerpt = _classification_excerpt(section_text, form)
        available_dates = _joined_unique(plan_rows["source_available_date"])
        required_dates = _joined_unique(plan_rows["evidence_required_from"])
        selection_dates = pd.to_datetime(plan_rows["observation_from"], errors="coerce")
        selection_start = selection_dates.min().strftime("%Y-%m-%d") if not selection_dates.isna().all() else ""
        selection_end = selection_dates.max().strftime("%Y-%m-%d") if not selection_dates.isna().all() else ""
        raw_manifest_sha = ""
        if Path(raw_manifest_path).exists():
            raw_manifest_sha = hashlib.sha256(Path(raw_manifest_path).read_bytes()).hexdigest()
        document = {
            "job_id": job_id,
            "issuer_id": str(row.issuer_id),
            "cik": str(row.cik),
            "accession_number": str(row.accession_number),
            "form": form,
            "security_ids": _joined_unique(plan_rows["security_id"]),
            "tickers": _joined_unique(plan_rows["ticker"]),
            "selection_date_start": selection_start,
            "selection_date_end": selection_end,
            "evidence_required_from": required_dates,
            "source_available_date": available_dates,
            "document_url": str(row.document_url),
            "raw_path": raw_path.as_posix(),
            "raw_manifest_path": raw_manifest_path,
            "raw_sha256": actual_sha or expected_sha,
            "raw_manifest_sha256": raw_manifest_sha,
            "raw_manifest_verified": manifest_ok,
            "document_title": extraction.get("document_title", ""),
            "document_text_chars": extraction.get("document_text_chars", 0),
            "document_text_sha256": extraction.get("document_text_sha256", ""),
            "extraction_status": extraction.get("extraction_status", ""),
            "section_label": extraction.get("section_label", ""),
            "section_text_chars": len(section_text),
            "section_text_sha256": _sha256_text(section_text) if section_text else "",
            "business_excerpt": excerpt,
            "business_excerpt_sha256": _sha256_text(excerpt) if excerpt else "",
            "business_excerpt_truncated": len(section_text) > len(excerpt),
            "review_status": "pending_manual_review",
            "review_note": "仅提取 SEC 主文档候选段落；不得据此自动赋予风险链。",
        }
        documents.append(document)
        templates.append({
            "evidence_id": f"sec:{job_id}",
            "security_id": "",
            "issuer_id": str(row.issuer_id),
            "ticker": "",
            "risk_chain": "",
            "effective_from": "",
            "effective_to": "",
            "evidence_source_type": "sec_filing_business_description",
            "evidence_source": f"SEC {form} 主文档（人工复核）",
            "evidence_locator": str(row.document_url),
            "evidence_available_date": available_dates.split(";", 1)[0] if available_dates else "",
            "accession_number": str(row.accession_number),
            "evidence_excerpt": excerpt,
            "confidence": "",
            "status": "pending_review",
            "notes": (
                f"job_id={job_id}; extraction_status={extraction.get('extraction_status', '')}; "
                "issuer级证据可扩展至同发行人多股类；有效期和风险链必须人工填写。"
            ),
        })
    return (
        pd.DataFrame(documents, columns=REVIEW_DOCUMENT_COLUMNS),
        pd.DataFrame(templates, columns=REVIEW_TEMPLATE_COLUMNS),
    )


def build_filing_plan_gaps(plan: pd.DataFrame, attempts: pd.DataFrame) -> pd.DataFrame:
    """List rows that need a new official filing locator or identity work."""
    attempted = set(
        attempts.loc[attempts["status"].astype(str).eq("fetched"), "job_id"].astype(str)
    )
    gaps = plan[~plan["job_id"].astype(str).isin(attempted)].copy()
    if gaps.empty:
        return pd.DataFrame(columns=REVIEW_GAP_COLUMNS)
    rows = []
    for row in gaps.itertuples(index=False):
        cik = str(row.cik or "").strip()
        cik_digits = re.sub(r"\D", "", cik)
        submissions_url = (
            f"https://data.sec.gov/submissions/CIK{cik_digits.zfill(10)}.json"
            if cik_digits
            else ""
        )
        identity_issue = str(row.plan_status) == "identity_unresolved"
        rows.append({
            "gap_id": f"gap:{row.job_id}:{row.security_id}",
            "security_id": str(row.security_id),
            "issuer_id": str(row.issuer_id),
            "ticker": str(row.ticker),
            "cik": cik,
            "cusip": str(row.cusip),
            "observation_from": str(row.observation_from),
            "evidence_required_from": str(row.evidence_required_from),
            "plan_status": str(row.plan_status),
            "issue_type": "identity_unresolved" if identity_issue else "missing_sec_filing_plan",
            "sec_submissions_url": submissions_url,
            "source_policy": "SEC filing business description / issuer official material / Nasdaq official material",
            "classification_allowed": False,
            "future_data_guard": "evidence_available_date <= selection_date",
            "next_action": (
                "先解决 CUSIP/证券身份，再建立点时申报定位；不得按名称或当前标签分类。"
                if identity_issue
                else "通过 SEC 官方 submissions/申报目录建立 accession、form、filed_date；不得猜 accession。"
            ),
        })
    return pd.DataFrame(rows, columns=REVIEW_GAP_COLUMNS).sort_values(
        ["issue_type", "ticker", "security_id"], kind="stable"
    ).reset_index(drop=True)


def review_summary(documents: pd.DataFrame, gaps: pd.DataFrame) -> dict:
    status_counts = {
        str(key): int(value)
        for key, value in documents["extraction_status"].value_counts(dropna=False).items()
    } if not documents.empty else {}
    return {
        "review_schema_version": REVIEW_SCHEMA_VERSION,
        "raw_document_count": int(len(documents)),
        "business_section_extracted_count": int(
            documents["extraction_status"].eq("business_section_extracted").sum()
        ) if not documents.empty else 0,
        "extraction_status_counts": status_counts,
        "filing_plan_gap_count": int(len(gaps)),
        "review_status": "manual_review_required",
        "risk_chain_assigned": False,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
        "future_data_guard": "evidence_available_date <= selection_date",
        "historical_backfill_allowed": False,
    }
