"""Index all saved candidate evidence; extract no filings and grant no PIT status."""
import argparse
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import yaml

SOURCE = Path(__file__).resolve()
OUTPUT = ROOT / 'data/cache/research/full_pool_saved_evidence_inventory_20261002_v1'
RAW_ROOT = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/raw_sec'
LOADED = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
          for path in (SOURCE, Path(yaml.__file__).resolve())}
PINS = {
 'wiring': ('data/cache/research/new_cutoff_identity_risk_wiring_20260925_v6/wiring.json', '1252cddfd4274ce8ce1f6a50c7e356fb790f45309bdd7146d71d317a754fd0fd'),
 'channels': ('data/cache/research/new_cutoff_conditional_channels_20260923_v1/channels.json', '3d708df6b273616edd46e06d2e2976acbc0e9fd90cc1243679ff94ca8befa3ac'),
 'observation': ('data/cache/research/current_quote_list_observation_20260923_v1/observation.json', 'a6d8899fb2bc22f755ecd721271ed173f24a0b959b6ff8da9c96985f940fa990'),
 'review': ('data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/reviewed/review_decisions_snapshot.yaml', '2313e9f7a2b3cad2b22dca7c7f2431dd57e74a5a4cf4c3bbca2c9c8eafa87f81'),
 'identities': ('data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv', '1434583b04e46b5260f6eef232c1de3939bdc1e1d3937f8c70ffb653e3257b0f'),
 'identity_manifest': ('data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv.manifest.json', '253eaeef5072c1360d3cf01ab19ce5c4772d9c053d94fd6984df5ad94b53cc6b'),
 'nport': ('data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv', '9b7af0d6a6654d230fe1a1a043ee935142f5e9b92bc944cd579f0080c279e384'),
 'nport_manifest': ('data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv.manifest.json', '9849bca9711054bf2ea0d745bb32f3bbd3e8c632f86ff089527d12764b952deb'),
 'exact_events': ('data/cache/candidate_pools/ndx_history/exact_events/exact_events.csv', 'd28d3cff6115926a808cbd00208ecc5ed2939da7a7befde2d8d93b331fae2324'),
 'exact_manifest': ('data/cache/candidate_pools/ndx_history/exact_events/manifest.json', '57e3ff36401994b2d67dfae72a82aa6ca8a0ae4f90444190b793924cc931588d'),
 'historical_coverage': ('data/cache/research/dynamic_frozen_v2/full_membership_coverage_20260912_v2.json', 'eb15d117e6b3c07a41decf1666b5dfbcfda2fd25ee00ea05b5df680d7473dd64'),
 'scope': ('config/ndx_membership_scope_research_v1.yaml', '3136387ea83523bd22068c7f70b282dcd44d9195efed985e630bcacd187f5d2a'),
}
CSV_ROLES = {'identities', 'nport', 'exact_events'}
YAML_ROLES = {'review', 'scope'}
FLAGS = dict.fromkeys(('point_in_time_verified', 'full_universe_coverage_verified', 'identity_interval_verified',
    'provider_binding_verified', 'risk_interval_verified', 'legal_training_input_admitted', 'promotion_allowed',
    'execution_authorized', 'fit_performed', 'http_performed', 'old_audit_called', 'prices_recomputed',
    'filing_raw_bytes_read', 'source_assertions_authenticated', 'full_transitive_source_closure_reverified'), False)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def reference(refs, role, pointer=None, csv_index=None):
    result = deepcopy(refs[role])
    if pointer is not None:
        result['json_pointer'] = pointer
    if csv_index is not None:
        result.update(csv_data_row_index=csv_index, csv_row_number_including_header=csv_index + 2)
    return result


def raw_reference(decision):
    issuer = decision['issuer_id']
    require(type(issuer) is str and re.fullmatch(r'issuer:\d{10}', issuer), 'Review issuer CIK required')
    cik = issuer.split(':')[1]
    accession = decision['accession_number']
    require(type(accession) is str and re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession), 'Review accession required')
    url = urlparse(decision['document_url'])
    prefix = '/Archives/edgar/data/' + str(int(cik)) + '/' + accession.replace('-', '') + '/'
    require(url.scheme == 'https' and url.hostname in {'www.sec.gov', 'sec.gov'}
            and url.path.startswith(prefix) and not url.query and not url.fragment, 'Issuer/SEC URL linkage differs')
    filename = url.path[len(prefix):]
    require(filename and '/' not in filename and '\\' not in filename and '%' not in filename
            and filename not in {'.', '..'}, 'Safe exact SEC filename required')
    digest = decision['raw_sha256']
    require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'Expected raw SHA required')
    return {'path': str(RAW_ROOT / ('issuer_' + cik) / accession.replace('-', '') / filename), 'sha256': digest}


