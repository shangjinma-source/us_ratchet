"""Immutable TSM conditional-evidence pointers; no inventory mutation or account call."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
SOURCE = Path(__file__).resolve()
OUTPUT = BASE / 'tsm_cash_inventory_binding_20261002_v1'
SID = 'security:incumbent_overlay:TSM'
ISSUER = 'issuer:0001046179'
GAP = 'DATED_IDENTITY_NOT_IN_BOUND_LANE_EVIDENCE'
SCHEMA = 'TSM_CASH_INVENTORY_CONDITIONAL_BINDING_V1'
BOUND = {
    'inventory': ('conditional_new_cash_inventory_20260925_v2/inventory.json', 'f8b88fc72c6a3906440d4ddc83b5614e2a0a009a8843603a6028b713f62cb626'),
    'publication': ('conditional_new_cash_inventory_20260925_v2/publication.json', 'e18344ff2535d4cea735d57e5d1c5cd99e60da98c8990040055b2bab48aa53a7'),
    'sidecar': ('tsm_incumbent_identity_20261002_v1/identity.json', '0bf3f51697fbf09966d6f20454c3a70552e97cbfe8f8bbbe6ad729f304eafbe9'),
    'sidecar_publication': ('tsm_incumbent_identity_20261002_v1/publication.json', 'a0dc16ce41f0930ed408b3aba0f4d63a37febec871dc8c14c7c49d281bcda236'),
}
CLOCK = [('2023-03-31', '2023-04-03'), ('2023-04-28', '2023-05-01'), ('2023-05-31', '2023-06-01'),
         ('2023-06-30', '2023-07-03'), ('2023-07-31', '2023-08-01'), ('2023-08-31', '2023-09-01')]
LANES = ('RETURN', 'BAD_TAIL', 'DRAWDOWN', 'LEGACY_TARGET_DISTANCE', 'INCUMBENT_ADD_ONLY_CONTROL', 'CASH_RETENTION_CONTROL')
FALSE = ('identity_gap_resolved', 'identity_interval_certified', 'provider_binding_verified', 'point_in_time_verified',
         'fork_executable', 'promotion_allowed', 'account_recomputed', 'old_source_closure_reaudited', 'inventory_rows_modified')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


LOADED = {str(SOURCE): digest(SOURCE.read_bytes())}


def encode(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def strict(sources):
    for path, sha in sources.items():
        require(digest(Path(path).read_bytes()) == sha, 'Source changed: ' + path)


def validate_sidecar(sidecar):
    fields = {'schema': 'TSM_INCUMBENT_CONDITIONAL_DATED_IDENTITY_V1', 'ticker': 'TSM',
              'security_id': SID, 'issuer_id': ISSUER, 'cusip': '874039100',
              'security_class': 'American Depositary Shares', 'fact_as_of': '2018-12-31',
              'report_date': '2018-12-31', 'filed_date': '2019-04-17',
              'evidence_available_date': '2019-04-18', 'fetched_at': '2026-07-14T17:38:21+00:00',
              'issuer_cik_binding_kind': 'SAVED_MANIFEST_AND_SEC_ARCHIVE_PATH_NOT_INLINE_FIELD'}
    require(all(sidecar.get(k) == v for k, v in fields.items()), 'Sidecar identity/date contract differs')
    require(type(sidecar.get('ordinary_shares_per_ads')) is int and sidecar['ordinary_shares_per_ads'] == 5, 'ADS fact ratio differs')
    for key in ('historical_2023_identity_interval_verified', 'point_in_time_verified', 'ndx_membership_verified',
                'price_identity_verified', 'holdings_conversion_performed', 'promotion_allowed', 'price_conversion_performed',
                'historical_2023_ads_ratio_verified', 'inline_cik_field_verified', 'local_evidence_available_in_2023_verified',
                'legal_identity_certified', 'corporate_action_completeness_verified', 'live_execution_authorized',
                'orders_generated', 'fit_performed', 'account_executed', 'old_audit_repeated'):
        require(sidecar.get(key) is False, 'Sidecar authority upgraded')
    require(type(sidecar.get('overlay_join_assumption')) is str and sidecar['overlay_join_assumption'].strip(), 'Missing conditional join explanation')
    require(type(sidecar.get('original_manifest')) is dict and type(sidecar.get('evidence')) in (dict, list), 'Missing preserved source evidence')
    require(set(sidecar.get('source_references', {})) == {'filing', 'manifest'}, 'Missing two source references')


def assemble(inventory, publication, sidecar, refs, sidecar_publication):
    require(set(refs) == set(BOUND), 'Exact input roles required')
    require(inventory['schema'] == 'CONDITIONAL_NEW_CASH_SIX_COORDINATE_INVENTORY_V2', 'Wrong inventory version')
    require(publication['schema'] == 'CONDITIONAL_CASH_INVENTORY_V2_PUBLICATION_RECEIPT_V1', 'Wrong publication schema')
    require(encode(publication['inventory_reference']) == encode(refs['inventory']), 'Publication inventory binding')
    require(encode(publication['source_hashes']) == encode(inventory['source_hashes']), 'Publication source map differs')
    require(publication['status'] == 'SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY' and publication['fork_executed'] is False, 'Publication status')
    for key in ('cash_fork_called', 'point_in_time_verified', 'promotion_allowed'):
        require(inventory[key] is False, 'Inventory permissions changed')
    validate_sidecar(sidecar)
    require(sidecar_publication['schema'] == 'TSM_CONDITIONAL_IDENTITY_PUBLICATION_V1'
            and sidecar_publication['status'] == 'PUBLISHED_CONDITIONAL_SID_SIDECAR_ONLY', 'Sidecar publication status')
    require(encode(sidecar_publication['identity_reference']) == encode(refs['sidecar']), 'Sidecar publication identity differs')
    require(encode(sidecar_publication['source_hashes']) == encode(sidecar['source_hashes']), 'Sidecar publication source map differs')
    require(type(inventory['branch_coordinate_count']) is int and inventory['branch_coordinate_count'] == 36 and len(inventory['rows']) == 36, '36 parent rows required')
    require(encode(inventory['decision_clock']) == encode([list(x) for x in CLOCK]), 'Six clock mismatch')
    rows, seen, count = [], set(), 0
    expected_tsm = {(lane, d, e) for lane in LANES for d, e in CLOCK if d != CLOCK[0][0] or lane == 'INCUMBENT_ADD_ONLY_CONTROL'}
    for ri, row in enumerate(inventory['rows']):
        coordinate = (row['lane'], row['decision_date'], row['execution_date'])
        require(coordinate in {(lane, d, e) for lane in LANES for d, e in CLOCK} and coordinate not in seen, 'Duplicate/unexpected row coordinate')
        seen.add(coordinate)
        require(row['fork_executable'] is False, 'Parent fork permission')
        ids = [s['security_id'] for s in row['securities']]
        require(len(ids) == len(set(ids)), 'Duplicate security row')
        require((SID in ids) == (coordinate in expected_tsm), 'TSM coordinate coverage changed')
        count += sum(s['gaps'].count(GAP) for s in row['securities'])
        require(encode(row['gaps']) == encode([{'security_id': s['security_id'], 'reason': g} for s in row['securities'] for g in s['gaps']]), 'Row gap projection mismatch')
        for si, sec in enumerate(row['securities']):
            if sec['security_id'] != SID:
                continue
            require(sec['gaps'] == [GAP] and sec['dated_identity_evidence'] == [], 'Original TSM gap/facts changed')
            require(sec['identity_interval_certified'] is False and sec['provider_binding_verified'] is False, 'TSM authority changed')
            require(type(sec['saved_coordinates']) is list and sec['saved_coordinates'], 'Missing TSM saved coordinates')
            for saved in sec['saved_coordinates']:
                require(saved['value']['ticker'] == 'TSM' and saved['value']['issuer_id'] == ISSUER, 'Saved TSM issuer/ticker mismatch')
            rows.append({'inventory_row_reference': dict(refs['inventory'], json_pointer=f'/rows/{ri}'),
                         'inventory_security_reference': dict(refs['inventory'], json_pointer=f'/rows/{ri}/securities/{si}'),
                         'original_security_row_sha256': digest(encode(sec)),
                         'lane': coordinate[0], 'decision_date': coordinate[1], 'execution_date': coordinate[2],
                         'security_id': SID, 'saved_issuer_id': ISSUER, 'saved_ticker': 'TSM',
                         'original_gaps_preserved': deepcopy(sec['gaps']), 'sidecar_reference': deepcopy(refs['sidecar']),
                         'association_reason': 'SAVED_OVERLAY_ISSUER_AND_TICKER_TO_DATED_ADS_FACT_CONDITIONAL_CROSS_SOURCE_JOIN',
                         'overlay_sid_replaced': False, 'shares_or_prices_rescaled': False, **{k: False for k in FALSE}})
    require(len(rows) == 31 and count == 155, '31 TSM bindings / 155 unchanged identity gaps required')
    return {'schema': SCHEMA, 'input_references': deepcopy(refs), 'binding_count': 31, 'original_identity_gap_count': 155,
            'remaining_original_identity_gap_count': 155, 'rows': rows, 'inventory_rows_copied': False,
            'evidence_scope': 'CONDITIONAL_DATED_ADS_FACT_ASSOCIATION_ONLY_NOT_LANE_ADMISSION', **{k: False for k in FALSE}}


def build():
    require(all(type(sha) is str and len(sha) == 64 for _, sha in BOUND.values()), 'Pending source anchor')
    strict(LOADED)
    refs = {k: {'path': str(BASE / path), 'sha256': sha} for k, (path, sha) in BOUND.items()}
    require({p.name for p in Path(refs['inventory']['path']).parent.iterdir()} == {'inventory.json', 'publication.json'}, 'Parent failed/orphan namespace')
    require({p.name for p in Path(refs['sidecar']['path']).parent.iterdir()} == {'identity.json', 'publication.json'}, 'Sidecar failed/orphan namespace')
    documents, sources = {}, dict(LOADED)
    for role, reference in refs.items():
        path, sha = reference['path'], reference['sha256']
        require(path not in sources or sources[path] == sha, 'Source conflict')
        raw = Path(path).read_bytes()
        require(digest(raw) == sha, 'Consumed bytes mismatch')
        sources[path] = sha
        documents[role] = json.loads(raw)
    result = assemble(**documents, refs=refs)
    strict(sources)
    result['source_hashes'] = sources
    return result


def durable(path, raw):
    with path.open('xb') as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def publish():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no retry')
    result = build()
    strict(result['source_hashes'])
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        raw = encode(result); path = OUTPUT / 'bindings.json'
        durable(path, raw)
        strict(result['source_hashes'])
        require(path.read_bytes() == raw and {p.name for p in OUTPUT.iterdir()} == {'bindings.json'}, 'Published bytes/namespace differs')
        return {'path': str(path), 'sha256': digest(raw)}
    except Exception as error:
        durable(OUTPUT / 'failure.json', encode({'status': 'FAILED_DO_NOT_CONSUME', 'error': str(error), 'retry_allowed': False}))
        raise


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    if not parser.parse_args().publish:
        parser.error('Explicit --publish required')
    print(json.dumps(publish(), indent=2))
