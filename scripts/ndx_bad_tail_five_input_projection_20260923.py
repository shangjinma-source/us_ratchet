"""Five-security subset of sealed conditional parents; no new prices or admission."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive

BASE = ROOT / 'data/cache/research'
SOURCE = Path(__file__).resolve()
OUTPUT = BASE / 'bad_tail_five_input_projection_20260923_v1/projection.json'
BOUND = {
    'price': ('return_eight_price_only_20260923_v1/raw_assembly.json', 'e1f00af594bfcb9a9c75b02493cf62fc64622e0b280ba2774346832b530b7336'),
    'price_final': ('return_eight_price_only_20260923_v1/finalization.json', '5f5714e66b906d02c33006e7b556177cd20945c0afca0a4d400df4e2073e2b9a'),
    'identity': ('return_eight_conditional_identity_20260923_v1/identities.json', '5f5bcbad2f5a3a340e0b3449b4b78ed55a44941d6402a4ee067dd779a4abaa6e'),
    'lane_prepare': ('cutoff_training_lanes_20260923_v2/prepare.json', 'b7eaff190f3b2225db87d14fd0f7afc0cd9420536e9a4661f986f8ac319a96ba'),
}
LOADED = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
          (SOURCE, archive.SOURCE, Path(archive.drift.__file__).resolve())}
CLOCK = [('2023-03-31', '2023-04-03'), ('2023-04-28', '2023-05-01'),
         ('2023-05-31', '2023-06-01'), ('2023-06-30', '2023-07-03'),
         ('2023-07-31', '2023-08-01'), ('2023-08-31', '2023-09-01')]
COORDINATES = {
    'AMAT': ('0000006951', '038222105', 'semiconductor_equipment'),
    'AVGO': ('0001730168', '11135F101', 'diversified_technology'),
    'BKR': ('0001701605', '05722G100', 'energy_technology'),
    'CDNS': ('0000813672', '127387108', 'eda_ip'),
    'FTNT': ('0001262039', '34959E109', 'cybersecurity'),
}
FALSE = ('new_http_performed', 'fit_performed', 'execution_performed', 'orders_generated',
         'execution_risk_chain_union_verified',
         'target_schedule_built', 'target_schedule_validity_verified', 'provider_binding_verified',
         'continuous_identity_interval_verified', 'historical_membership_verified',
         'exchange_calendar_completeness_verified', 'quote_basis_independently_authenticated',
         'corporate_action_completeness_verified', 'dividend_cash_flows_modelled',
         'historical_full_source_closure_verified', 'point_in_time_verified', 'promotion_allowed')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reference(role):
    path, digest = BOUND[role]
    return dict(path=str(BASE / path), sha256=digest)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def project(documents):
    price, identity, lanes = (documents[k] for k in ('price', 'identity', 'lane_prepare'))
    require(price['schema'] == 'RETURN_EIGHT_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1' and
            identity['schema'] == 'RETURN_EIGHT_CONDITIONAL_IDENTITY_ASSEMBLY_V1', 'Exact conditional parent schemas required')
    require(documents['price_final']['raw_reference'] == reference('price') and
            documents['price_final']['status'] == 'CONDITIONAL_RAW_PRICE_RECONSTRUCTION_PASSED', 'Parent price final linkage differs')
    for document in (price, identity):
        require(document['promotion_allowed'] is False and document['point_in_time_verified'] is False, 'Parent scope upgraded')
    require(identity['continuous_identity_interval_verified'] is False and identity['provider_price_binding_verified'] is False,
            'Conditional identity parent required')
    require(lanes['fit_performed'] is False and lanes['whole_lot_execution_performed'] is False and
            lanes['continuous_target_schedule_built'] is False and lanes['historical_account_outcomes_used_for_selection'] is False and
            lanes['promotion_allowed'] is False, 'Lane preparation scope upgraded')
    calendar = price['calendar']
    require(len(calendar) == 107 and calendar == sorted(set(calendar)) and
            (calendar[0], calendar[-1]) == ('2023-03-31', '2023-09-01'), 'Exact 107-session parent calendar required')
    require(identity['conditional_window'] == dict(start=calendar[0], end=calendar[-1]), 'Conditional parent window differs')
    all_labels = {r['security_id']: r for r in identity['rows']}
    require(len(all_labels) == len(identity['rows']) == 8, 'Complete eight-security identity parent required')
    require(len(price['tickers']) == price['ticker_count'] == 8 and price['session_count'] == 107 and
            price['price_cell_count'] == 1712 and set(price['tickers']) == {r['ticker'] for r in all_labels.values()}, 'Eight-security parent denominator differs')
    require([(d['cutoff'], d['execution_date']) for d in lanes['decisions']] == CLOCK, 'Exact six lane clocks required')
    choices, risk_chains, selected_sids = [], {}, set()
    for decision in lanes['decisions']:
        cutoff, execution = decision['cutoff'], decision['execution_date']
        require(calendar[calendar.index(cutoff) + 1] == execution, 'Execution must be next observed session')
        candidates = decision['lanes']['BAD_TAIL']
        require(len(candidates) == 1, 'Unique observed BAD_TAIL candidate required; no tie resolution here')
        candidate = candidates[0]
        selected = candidate['selected']
        require(candidate['holding_count'] == len(selected) == 4 and
                len({v['issuer_id'] for v in selected.values()}) == 4, 'Actual selected count or issuer uniqueness differs')
        require(set(candidate['tickers'].split(';')) == {v['ticker'] for v in selected.values()}, 'Candidate ticker list differs')
        for sid, selection in selected.items():
            ticker = selection['ticker']
            require(ticker in COORDINATES, 'Unexpected BAD_TAIL security')
            cik, cusip, chain = COORDINATES[ticker]
            require(sid == f'security:{cik}:{cusip}' and selection['issuer_id'] == f'issuer:{cik}' and
                    selection['risk_chain'] == chain, 'Saved SID/issuer/risk chain differs')
            label = all_labels[sid]
            require((label['ticker'], label['subject_cik'], label['cusip'], label['issuer_id']) ==
                    (ticker, cik, cusip, selection['issuer_id']), 'Parent identity coordinate differs')
            selected_sids.add(sid)
        risk_chains[cutoff] = {sid: v['risk_chain'] for sid, v in selected.items()}
        choices.append(dict(decision_date=cutoff, execution_date=execution, saved_candidate=deepcopy(candidate),
                            queue_reference=deepcopy(decision['queue_reference']), target_weights_materialized=False))
    labels = [deepcopy(all_labels[sid]) for sid in sorted(selected_sids)]
    require(len(labels) == 5 and {r['ticker'] for r in labels} == set(COORDINATES) and
            len({r['issuer_id'] for r in labels}) == 5, 'Exact five security / five issuer union required')
    tickers = sorted(COORDINATES)
    matrices = {}
    for kind in ('open', 'close'):
        parent = price['matrices'][kind]
        require(set(parent) == set(calendar), 'Parent matrix dates differ')
        matrices[kind] = {}
        for day in calendar:
            require(set(parent[day]) == set(price['tickers']), 'Incomplete parent matrix row')
            matrices[kind][day] = {}
            for ticker in tickers:
                value = parent[day][ticker]
                require(type(value) is str and Decimal(value).is_finite() and Decimal(value) > 0, 'Positive exact Decimal string required')
                matrices[kind][day][ticker] = value
    channels = [deepcopy(row) for row in price['channels'] if row['ticker'] in COORDINATES]
    require(len(channels) == 5 and {r['ticker'] for r in channels} == set(tickers) and
            all([r['session'] for r in c['rows']] == calendar for c in channels), 'Complete five inherited channel calendars required')
    return dict(schema='BAD_TAIL_FIVE_SECURITY_107_SESSION_INPUT_PROJECTION_V1', lane='BAD_TAIL',
        parent_references={role: reference(role) for role in BOUND}, calendar=deepcopy(calendar),
        observed_decision_clock=[list(pair) for pair in CLOCK], saved_lane_choices=choices,
        selected_risk_chains_by_decision=risk_chains, security_count=5, distinct_issuer_count=5,
        price_projection=dict(tickers=tickers, ticker_count=5, session_count=107, price_cell_count=1070,
            matrices=matrices, channels=channels, parent_price_reference=reference('price'),
            matrix_value_encoding=price['matrix_value_encoding'], nominal_price_status=price['nominal_price_status'],
            calendar_status=price['calendar_status'], source_mode='EXACT_SUBSET_OF_SEALED_CONDITIONAL_PARENT'),
        identity_projection=dict(rows=labels, conditional_window=deepcopy(identity['conditional_window']),
            interval_stability_assumption=identity['interval_stability_assumption'],
            parent_identity_reference=reference('identity'), parent_schedule_binding_reused_as_bad_tail_admission=False,
            evidence_scope='PARENT_DATED_FACTS_AND_107_DAY_CONDITIONAL_ASSUMPTION_ONLY'),
        downstream_status='TARGET_SCHEDULE_NOT_YET_MATERIALIZED_OR_VERIFIED',
        fixed_four_security_policy=False, original_parent_assets_modified=False, **dict.fromkeys(FALSE, False))


def build():
    archive.strict(LOADED)
    sources, documents = dict(LOADED), {}
    for role in BOUND:
        ref = reference(role)
        raw = Path(ref['path']).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'Hard parent bytes differ')
        archive.merge(sources, {ref['path']: ref['sha256']})
        documents[role] = json.loads(raw, object_pairs_hook=unique)
        for key in ('source_hashes', 'historical_expected_source_hashes', 'prepare_source_hashes'):
            if key in documents[role]: archive.merge(sources, documents[role][key])
    contract = archive.load_contract()
    resolution = archive.verify_expected_sources(sources, contract)
    result = project(documents)
    require(archive.verify_expected_sources(sources, contract) == resolution, 'Sources changed during projection')
    return dict(result, historical_expected_source_hashes=sources, archive_resolution=resolution)


def publish():
    require(not OUTPUT.parent.exists(), 'Fresh fixed projection namespace required')
    value = build()
    contract = archive.load_contract()
    def verify():
        require(archive.verify_expected_sources(value['historical_expected_source_hashes'], contract) == value['archive_resolution'], 'Publication source drift')
    verify()
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    OUTPUT.parent.mkdir(parents=True, exist_ok=False)
    with OUTPUT.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    verify()
    require(OUTPUT.read_bytes() == raw, 'Published projection differs')
    return dict(path=str(OUTPUT), sha256=hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    print(json.dumps(publish()))
