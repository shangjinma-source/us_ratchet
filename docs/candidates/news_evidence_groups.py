"""Pure evidence grouping candidate; no semantic clustering or trading decisions.

Feed saved event observations BEFORE URL deduplication, including older snapshots.
Returned observations retain every source and timestamp. Groups contain indices,
not replacement articles. Exact captured excerpt equality is not proof of equal
full articles, independent sources, or a publisher-confirmed revision.
"""
from copy import deepcopy
from hashlib import sha256
from urllib.parse import urlsplit


def _usable_url(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme in ('https', 'http') and bool(parsed.hostname) and not parsed.username
    except ValueError:
        return False


def group_evidence(events):
    """Preserve input order; compare exact URL and exact nonempty source_text.

    No title, supplied hash, timestamp, or AI summary determines equivalence.
    Same-URL captures with different text are observed variants, not adjudicated
    corrections. Whitespace/case differences deliberately remain distinct.
    """
    observations = deepcopy(list(events))
    by_url, by_text = {}, {}
    for index, event in enumerate(observations):
        if not isinstance(event, dict):
            raise ValueError('EVENT_MUST_BE_OBJECT')
        url = event.get('url')
        if _usable_url(url):
            by_url.setdefault(url, []).append(index)
        body = event.get('source_text')
        if isinstance(body, str) and body.strip() and _usable_url(url):
            by_text.setdefault(body, []).append(index)

    url_groups = []
    for url, indices in by_url.items():
        if len(indices) < 2:
            continue
        versions, unavailable = {}, []
        for index in indices:
            body = observations[index].get('source_text')
            if not isinstance(body, str) or not body.strip():
                unavailable.append(index)
                continue
            versions.setdefault(body, []).append(index)
        url_groups.append(dict(
            url=url, observation_indices=indices,
            has_observed_text_variants=len(versions) > 1,
            versions=[dict(captured_text_sha256=sha256(body.encode('utf-8')).hexdigest(),
                           observation_indices=members) for body, members in versions.items()],
            unavailable_text_indices=unavailable,
        ))

    duplicates = []
    for body, indices in by_text.items():
        urls = list(dict.fromkeys(observations[index]['url'] for index in indices))
        if len(urls) > 1:
            duplicates.append(dict(
                captured_text_sha256=sha256(body.encode('utf-8')).hexdigest(),
                observation_indices=indices, urls=urls,
                relation='EXACT_CAPTURED_TEXT_ACROSS_URLS',
            ))
    return dict(
        schema_version='news-evidence-groups-v1', observations=observations,
        same_url_groups=url_groups, exact_text_groups=duplicates,
        limitations=[
            'Groups preserve observations; do not replace or suppress original sources.',
            'Different captures may reflect extraction changes, not publisher revisions.',
            'Exact captured excerpts may omit different full-article content.',
            'No semantic conflict detection, truth judgment, or chronological inference.',
        ],
    )
