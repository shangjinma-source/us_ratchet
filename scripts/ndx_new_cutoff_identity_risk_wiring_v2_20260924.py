"""Two-row reference increment; old nineteen rows and numerical evidence stay unchanged."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
SOURCE=Path(__file__).resolve();BASE=SOURCE.parents[1]/'data/cache/research'
OUTPUT=BASE/'new_cutoff_identity_risk_wiring_20260924_v2/wiring.json'
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BOUND={
 'original_wiring':('new_cutoff_identity_risk_wiring_20260923_v1/wiring.json','29da295126a93b842928d8df21142bcb846fc617b71886b2fb04507ff4adf3b4'),
 'pcar_adjudication':('pcar_conditional_risk_adjudication_20260924_v1/adjudication.json','51fdca5cd417d3591a8ad13a977596cf5d30c921943dd8a6c09a0b03aa1810a0'),
 'crwd_identity':('crwd_conditional_identity_20260923_v1/identity.json','a8c85fe6f9f2151c0d53f342769161027817479682672f29e9f45e82df1ee518'),
 'channels':('new_cutoff_conditional_channels_20260923_v1/channels.json','3d708df6b273616edd46e06d2e2976acbc0e9fd90cc1243679ff94ca8befa3ac'),
 'audit':('new_cutoff_conditional_channels_20260923_v1/independent_raw_decimal_audit.json','a11e7fb3b9006eba71b9d254557f713a32b2615407c9b8f77e7b24a8c01a2ace'),
}
OLD_STATE='DATED_COORDINATE_AND_LEGACY_RISK_AVAILABLE_FOR_EXPLICIT_NEW_ASSUMPTION'
NEW_STATE='DATED_COORDINATE_AND_CONDITIONAL_RISK_AVAILABLE_FOR_EXPLICIT_NEW_ASSUMPTION'
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


def assemble(docs):
    old,p,c,channels,audit=(docs[k] for k in ('original_wiring','pcar_adjudication','crwd_identity','channels','audit'))
    require(old['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V1','Original schema')
    require(all(old[k] is False for k in FALSE),'Original permissions')
    require(all(d['promotion_allowed'] is False for d in docs.values()),'Parent promotion')
    require(old['input_references']['channels']==ref('channels') and old['input_references']['audit']==ref('audit') and audit['candidate_reference']==ref('channels'),'Numerical source binding')
    require(audit['status']=='PASSED' and type(audit['completed']) is int and audit['completed']==101,'Complete saved audit')
    calendar=old['calendar'];window=dict(first=calendar[0],last=calendar[-1])
    require(calendar==channels['calendar']==c['calendar'] and len(calendar)==127 and calendar==sorted(set(calendar)) and window=={'first':'2026-03-20','last':'2026-09-21'},'Exact existing window')
    tickers=[r['ticker'] for r in old['rows']]
    require(len(tickers)==len(set(tickers))==101 and [r['ticker'] for r in channels['rows']]==[r['ticker'] for r in audit['details']]==tickers,'101 numerical order')
    original19=[r for r in old['rows'] if r['identity_risk_state']==OLD_STATE]
    require(len(original19)==19 and len({r['coordinate']['issuer_id'] for r in original19})==18,'Original19/18 denominator')
    rows=deepcopy(old['rows']);by={r['ticker']:r for r in rows}
    for i,(row,ch,detail) in enumerate(zip(rows,channels['rows'],audit['details'])):
        require(row['channel_reference']==ref('channels','/rows/'+str(i)) and row['channel_audit_reference']==ref('audit','/details/'+str(i)),'Channel row pointer')
        require(row['channel_row_sha256']==sha(encode(ch)) and row['independent_channel_detail']==detail,'Saved exact numeric evidence')
    require(p['schema']=='PCAR_CONDITIONAL_RISK_ADJUDICATION_V1' and p['ticker']=='PCAR' and p['issuer_id']=='issuer:0000075362'
      and p['conditional_assigned_risk_chain']=='automotive' and p['conditional_classification_adopted'] is True
      and p['future_window_use_requires_explicit_stability_assumption'] is True and p['new_window'] is None,'PCAR conditional judgment')
    for key in ('classification_uniquely_proven','current_interval_verified','identity_interval_verified','provider_binding_verified','point_in_time_verified','legal_training_input_admitted','live_execution_authorized','cprt_classification_adjudicated','existing_facts_or_wiring_modified'):
        require(p[key] is False,'PCAR authority upgrade')
    pr=by['PCAR'];require(pr['risk_chain'] is None and pr['risk_sources']==[] and pr['identity_risk_state']=='DATED_COORDINATE_RISK_UNASSIGNED','PCAR original risk null')
    fact=pr['complete_original_evidence'][0]['complete_original_fact']
    require(fact['risk_chain'] is None and fact['risk_chain_assigned'] is False and fact['issuer_id']==p['issuer_id'],'Preserved null-risk facts')
    require(pr['coordinate']==dict(ticker='PCAR',security_id='security:0000075362:693718108',issuer_id='issuer:0000075362',cusip='693718108',security_class='Common Stock, $1 par value'),'PCAR dated coordinate')
    require(c['schema']=='CRWD_CONDITIONAL_DATED_IDENTITY_V1' and c['ticker']=='CRWD' and c['subject_cik']=='0001535527'
      and c['security_id']=='security:0001535527:22788C105' and c['issuer_id']=='issuer:0001535527' and c['cusip']=='22788C105'
      and c['security_class']=='CLASS_A_COMMON' and c['risk_chain']=='cybersecurity','CRWD exact dated coordinate')
    for key in ('evidence_available_before_window_start','latest_security_interval_verified','classification_valid_interval_verified','provider_security_binding_verified','point_in_time_verified','volume_unit_verified','legal_training_input_ready','execution_authorized'):
        require(c[key] is False,'CRWD authority upgrade')
    require(c['memo_publication_date']=='2026-06-09' and calendar[0]<c['memo_publication_date']<=calendar[-1]
      and c['volume_status']=='BLOCKED_VOLUME_UNIT_UNKNOWN','CRWD late memo/volume boundary')
    require(c['input_references']['channels']==ref('channels') and c['input_references']['audit']==ref('audit'),'CRWD parent numeric refs')
    cr=by['CRWD'];require(cr['coordinate'] is None and cr['risk_chain'] is None,'CRWD original unassembled')
    require(cr['independent_channel_detail']['liquidity_status']=='BLOCKED_VOLUME_UNIT_UNKNOWN' and 'SAVED_VOLUME_UNIT_RESTRICTION_RETAINED' in cr['gaps'],'CRWD volume remains blocked')
    extensions=[]
    for ticker,role,chain,remove in [('PCAR','pcar_adjudication','automotive','NO_BUSINESS_RISK_CLASSIFICATION_ADJUDICATED'),('CRWD','crwd_identity','cybersecurity','NO_DATED_COORDINATE_AND_RISK_ASSEMBLED_FROM_SELECTED_SOURCES')]:
        row=by[ticker];original=deepcopy(row);source=docs[role]
        if ticker=='CRWD':row['coordinate']={k:c[k] for k in ('security_id','issuer_id','ticker','cusip','security_class')}
        row['risk_chain']=chain;row['identity_risk_state']=NEW_STATE
        row['new_assumption']=dict(scope='CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY',window=deepcopy(window),
          security_continuity_is_explicit_assumption=True,risk_label_persistence_is_explicit_assumption=True,
          interval_certified=False,source_interval_extended=False,provider_binding_verified=False)
        row['risk_sources']=[dict(source=ref(role),source_kind='NEW_CONDITIONAL_ANALYST_JUDGMENT' if ticker=='PCAR' else 'HISTORICAL_REVIEWED_BUSINESS_MATCH_WITH_CROSS_DOCUMENT_IDENTITY',risk_chain=chain)]
        row['gaps']=[g for g in row['gaps'] if g!=remove]
        if ticker=='CRWD':row['gaps'].append('DATED_MEMO_POSTDATES_WINDOW_START_NO_EARLY_AVAILABILITY_PROOF')
        row['extended_provenance_reference']=dict(json_pointer='/extended_provenance/'+str(len(extensions)))
        extensions.append(dict(ticker=ticker,original_row_reference=ref('original_wiring','/rows/'+str(tickers.index(ticker))),
          original_row=original,increment_source=ref(role),complete_increment_evidence=deepcopy(source),
          new_window_assumption=deepcopy(row['new_assumption']),prior_facts_modified=False,
          early_window_evidence_available=False if ticker=='CRWD' else None,
          early_window_status='MEMO_POSTDATES_WINDOW_START' if ticker=='CRWD' else 'NOT_NEWLY_ADJUDICATED',
          numerical_or_training_admission_inferred=False))
    unchanged=[r for r in rows if r['ticker'] not in ('PCAR','CRWD')]
    require(canonical(unchanged)==canonical([r for r in old['rows'] if r['ticker'] not in ('PCAR','CRWD')]),'Other99 changed')
    after19=[r for r in rows if r['identity_risk_state']==OLD_STATE]
    require(canonical(after19)==canonical(original19),'Original19 changed')
    candidates=[r for r in rows if r['coordinate'] is not None and r['risk_chain'] is not None]
    missing=[r for r in rows if r['coordinate'] is None]
    unassigned=[r for r in rows if r['coordinate'] is not None and r['risk_chain'] is None]
    require(len(candidates)==21 and len(missing)==79 and [r['ticker'] for r in unassigned]==['CPRT'],'Derived21/79/1 denominator')
    value=deepcopy(old)
    value.update(schema='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V2',rows=rows,extended_provenance=extensions,
      input_references={k:ref(k) for k in BOUND},original_input_references=deepcopy(old['input_references']),
      original19_exact_proof=dict(source=ref('original_wiring'),count=19,tickers=[r['ticker'] for r in original19],
        original_rows_sha256=sha(canonical(original19)),new_rows_sha256=sha(canonical(after19)),exact=True),
      unchanged_other99_exact=True,candidate_security_count=len(candidates),candidate_issuer_count=len({r['coordinate']['issuer_id'] for r in candidates}),
      dated_coordinate_risk_unassigned_count=len(unassigned),bounded_source_missing_count=len(missing),
      candidate_count_is_not_fit_column_count=True,fit_column_count=None,typed_panel_rebuilt=False,
      conditional_candidates_with_saved_volume_unit_block=[r['ticker'] for r in candidates if r['independent_channel_detail']['liquidity_status']=='BLOCKED_VOLUME_UNIT_UNKNOWN'])
    value.pop('source_hashes',None)
    return value


def build():
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