def assemble_inventory(docs, refs):
    """Pure metadata join. CSV refs use explicit data row indexes, not JSON pointers."""
    require(set(docs) == set(PINS) == set(refs), 'Complete direct source roles required')
    wiring, channels, observation = (docs[key] for key in ('wiring', 'channels', 'observation'))
    require(wiring['schema'] == 'NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V6'
            and channels['schema'] == 'NEW_CUTOFF_CONDITIONAL_CHANNELS_V1'
            and observation['schema'] == 'ndx_current_quote_list_observation_v1', 'Parent schemas differ')
    for doc in (wiring, channels):
        for flag in ('point_in_time_verified', 'legal_training_input_admitted', 'promotion_allowed'):
            require(doc[flag] is False, 'Parent authority changed')
    require(observation['point_in_time_membership_verified'] is False
            and observation['historical_backfill_allowed'] is False, 'Current observation cannot prove historical membership')
    members = [row['ticker'] for row in wiring['rows']]
    require(len(members) == len(set(members)) == 101, 'Complete 101 wiring denominator required')
    require([row['ticker'] for row in channels['rows']] == members
            and [row['symbol'] for row in observation['rows']] == members, 'Exact current row order required')
    policy = docs['scope']['membership_contract']
    require(policy['permitted_status'] == 'VERIFIED_POINT_IN_TIME_MEMBER'
            and policy['unknown_membership_policy'] == 'EXCLUDE_AND_REPORT_NOT_ACCEPT'
            and policy['source_hash_alone_proves_membership'] is False
            and policy['current_snapshot_historical_backfill_allowed'] is False, 'Membership scope differs')
    require(docs['review']['research_only'] is True, 'Saved review must remain research-only')
    for role, manifest_role in (('identities', 'identity_manifest'), ('nport', 'nport_manifest')):
        manifest = docs[manifest_role]
        require(manifest['content_sha256'] == refs[role]['sha256']
                and type(manifest['row_count']) is int and manifest['row_count'] == len(docs[role]), 'CSV manifest linkage differs')
    event_meta = docs['exact_manifest']['files']['exact_events']
    require(event_meta['sha256'] == refs['exact_events']['sha256']
            and type(event_meta['rows']) is int and event_meta['rows'] == len(docs['exact_events']), 'Event source linkage differs')
    historical = docs['historical_coverage']
    require(historical['schema'] == 'ndx_full_membership_coverage_research_v1'
            and type(historical['date_count']) is int and historical['date_count'] == len(historical['dates']) == 15
            and historical['exact_daily_membership_verified'] is False, 'Historical denominator differs')
    historical_dates = [row['coordinate']['selection_date'] for row in historical['dates']]
    require(historical_dates == sorted(set(historical_dates)), 'Unique historical coordinates required')
    nport_index = {}
    for index, row in enumerate(docs['nport']):
        nport_index.setdefault(row['cusip'], []).append((index, row))
    rows, queue = [], []
    for index, ticker in enumerate(members):
        parent, channel = wiring['rows'][index], channels['rows'][index]
        for flag in ('point_in_time_verified', 'legal_training_input_admitted', 'promotion_allowed'):
            require(parent[flag] is False and channel[flag] is False, 'Row authority changed')
        identity_matches = []
        for identity_index, identity in enumerate(docs['identities']):
            if identity['ticker'] != ticker:
                continue
            require(identity['issuer_id'] == 'issuer:' + identity['cik'], 'Saved issuer coordinate inconsistent')
            if identity['identity_status'] == 'resolved':
                require(bool(identity['cusip']) and identity['security_id'] == 'security:' + identity['cik'] + ':' + identity['cusip'],
                        'Resolved identity coordinate inconsistent')
            matches = [{'row': deepcopy(nport), 'reference': reference(refs, 'nport', csv_index=nport_row),
                'match_basis': 'CUSIP_EXACT_TO_IDENTITY_ROW_NOT_TICKER',
                'nport_issuer_cik_field_available': False, 'nport_reporter_is_security_issuer': False}
                for nport_row, nport in (nport_index.get(identity['cusip'], []) if identity['cusip'] else [])]
            identity_matches.append({'row': deepcopy(identity), 'reference': reference(refs, 'identities', csv_index=identity_index),
                'nport_matches': matches, 'nport_reports_are_daily_ndx_membership': False})
        resolved = {(match['row']['security_id'], match['row']['issuer_id'], match['row']['cusip'])
                    for match in identity_matches if match['row']['identity_status'] == 'resolved'}
        review_matches = []
        for review_index, decision in enumerate(docs['review']['decisions']):
            if ticker in decision['tickers']:
                review_matches.append({'decision': deepcopy(decision),
                    'reference': reference(refs, 'review', '/decisions/' + str(review_index)),
                    'raw_reference': raw_reference(decision), 'raw_bytes_checked_by_this_inventory': False,
                    'review_issuer_matches_resolved_identity_index': bool(resolved) and all(item[1] == decision['issuer_id'] for item in resolved),
                    'matching_ticker_authenticates_identity': False})
        accepted = [item for item in review_matches if item['decision']['status'] == 'accepted']
        price_ok = channel['status'] == 'CONDITIONAL_NUMERIC_RESULT'
        require(channel['status'] in {'CONDITIONAL_NUMERIC_RESULT', 'BLOCKED_PRICE_INPUT'}, 'Unknown channel state')
        require((channel['channel_input'] is not None) == price_ok, 'Channel status/payload differs')
        liquidity = deepcopy(channel['channel_input']['liquidity']) if price_ok else None
        # Preserve all saved liquidity evidence without recomputing any observations.
        liquid_status = liquidity['status'] if liquidity is not None else 'NOT_AVAILABLE_PRICE_BLOCKED'
        missing = parent['coordinate'] is None
        selected = missing and len(resolved) == 1 and len(accepted) == 1 and price_ok and liquid_status != 'BLOCKED_VOLUME_UNIT_UNKNOWN'
        row = {'ticker': ticker, 'original_wiring_row': deepcopy(parent), 'wiring_reference': reference(refs, 'wiring', '/rows/' + str(index)),
            'observation_row': deepcopy(observation['rows'][index]), 'observation_reference': reference(refs, 'observation', '/rows/' + str(index)),
            'channel_reference': reference(refs, 'channels', '/rows/' + str(index)),
            'channel_state': {'status': channel['status'], 'reasons': deepcopy(channel['reasons']),
                'liquidity_status': liquid_status, 'liquidity_reference': reference(refs, 'channels', '/rows/' + str(index) + '/channel_input/liquidity') if price_ok else None,
                'raw_reference': deepcopy(channel['raw_reference']), 'receipt_reference': deepcopy(channel['receipt_reference']),
                'volume_units_independently_certified': channel['volume_units_independently_certified']},
            'identity_matches': identity_matches, 'review_matches': review_matches,
            'identity_match_count': len(identity_matches), 'resolved_coordinate_count': len(resolved), 'accepted_review_count': len(accepted),
            'already_wired_conditional_coordinate': not missing, 'raw_extraction_requested': selected,
            'membership_status': 'UNKNOWN_NOT_AUTHENTICATED_BY_THIS_INVENTORY',
            'conditional_evidence_role': 'REUSE_PARENT_WIRING_NOT_REEXTRACT' if not missing else 'SOURCE_LEAD_ONLY_NOT_IDENTITY_ADMISSION',
            'formal_eligible_security_count_contribution': None, **FLAGS}
        rows.append(row)
        if selected:
            queue.append({'ticker': ticker, 'inventory_row_index': index,
                'raw_reference': deepcopy(accepted[0]['raw_reference']), 'review_match': deepcopy(accepted[0]),
                'resolved_identity_coordinates': [{'security_id': sid, 'issuer_id': issuer, 'cusip': cusip} for sid, issuer, cusip in sorted(resolved)],
                'identity_matches': deepcopy(identity_matches), 'purpose': 'EXTRACT_SAVED_RAW_FACTS_ONLY_NOT_FIT_OR_PIT_ADMISSION', **FLAGS})
    summary = {'observed_denominator': len(rows), 'already_wired_conditional_count': sum(r['already_wired_conditional_coordinate'] for r in rows),
        'remaining_unassembled_count': sum(not r['already_wired_conditional_coordinate'] for r in rows),
        'remaining_with_single_accepted_review': sum(not r['already_wired_conditional_coordinate'] and r['accepted_review_count'] == 1 for r in rows),
        'remaining_with_unique_resolved_coordinate': sum(not r['already_wired_conditional_coordinate'] and r['resolved_coordinate_count'] == 1 for r in rows),
        'remaining_with_conditional_price': sum(not r['already_wired_conditional_coordinate'] and r['channel_state']['status'] == 'CONDITIONAL_NUMERIC_RESULT' for r in rows),
        'blocked_price_count': sum(r['channel_state']['status'] == 'BLOCKED_PRICE_INPUT' for r in rows),
        'blocked_volume_unit_count': sum(r['channel_state']['liquidity_status'] == 'BLOCKED_VOLUME_UNIT_UNKNOWN' for r in rows),
        'raw_extraction_queue_count': len(queue), 'historical_denominator_count': 15,
        'verified_pit_eligible_count': None}
    return {'schema': 'FULL_POOL_SAVED_EVIDENCE_INVENTORY_V1', 'rows': rows, 'extraction_queue': queue, 'summary': summary,
        'historical_denominators': [{'source_row': deepcopy(row), 'reference': reference(refs, 'historical_coverage', '/dates/' + str(index))}
                                    for index, row in enumerate(historical['dates'])],
        'original_membership_scope_contract': deepcopy(docs['scope']),
        'saved_exact_event_manifest': deepcopy(docs['exact_manifest']),
        'saved_exact_event_rows': deepcopy(docs['exact_events']),
        'event_registry_is_complete_interval_certification': False,
        'current_rows_replace_historical_denominators': False, 'raw_path_is_planned_reference_not_this_run_byte_attestation': True,
        'source_matching_policy': 'TICKER_FOR_INDEX_LOCATION_ONLY_SID_CUSIP_FOR_REPORT_LINKS_REPORTER_NOT_ISSUER',
        'input_references': deepcopy(refs), **FLAGS}


