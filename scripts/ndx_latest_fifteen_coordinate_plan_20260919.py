"""Source-bound proposal only: reuse adjudicated coordinates, never mint CIK/CUSIP joins."""
import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
INVENTORY = BASE / 'latest_security_source_inventory_20260919_v1/inventory_with_events_draft.json'
INVENTORY_SHA = 'b89100d2147d5879a8e0cd19134a4cf27632dcd7ddc700626ba8bb501a5f81c8'
TICKERS = 'AMAT LRCX FAST ODFL AMZN ADI CDNS NFLX DXCM AVGO FTNT PANW GOOG BKR CRWD'.split()
REUSABLE = {'AMAT', 'ADI', 'CDNS', 'AVGO', 'FTNT', 'GOOG', 'BKR'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

LOADED = {str(Path(__file__).resolve()): sha(__file__)}


def merge_sources(target, incoming):
    for path, expected in incoming.items():
        path = str(Path(path).resolve())
        if path in target and target[path] != expected:
            raise ValueError('Conflicting source SHA')
        target[path] = expected


def verify(sources):
    for path, expected in {**sources, **LOADED}.items():
        if path in sources and path in LOADED and sources[path] != LOADED[path]:
            raise ValueError('Loaded source hash differs')
        if sha(path) != expected:
            raise ValueError('Source bytes differ: ' + path)


def canonical(value):
    return json.dumps(value,sort_keys=True,allow_nan=False)


def row_plan(row):
    ticker = row['ticker']
    if ticker not in TICKERS or row['fit127_date_coverage_only'] is not True:
        raise ValueError('Exact proposed cohort and date coverage required')
    if sha(INVENTORY) != INVENTORY_SHA:
        raise ValueError('Hard inventory differs')
    original = [r for r in json.loads(INVENTORY.read_text(encoding='utf-8'))['rows'] if r['ticker']==ticker]
    if len(original)!=1 or canonical(original[0])!=canonical(row):
        raise ValueError('Dated class, issuer, source and risk facts must equal hard inventory')
    facts = row['dated_security_fact_candidates']
    coordinates = set()
    for wrapped in facts:
        fact = wrapped['fact']
        if wrapped['source'] not in ('four', 'seven'):
            raise ValueError('Unsupported dated coordinate authority')
        cik = fact.get('issuer_cik', fact.get('subject_cik'))
        if fact['ticker'] != ticker or 'issuer:' + cik != row['current_issuer_id']:
            raise ValueError('Conflicting dated issuer; no ticker-only join')
        coordinate = fact.get('security_id')
        if coordinate != 'security:' + cik + ':' + fact['cusip']:
            raise ValueError('Existing adjudicated coordinate differs')
        if not fact.get('security_class', fact.get('security_class_cover')):
            raise ValueError('Explicit dated class required')
        coordinates.add(coordinate)
    if len(coordinates) > 1 or bool(coordinates) != (ticker in REUSABLE):
        raise ValueError('Expected existing coordinate set differs')
    action_facts = copy.deepcopy(row['dated_action_document_candidates'])
    cusips = sorted({x['fact']['cusip'] for x in action_facts if x['fact'].get('cusip')})
    chains = sorted(set(row['historical_conditional_business_chain_candidates'] + row['historical_original_risk_labels']))
    if len(chains) != 1:
        raise ValueError('Do not silently resolve historical risk conflicts')
    gaps = ['LATEST_20260318_20260917_SECURITY_CONTINUITY_IS_UNVERIFIED',
            'PROVIDER_CHANNEL_TO_SECURITY_BINDING_UNVERIFIED',
            'HISTORICAL_RISK_CHAIN_LATEST_VALIDITY_UNVERIFIED', 'POINT_IN_TIME_MEMBERSHIP_UNVERIFIED']
    if not coordinates:
        gaps.append('ACTION_CUSIP_TO_SEC_SUBJECT_CIK_AND_CLASS_ADJUDICATION_REQUIRED')
    if ticker == 'LRCX':
        if cusips != ['512807306']:
            raise ValueError('Explicit post-action LRCX CUSIP required')
        gaps.append('POST_20241003_ONLY_NO_OLD_CUSIP_STITCHING')
    if ticker == 'CRWD':
        gaps.append('LIQUIDITY_BLOCKED_RETURNED_SPLIT_20260702_IN_63_SESSION_WINDOW')
    return dict(ticker=ticker, current_issuer_id=row['current_issuer_id'],
        proposed_reused_security_id=next(iter(coordinates)) if coordinates else None,
        proposed_new_security_id=None,
        status='EXISTING_DATED_COORDINATE_REUSE_PROPOSAL' if coordinates else 'HOLD_EXACT_ISSUER_CLASS_LINK_REQUIRED',
        dated_coordinate_facts=copy.deepcopy(facts), action_document_facts=action_facts,
        candidate_action_cusips=cusips,
        risk_chain_candidate=chains[0],
        risk_source_kind='INDEPENDENT_REVIEWED_DATED_BUSINESS' if row['historical_conditional_business_chain_candidates'] else 'LEGACY_LOCAL_RISK_LABEL_NOT_NEW_ADJUDICATION',
        risk_document_ids=row['historical_business_document_ids'],
        fit_price_window={'first':'2026-03-18','last':'2026-09-17','prices':127,'returns':126},
        proposed_continuity_assumption='Same explicitly dated security/class persists across this latest window; assumption not verified or authorized by this plan.',
        liquidity_status='BLOCKED_VOLUME_UNIT_UNKNOWN' if ticker=='CRWD' else 'NOT_ADJUDICATED_BY_COORDINATE_PLAN',
        gaps=gaps, identity_assumption_approved=False, risk_assumption_approved=False,
        channel_producer_execution_authorized=False, legal_training_input_ready=False,
        point_in_time_verified=False, promotion_allowed=False)


def build():
    if sha(INVENTORY) != INVENTORY_SHA:
        raise ValueError('Hard inventory differs')
    inventory = json.loads(INVENTORY.read_text(encoding='utf-8'))
    sources = dict(LOADED)
    merge_sources(sources,{str(INVENTORY):INVENTORY_SHA})
    merge_sources(sources,inventory['sources'])
    verify(sources)
    indexed = {r['ticker']:r for r in inventory['rows']}
    rows = [row_plan(indexed[t]) for t in TICKERS]
    # Bind actual action raw bytes and original annual cover bytes, not just tickers.
    for row in rows:
        for wrapped in row['action_document_facts']:
            fact = wrapped['fact']
            merge_sources(sources,{fact['raw_path']:fact['raw_sha256']})
            if fact.get('identity_evidence'):
                evidence = fact['identity_evidence']
                merge_sources(sources,{evidence['raw_path']:evidence['raw_sha256']})
    verify(sources)
    return dict(schema='LATEST_FIFTEEN_CONDITIONAL_COORDINATE_PLAN_V1', rows=rows,
        source_hashes=sources, source_scope='Sealed adjudication reports and directly referenced raw bytes; recursive historical provenance is not re-certified.',
        counts={'planned':15,'existing_coordinate_reuse_proposals':7,'held_exact_link':8,
                'new_coordinate_ids':0,'approved_for_training':0},
        minimal_expansion_beyond_four=['ADI','FTNT','BKR'],
        proposed_first_research_subset=[t for t in TICKERS if t in REUSABLE],
        fit_performed=False, prices_rebuilt=False, point_in_time_verified=False, promotion_allowed=False)


def publish_verified(value,output):
    verify(value['source_hashes'])
    output=Path(output)
    descriptor,name=tempfile.mkstemp(prefix=output.name+'.',suffix='.tmp',dir=output.parent)
    temporary=Path(name)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as handle:
            json.dump(value,handle,ensure_ascii=True,indent=2,allow_nan=False)
            handle.flush();os.fsync(handle.fileno())
        os.link(temporary,output)
        verify(value['source_hashes'])
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    output = BASE / 'latest_security_source_inventory_20260919_v1/fifteen_coordinate_plan.json'
    value = build()
    publish_verified(value,output)
    print(json.dumps(dict(path=str(output),sha256=sha(output),counts=value['counts'])))
