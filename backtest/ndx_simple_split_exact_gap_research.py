"""Specific-event research with exact historical cache gaps; no strict-closure claim."""
from datetime import datetime
import hashlib
from pathlib import Path
from types import FunctionType, SimpleNamespace

from backtest import ndx_exact_price_cache_drift_research as drift
from backtest import ndx_specific_split_registry_v2_research as original
from backtest import ndx_simple_split_quote_guard_v3_research as addressed

nominal = addressed.nominal
SOURCE = Path(__file__).resolve()
LOADED = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
    SOURCE, drift.SOURCE, Path(original.__file__).resolve(), Path(addressed.__file__).resolve(),
    Path(addressed.previous.__file__).resolve(), Path(addressed.previous.first_guard.__file__).resolve(),
    Path(original.original.__file__).resolve(), nominal.SOURCE)}


def private(function, **replacements):
    return FunctionType(function.__code__, dict(function.__globals__, **replacements),
                        function.__name__, function.__defaults__, function.__closure__)


def merge(target, addition):
    for path, sha in addition.items():
        original.merge_source(target, path, sha)


def partition(expected, contract, *, require_all=False):
    # Hashes stay historical expectations throughout. The verifier returns a
    # separate current verified set; it never substitutes new CSV hashes.
    result = drift.verify_expected_sources(expected, contract)
    for path, sha in LOADED.items():
        if drift.file_sha(path) != sha:
            raise ValueError('Loaded exact-gap source changed: ' + path)
    if require_all and len(result['historical_gap_observations']) != 26:
        raise ValueError('Exact complete 26-file historical gap required')
    return result


def attach_partition(document, expected, checked):
    document.update(historical_expected_source_hashes=dict(expected),
                    verified_source_hashes=checked['verified_source_hashes'],
                    historical_price_cache_gap_observations=checked['historical_gap_observations'],
                    historical_full_source_closure_verified=False,
                    old_strict_registry_passed=False, point_in_time_verified=False,
                    promotion_allowed=False)
    return document


def load_registry():
    contract = drift.load_contract()
    expected = dict(LOADED)
    partition(expected, contract)
    def verify(mapping):
        merge(expected, mapping)
        partition(expected, contract)
    proxy = SimpleNamespace(**dict(vars(nominal), verify=verify))
    # Only the verification policy changes privately. Official raw bytes still
    # require exact SHA: none belong to the explicitly bounded root-CSV gaps.
    loader = private(original.load_registry, nominal=proxy)
    try:
        document = loader()
        merge(expected, document.pop('source_hashes'))
        if document['event_count'] != 25 or document['guard_eligible_event_count'] != 23:
            raise ValueError('Original finite event denominator differs')
        document['schema'] = 'SPECIFIC_25_EVENT_REGISTRY_EXACT_26_HISTORICAL_GAP_RESEARCH_V1'
        return attach_partition(document, expected, partition(expected, contract, require_all=True))
    finally:
        partition(expected, contract)


def reconstruct_raw_addressed_nominal_quote(*, provider_manifest_path, provider_manifest_sha256,
                                           raw_path, raw_sha256, ticker, calendar, quote_field_basis):
    if quote_field_basis != nominal.BASIS:
        raise ValueError('Explicit split-adjusted quote basis required; adjclose unsupported')
    contract = drift.load_contract()
    evidence = load_registry()
    expected = dict(evidence['historical_expected_source_hashes'])
    checked = partition(expected, contract, require_all=True)
    if (checked['verified_source_hashes'] != evidence['verified_source_hashes'] or
            checked['historical_gap_observations'] != evidence['historical_price_cache_gap_observations'] or
            evidence['historical_full_source_closure_verified'] is not False or
            'source_hashes' in evidence):
        raise ValueError('Registry source partition differs')
    if ticker in original.TRANSITIONS:
        raise ValueError('Explicit historical identity transition required')
    if ticker in original.BLOCKED:
        raise ValueError('Complex corporate action is outside simple-split scope')
    def verify(mapping):
        merge(expected, mapping)
        partition(expected, contract)
    proxy = SimpleNamespace(**dict(vars(nominal), verify=verify))
    loader = private(addressed.load_capture_by_raw, nominal=proxy)
    try:
        decoded, capture, request, raw_evidence = loader(
            manifest_path=provider_manifest_path, manifest_sha256=provider_manifest_sha256,
            raw_path=raw_path, raw_sha256=raw_sha256, sources=expected)
        received = datetime.fromisoformat(capture['received_at_utc'])
        if received.tzinfo is None or received.utcoffset().total_seconds() != 0:
            raise ValueError('Exact UTC receipt required')
        if any(nominal._day(day) >= received.astimezone(nominal.NEW_YORK).date().isoformat() for day in calendar):
            raise ValueError('Reception-day bars are not finalized')
        eligible = [event for event in evidence['events'] if event['simple_split_guard_eligible']]
        matches = addressed.previous.first_guard.match_returned_events(
            decoded=decoded, ticker=ticker, specific_events=eligible,
            blocked_tickers=original.BLOCKED | original.TRANSITIONS)
        known = addressed.previous.validate_known_event_denominator(
            ticker=ticker, matches=matches, events=eligible, request=request)
        result = nominal.reconstruct_nominal_quote_ticker(
            raw=decoded, ticker=ticker, calendar=calendar, request=request,
            received_at_utc=capture['received_at_utc'], quote_field_basis=quote_field_basis)
        output = dict(schema='SPECIFIC_SPLIT_RAW_ADDRESSED_EXACT_26_GAP_GUARD_RESEARCH_V1',
            reconstruction=result, original_capture_reference=dict(
                manifest_path=str(Path(provider_manifest_path).resolve()), manifest_sha256=provider_manifest_sha256,
                raw_path=str(Path(raw_path).resolve()), raw_sha256=raw_sha256),
            raw_decoding_evidence=raw_evidence, matched_specific_events=matches,
            known_in_request_event_dates=known, returned_event_count=len(matches),
            registry_event_count=25, registry_guard_eligible_event_count=23,
            original_capture_names_synthesized=False, known_in_request_events_all_present=True,
            all_returned_events_individually_supported=True, no_returned_events_observed=not matches,
            absence_of_returned_events_proves_no_corporate_actions=False,
            complete_corporate_action_history_verified=False, quote_basis_independently_authenticated=False,
            price_identity_verified=False, new_22_receipt_format_admitted=False,
            scope='SPECIFIC_STANDARD_SHARE_SPLITS_ONLY_WITH_EXPLICIT_HISTORICAL_CACHE_GAPS')
        return attach_partition(output, expected, partition(expected, contract, require_all=True))
    finally:
        partition(expected, contract)