def read_inputs():
    docs, refs = {}, {}
    sources = dict(LOADED)
    for role, (relative, digest) in PINS.items():
        path = ROOT / relative
        raw = path.read_bytes()
        require(sha(raw) == digest, 'Source bytes differ: ' + role)
        sources[str(path)] = digest
        refs[role] = {'path': str(path), 'sha256': digest}
        docs[role] = (list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))) if role in CSV_ROLES else
                      yaml.safe_load(raw.decode('utf-8-sig')) if role in YAML_ROLES else json.loads(raw))
    return docs, refs, sources


def guard(sources):
    require(all(sources.get(path) == digest for path, digest in LOADED.items()), 'Loaded source linkage differs')
    for path, digest in sources.items():
        require(sha(Path(path).read_bytes()) == digest, 'Source drift: ' + path)


def write_new(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False, ensure_ascii=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Output changed')
    return sha(raw)


def run():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no retry')
    guard(LOADED)
    docs, refs, sources = read_inputs()
    guard(sources)
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        write_new(OUTPUT / 'started.json', {'source_hashes': sources, 'retry_allowed': False, **FLAGS})
        result = assemble_inventory(docs, refs)
        require(result['summary'] == {'observed_denominator': 101, 'already_wired_conditional_count': 25,
            'remaining_unassembled_count': 76, 'remaining_with_single_accepted_review': 57,
            'remaining_with_unique_resolved_coordinate': 65, 'remaining_with_conditional_price': 71,
            'blocked_price_count': 5, 'blocked_volume_unit_count': 2, 'raw_extraction_queue_count': 53,
            'historical_denominator_count': 15, 'verified_pit_eligible_count': None}, 'Pinned batch denominator differs')
        result['source_hashes'] = sources
        guard(sources)
        digest = write_new(OUTPUT / 'inventory.json', result)
        guard(sources)
        publication = write_new(OUTPUT / 'publication.json', {'schema': 'FULL_POOL_SAVED_EVIDENCE_INVENTORY_PUBLICATION_V1',
            'status': 'PUBLISHED_SOURCE_INDEX_ONLY_NOT_PIT_ADMISSION', 'inventory_reference': {'path': str(OUTPUT / 'inventory.json'), 'sha256': digest},
            'source_hashes': sources, **FLAGS})
        guard(sources)
        require(sha((OUTPUT / 'inventory.json').read_bytes()) == digest and sha((OUTPUT / 'publication.json').read_bytes()) == publication
                and {p.name for p in OUTPUT.iterdir()} == {'started.json', 'inventory.json', 'publication.json'}, 'Final publication differs')
        return {'path': str(OUTPUT / 'inventory.json'), 'sha256': digest, 'publication_sha256': publication}
    except Exception as error:
        write_new(OUTPUT / 'failure.json', {'status': 'FAILED_DO_NOT_CONSUME', 'error': str(error), 'retry_allowed': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    if not parser.parse_args().execute:
        parser.error('Explicit --execute required')
    print(json.dumps(run(), indent=2))
