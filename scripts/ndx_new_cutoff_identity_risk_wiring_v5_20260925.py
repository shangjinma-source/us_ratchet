"""ORLY-only conditional identity and risk wiring; no historical facts or numerical columns rewritten."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
SOURCE=Path(__file__).resolve();BASE=SOURCE.parents[1]/'data/cache/research'
OUTPUT=BASE/'new_cutoff_identity_risk_wiring_20260925_v5/wiring.json'
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BOUND={
 'parent_wiring':('new_cutoff_identity_risk_wiring_20260925_v4/wiring.json','5169ebe6581b3673b7c30f06f7ca0f13acab17f56fb002b3c47e013341726f62'),
 'orly_declaration':('orly_conditional_identity_risk_20260925_v1/declaration.json','ff9a4a2548a833be786d79a8d968479b2f8ee443b182fb277621603dd8a40d95')}
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



COORDINATE=dict(ticker='ORLY',security_id='security:0000898173:67103H107',issuer_id='issuer:0000898173',
    cusip='67103H107',security_class='Common Stock')
WINDOW=dict(first='2026-03-20',last='2026-09-21')
SIDECARS=('original19_exact_proof','extended_provenance','v3_extended_provenance','v4_extended_provenance')


def validate_declaration(declaration):
    require(declaration['schema']=='ORLY_CONDITIONAL_DATED_IDENTITY_RISK_V1' and
        {k:declaration[k] for k in COORDINATE}==declaration['coordinate']==COORDINATE and declaration['risk_chain']=='automotive' and
        declaration['research_only'] is True and declaration['conditional_risk_chain_assigned'] is True,
        'Exact conditional ORLY declaration required')
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
        declaration['annual_fetched_at']=='2026-07-15T06:38:30+00:00' and
        declaration['form_received_at']=='2026-09-24T17:37:33.511356+00:00','Preserve late review and local receipts')
    require(all(x['decision_id']=='current:ORLY' and x['risk_chain']=='automotive' and
        x['status']=='accepted' and x['confidence']=='high' for x in (seed,review)), 'Saved research decision')
    require(review['security_ids']==['security:0000898173:current_ticker:ORLY'] and
        review['issuer_id']=='issuer:0000898173' and review['allow_fallback'] is False,
        'Original current_ticker decision must not masquerade as dated identity')
    visual=declaration['complete_visual_transcription'];capture=declaration['complete_capture_evidence']
    require(declaration['publication_date'] is None and declaration['publication_date_verified'] is False and
        declaration['action_or_signature_date_used_as_publication'] is False and
        declaration['action_date']==declaration['signature_date']=='2025-06-09','Action and signature are not publication')
    require(visual['publication_date'] is None and visual['publication_date_verified'] is False and
        visual['action_date']==visual['signature_date']=='2025-06-09' and
        visual['cusip_original_text']=='67103H 107' and visual['cusip']=='67103H107' and
        visual['visual_transcription_is_not_text_parser_output'] is True and
        visual['text_extraction_empty_by_page']==[True,True] and visual['ein_used_as_cik'] is False,
        'Explicit saved visual facts and non-parser boundary')
    require(capture['occ_local_pdf_available'] is False and capture['occ_failure_is_identity_source'] is False and
        type(capture['occ_receipt']['http_status']) is int and capture['occ_receipt']['http_status']==403 and
        type(capture['form_receipt']['http_status']) is int and capture['form_receipt']['http_status']==200 and
        capture['form_receipt']['received_at_utc']==declaration['form_received_at'],'Failed OCC is not memo evidence')
    old=declaration['original_faq_registry_event']
    require(old['ticker']=='ORLY' and old['cusip'] is None and old['publication_date'] is None,'Old FAQ null retained')
    manifest=declaration['annual_manifest']
    require(manifest['cik']=='0000898173' and manifest['accession_number']==review['accession_number']=='0000898173-26-000009' and
        manifest['fetched_at']==declaration['annual_fetched_at'] and manifest['content_sha256']==review['raw_sha256'] and
        manifest['research_only'] is True,'Saved annual source linkage')



def assemble(docs):
    old=docs['parent_wiring'];declaration=docs['orly_declaration']
    require(old['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V4' and all(old[k] is False for k in FALSE),
        'Conditional V4 parent required')
    rows=deepcopy(old['rows']);tickers=[r['ticker'] for r in rows]
    require(len(tickers)==len(set(tickers))==101 and tickers.count('ORLY')==1,'Complete101 parent rows')
    position=tickers.index('ORLY');row=rows[position];original=deepcopy(row)
    require(row['coordinate'] is None and row['risk_chain'] is None and row['new_assumption'] is None and
        row['complete_original_evidence']==[] and row['risk_sources']==[] and
        row['identity_risk_state']=='NOT_ASSEMBLED_FROM_THIS_BOUNDED_SOURCE_SET','Original ORLY unassembled state')
    require(all(row[k] is False for k in FALSE),'Original row authority')
    validate_declaration(declaration)
    calendar=old['calendar']
    require(len(calendar)==len(set(calendar))==127 and calendar==sorted(calendar) and
        dict(first=calendar[0],last=calendar[-1])==WINDOW and row['new_assumed_window']==WINDOW,'Preserved127 window')
    crwd=next(r for r in rows if r['ticker']=='CRWD')
    require(crwd['independent_channel_detail']['liquidity_status']=='BLOCKED_VOLUME_UNIT_UNKNOWN' and
        old['conditional_candidates_with_saved_volume_unit_block']==['CRWD'],'CRWD volume block retained')
    row['coordinate']=deepcopy(COORDINATE);row['risk_chain']='automotive'
    row['identity_risk_state']='DATED_COORDINATE_AND_CONDITIONAL_RISK_AVAILABLE_FOR_EXPLICIT_NEW_ASSUMPTION'
    row['new_assumption']=dict(scope='CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY',window=deepcopy(WINDOW),
        security_continuity_is_explicit_assumption=True,risk_label_persistence_is_explicit_assumption=True,
        cross_document_identity_connection_is_explicit_assumption=True,
        interval_certified=False,source_interval_extended=False,provider_binding_verified=False)
    row['risk_sources']=[dict(source=ref('orly_declaration'),source_kind='NEW_CONDITIONAL_DATED_IDENTITY_AND_SAVED_RISK_DECLARATION',
        risk_chain='automotive')]
    missing_gap='NO_DATED_COORDINATE_AND_RISK_ASSEMBLED_FROM_SELECTED_SOURCES'
    require(row['gaps'].count(missing_gap)==1,'Original unassembled gap required')
    row['gaps']=[g for g in row['gaps'] if g!=missing_gap]+[
        'SAVED_REVIEW_POSTDATES_WINDOW_START_NO_EARLY_AVAILABILITY_PROOF',
        'LOCAL_RECEIPTS_POSTDATE_WINDOW_START_NO_EARLY_POSSESSION_PROOF',
        'VISUAL_FORM_CUSIP_TO_ANNUAL_CIK_CONNECTION_IS_CONDITIONAL',
        'PUBLICATION_DATE_UNKNOWN_ACTION_AND_SIGNATURE_NOT_PUBLICATION']
    row['v5_extended_provenance_reference']=dict(json_pointer='/v5_extended_provenance/0')
    unchanged=[r for r in rows if r['ticker']!='ORLY'];before=[r for r in old['rows'] if r['ticker']!='ORLY']
    require(canonical(unchanged)==canonical(before),'Other100 rows must remain exact')
    candidates=[r for r in rows if r['coordinate'] is not None and r['risk_chain'] is not None]
    missing=[r for r in rows if r['coordinate'] is None]
    unassigned=[r for r in rows if r['coordinate'] is not None and r['risk_chain'] is None]
    issuers={r['coordinate']['issuer_id'] for r in candidates}
    require(len(candidates)==len({r['coordinate']['security_id'] for r in candidates})==24 and
        len(issuers)==23 and len(missing)==77 and not unassigned,'Derived24/23/77/0 denominator')
    value=deepcopy(old);value.pop('source_hashes',None)
    value.update(schema='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V5',rows=rows,
        input_references={k:ref(k) for k in BOUND},parent_v4_input_references=deepcopy(old['input_references']),
        parent_v4_other100_proof=dict(exact=old['unchanged_other100_exact'],sha256=old['unchanged_other100_sha256']),
        v5_extended_provenance=[dict(ticker='ORLY',original_row_reference=ref('parent_wiring','/rows/'+str(position)),
            original_row=original,increment_source=ref('orly_declaration'),complete_increment_evidence=deepcopy(declaration),
            new_window_assumption=deepcopy(row['new_assumption']),saved_review_selection_date=declaration['saved_review_selection_date'],
            saved_review_selection_postdates_window_start=True,early_window_review_availability_verified=False,
            early_window_local_evidence_available=False,publication_date=None,action_date='2025-06-09',signature_date='2025-06-09',
            action_or_signature_date_used_as_publication=False,identity_anchor_role='VISUALLY_TRANSCRIBED_ORGANIZATIONAL_ACTION_DATE_NOT_PUBLICATION_OR_JOINT_AVAILABILITY',prior_facts_modified=False,numerical_or_training_admission_inferred=False)],
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
