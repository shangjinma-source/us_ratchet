"""CTAS-only conditional identity and risk wiring; no historical facts or numerical columns rewritten."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
SOURCE=Path(__file__).resolve();BASE=SOURCE.parents[1]/'data/cache/research'
OUTPUT=BASE/'new_cutoff_identity_risk_wiring_20260925_v6/wiring.json'
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BOUND={
 'parent_wiring':('new_cutoff_identity_risk_wiring_20260925_v5/wiring.json','4889b642f2700256487eaf2753d303f1a35dbb6941c1080a0b7eca0ec51e1636'),
 'ctas_declaration':('ctas_conditional_identity_risk_20260925_v1/declaration.json','cd06a401f62955e8b1984d69e8033e86ead719b545ff5946b3ae1621ddfbd849')}
FALSE=('identity_interval_verified','provider_binding_verified','risk_interval_verified','point_in_time_verified','historical_membership_verified',
 'complete_corporate_actions_verified','legal_training_input_admitted','promotion_allowed','fit_performed','execution_authorized','http_performed',
 'prices_recomputed','old_build_called','original_windows_extended','full_transitive_source_closure_reverified')

def require(ok,message):
    if not ok:raise ValueError(message)


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def encode(v):return (json.dumps(v,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def ref(role,pointer=None):
    p,h=BOUND[role];r=dict(path=str(BASE/p),sha256=h)
    if pointer is not None:r['json_pointer']=pointer
    return r


def loads(raw):
    def unique(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    def fail(v):raise ValueError('Nonfinite JSON')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=fail)


def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source changed')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Bound source changed')



COORDINATE=dict(ticker='CTAS',security_id='security:0000723254:172908105',issuer_id='issuer:0000723254',
    cusip='172908105',security_class='Common stock, no par value')
WINDOW=dict(first='2026-03-20',last='2026-09-21')
SIDECARS=('original19_exact_proof','extended_provenance','v3_extended_provenance','v4_extended_provenance','v5_extended_provenance')


def validate_declaration(declaration):
    require(declaration['schema']=='CTAS_CONDITIONAL_DATED_IDENTITY_RISK_V1' and
        {k:declaration[k] for k in COORDINATE}==declaration['coordinate']==COORDINATE and declaration['risk_chain']=='industrial' and
        declaration['research_only'] is True and declaration['conditional_risk_chain_assigned'] is True,
        'Exact conditional CTAS declaration required')
    require(declaration['assumed_window']==WINDOW and type(declaration['new_window_assumption']) is str and
        declaration['new_window_assumption'].strip(),'Exact new assumed window and explicit assumption')
    for key in ('point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized',
                'early_window_review_availability_verified','early_window_local_evidence_available',
                'direct_single_document_cusip_cik_proof','identity_interval_verified','risk_interval_verified',
                'provider_binding_verified','complete_corporate_actions_verified','option_contract_terms_used_as_equity_identity'):
        require(declaration[key] is False,'Declaration authority or early availability upgrade')
    review=declaration['saved_review_decision'];seed=declaration['saved_seed_decision']
    require(declaration['saved_review_selection_postdates_window_start'] is True and
        declaration['saved_review_selection_date']==review['selection_date']=='2026-07-13' and
        declaration['annual_fetched_at']=='2026-07-15T06:38:08+00:00' and
        declaration['memo_received_at']=='2026-09-24T18:15:56.892204+00:00','Preserve late review and local receipts')
    require(all(x['decision_id']=='current:CTAS' and x['risk_chain']=='industrial' and
        x['status']=='accepted' and x['confidence']=='high' for x in (seed,review)), 'Saved research decision')
    require(review['security_ids']==['security:0000723254:current_ticker:CTAS'] and
        review['issuer_id']=='issuer:0000723254' and review['allow_fallback'] is False,
        'Original current_ticker decision must not masquerade as dated identity')
    memo=declaration['complete_memo_evidence'];capture=declaration['complete_capture_evidence']
    require(memo['publication_date']=='2024-08-21' and
        memo['publication_date_role']=='MEMORANDUM_PRINTED_DATE_NOT_LOCAL_AVAILABILITY' and
        memo['cusip']=='172908105' and memo['security_class_in_memo']=='Common Shares' and
        memo['page_count']==4 and memo['page_number']==1 and memo['disclaimer_page']==3 and
        memo['unofficial_summary'] is True and memo['option_deliverable_is_not_equity_identity_proof'] is True,
        'Printed memorandum date is not joint availability')
    require(capture['strict_single_part_payload_exact'] is True and capture['original_body_is_pdf_without_multipart'] is False and
        type(capture['original_receipt']['http_status']) is int and capture['original_receipt']['http_status']==200 and
        capture['original_receipt']['received_at_utc']==declaration['memo_received_at'] and
        capture['original_extraction']['part_count']==1 and capture['original_extraction']['payload_start_offset']==195 and
        capture['original_extraction']['network_repeated'] is False and capture['original_extraction']['raw_modified'] is False,
        'Complete saved multipart and derived chain')
    old=declaration['registry_event']
    require(declaration['registry_event_pointer']=='/events/6' and old['ticker']=='CTAS' and old['cusip'] is None and old['publication_date'] is None,'Old registry null retained')
    manifest=declaration['annual_manifest']
    require(manifest['cik']=='0000723254' and manifest['accession_number']==review['accession_number']=='0000723254-25-000017' and
        manifest['fetched_at']==declaration['annual_fetched_at'] and manifest['content_sha256']==review['raw_sha256'] and
        manifest['research_only'] is True,'Saved annual source linkage')



def assemble(docs):
    old=docs['parent_wiring'];declaration=docs['ctas_declaration']
    require(old['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V5' and all(old[k] is False for k in FALSE),
        'Conditional V5 parent required')
    rows=deepcopy(old['rows']);tickers=[r['ticker'] for r in rows]
    require(len(tickers)==len(set(tickers))==101 and tickers.count('CTAS')==1,'Complete101 parent rows')
    position=tickers.index('CTAS');row=rows[position];original=deepcopy(row)
    require(row['coordinate'] is None and row['risk_chain'] is None and row['new_assumption'] is None and
        row['complete_original_evidence']==[] and row['risk_sources']==[] and
        row['identity_risk_state']=='NOT_ASSEMBLED_FROM_THIS_BOUNDED_SOURCE_SET','Original CTAS unassembled state')
    require(all(row[k] is False for k in FALSE),'Original row authority')
    validate_declaration(declaration)
    calendar=old['calendar']
    require(len(calendar)==len(set(calendar))==127 and calendar==sorted(calendar) and
        dict(first=calendar[0],last=calendar[-1])==WINDOW and row['new_assumed_window']==WINDOW,'Preserved127 window')
    crwd=next(r for r in rows if r['ticker']=='CRWD')
    require(crwd['independent_channel_detail']['liquidity_status']=='BLOCKED_VOLUME_UNIT_UNKNOWN' and
        old['conditional_candidates_with_saved_volume_unit_block']==['CRWD'],'CRWD volume block retained')
    row['coordinate']=deepcopy(COORDINATE);row['risk_chain']='industrial'
    row['identity_risk_state']='DATED_COORDINATE_AND_CONDITIONAL_RISK_AVAILABLE_FOR_EXPLICIT_NEW_ASSUMPTION'
    row['new_assumption']=dict(scope='CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY',window=deepcopy(WINDOW),
        security_continuity_is_explicit_assumption=True,risk_label_persistence_is_explicit_assumption=True,
        cross_document_identity_connection_is_explicit_assumption=True,
        interval_certified=False,source_interval_extended=False,provider_binding_verified=False)
    row['risk_sources']=[dict(source=ref('ctas_declaration'),source_kind='NEW_CONDITIONAL_DATED_IDENTITY_AND_SAVED_RISK_DECLARATION',
        risk_chain='industrial')]
    missing_gap='NO_DATED_COORDINATE_AND_RISK_ASSEMBLED_FROM_SELECTED_SOURCES'
    require(row['gaps'].count(missing_gap)==1,'Original unassembled gap required')
    row['gaps']=[g for g in row['gaps'] if g!=missing_gap]+[
        'SAVED_REVIEW_POSTDATES_WINDOW_START_NO_EARLY_AVAILABILITY_PROOF',
        'LOCAL_RECEIPTS_POSTDATE_WINDOW_START_NO_EARLY_POSSESSION_PROOF',
        'MEMO_CUSIP_TO_ANNUAL_CIK_CONNECTION_IS_CONDITIONAL',
        'PRINTED_MEMO_DATE_IS_NOT_JOINT_AVAILABILITY_OR_LOCAL_RECEIPT']
    row['v6_extended_provenance_reference']=dict(json_pointer='/v6_extended_provenance/0')
    unchanged=[r for r in rows if r['ticker']!='CTAS'];before=[r for r in old['rows'] if r['ticker']!='CTAS']
    require(canonical(unchanged)==canonical(before),'Other100 rows must remain exact')
    candidates=[r for r in rows if r['coordinate'] is not None and r['risk_chain'] is not None]
    missing=[r for r in rows if r['coordinate'] is None]
    unassigned=[r for r in rows if r['coordinate'] is not None and r['risk_chain'] is None]
    issuers={r['coordinate']['issuer_id'] for r in candidates}
    require(len(candidates)==len({r['coordinate']['security_id'] for r in candidates})==25 and
        len(issuers)==24 and len(missing)==76 and not unassigned,'Derived25/24/76/0 denominator')
    value=deepcopy(old);value.pop('source_hashes',None)
    value.update(schema='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V6',rows=rows,
        input_references={k:ref(k) for k in BOUND},parent_v5_input_references=deepcopy(old['input_references']),
        parent_v5_other100_proof=dict(exact=old['unchanged_other100_exact'],sha256=old['unchanged_other100_sha256']),
        v6_extended_provenance=[dict(ticker='CTAS',original_row_reference=ref('parent_wiring','/rows/'+str(position)),
            original_row=original,increment_source=ref('ctas_declaration'),complete_increment_evidence=deepcopy(declaration),
            new_window_assumption=deepcopy(row['new_assumption']),saved_review_selection_date=declaration['saved_review_selection_date'],
            saved_review_selection_postdates_window_start=True,early_window_review_availability_verified=False,
            early_window_local_evidence_available=False,publication_date='2024-08-21',
            annual_fetched_at=declaration['annual_fetched_at'],memo_received_at=declaration['memo_received_at'],
            printed_memo_date_is_not_joint_availability=True,identity_anchor_role='MEMORANDUM_PRINTED_DATE_NOT_JOINT_AVAILABILITY',prior_facts_modified=False,numerical_or_training_admission_inferred=False)],
        unchanged_other100_exact=True,unchanged_other100_sha256=sha(canonical(unchanged)),
        candidate_security_count=len(candidates),candidate_issuer_count=len(issuers),bounded_source_missing_count=len(missing),
        dated_coordinate_risk_unassigned_count=0,candidate_count_is_not_fit_column_count=True,
        fit_column_count=None,typed_panel_rebuilt=False)
    require(all(canonical(value[k])==canonical(old[k]) for k in SIDECARS),'All prior sidecars preserved')
    return value

def build():
    require(all(type(h) is str and len(h)==64 for p,h in BOUND.values()),'Saved declaration hard SHA pending')
    sources={str(SOURCE):LOADED_SHA};guard(sources);docs={}
    for role in BOUND:
        r=ref(role);raw=Path(r['path']).read_bytes();require(sha(raw)==r['sha256'],'Consumed parent hash')
        sources[r['path']]=r['sha256'];docs[role]=loads(raw)
    value=assemble(docs);value['source_hashes']=sources;guard(sources);return value


def publish():
    require(not OUTPUT.parent.exists(),'Fixed namespace already exists')
    value=build();guard(value['source_hashes']);raw=encode(value)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw,'Output bytes changed')
    require({p.name for p in OUTPUT.parent.iterdir()}=={'wiring.json'},'Unexpected namespace file')
    return dict(path=str(OUTPUT),sha256=sha(raw))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');a=p.parse_args()
    require(a.publish,'Explicit --publish required');print(json.dumps(publish()))
