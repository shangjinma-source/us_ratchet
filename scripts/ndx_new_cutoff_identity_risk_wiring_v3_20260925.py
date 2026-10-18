"""CPRT-only conditional risk wiring; no historical facts or numerical columns rewritten."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
SOURCE=Path(__file__).resolve();BASE=SOURCE.parents[1]/'data/cache/research'
OUTPUT=BASE/'new_cutoff_identity_risk_wiring_20260925_v3/wiring.json'
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BOUND={
 'parent_wiring':('new_cutoff_identity_risk_wiring_20260924_v2/wiring.json','d374ee81bb6c9f0003f20a4c4e4a819b2a01cbbd638af43974baf64c9cd571df'),
 'cprt_declaration':('cprt_saved_risk_adjudication_20260925_v1/adjudication.json','3022577f119cd198868b9ab861d7ec351ca2df7eca297d77b1ab43a2d9ebe28f')}
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



def validate_declaration(declaration,row):
    require(declaration['schema']=='CPRT_SAVED_RISK_CONDITIONAL_ADJUDICATION_V1' and
        all(declaration[key]==value for key,value in row['coordinate'].items()) and declaration['risk_chain']=='automotive' and
        declaration['conditional_risk_chain_assigned'] is True and declaration['research_only'] is True,'Exact saved conditional CPRT declaration')
    require(declaration['assumed_window']==dict(first='2026-03-20',last='2026-09-21') and type(declaration['new_window_assumption']) is str and declaration['new_window_assumption'].strip(),'Explicit new-window assumption')
    for key in ('point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized'):
        require(declaration[key] is False,'Declaration authority upgrade')
    require(declaration['original_identity_fact']==row['complete_original_evidence'][0]['complete_original_fact'],'Original identity fact differs')
    business=declaration['original_business_fact']
    require(business['assigned_risk_chain'] is None and business['risk_chain_assigned'] is False and
        business['boundary_status']=='UNRESOLVED_EXISTING_ALTERNATIVES' and business['candidate_risk_chains']==['internet_ecommerce','automotive','industrial'] and
        type(declaration['saved_seed_decision']) is dict and type(declaration['saved_review_decision']) is dict,'Saved original undecided business and decisions required')
    require(declaration['saved_review_decision']['selection_date']=='2026-07-13' and
        declaration['saved_review_selection_postdates_window_start'] is True and declaration['early_window_review_availability_verified'] is False,'Late review cannot imply early-window availability')


def assemble(docs):
    old=docs['parent_wiring'];declaration=docs['cprt_declaration']
    require(old['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V2' and all(old[k] is False for k in FALSE),'Conditional V2 parent required')
    rows=deepcopy(old['rows']);tickers=[r['ticker'] for r in rows]
    require(len(tickers)==len(set(tickers))==101 and tickers.count('CPRT')==1,'Complete101 parent rows')
    position=tickers.index('CPRT');row=rows[position];original=deepcopy(row)
    require(row['coordinate']==dict(ticker='CPRT',security_id='security:0000900075:217204106',issuer_id='issuer:0000900075',cusip='217204106',security_class='Common Stock, par value $0.0001'),'Exact preserved CPRT dated coordinate')
    require(row['identity_risk_state']=='DATED_COORDINATE_RISK_UNASSIGNED' and row['risk_chain'] is None and row['risk_sources']==[],'Original CPRT risk remains unassigned')
    fact=row['complete_original_evidence'][0]['complete_original_fact']
    require(fact['risk_chain'] is None and fact['risk_chain_assigned'] is False,'Original nested null risk must remain')
    validate_declaration(declaration,row)
    calendar=old['calendar'];require(len(calendar)==127 and calendar[0]=='2026-03-20' and calendar[-1]=='2026-09-21','Existing conditional window')
    row['risk_chain']='automotive';row['identity_risk_state']='DATED_COORDINATE_AND_CONDITIONAL_RISK_AVAILABLE_FOR_EXPLICIT_NEW_ASSUMPTION'
    row['new_assumption']=dict(scope='CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY',window=dict(first=calendar[0],last=calendar[-1]),
        security_continuity_is_explicit_assumption=True,risk_label_persistence_is_explicit_assumption=True,
        interval_certified=False,source_interval_extended=False,provider_binding_verified=False)
    row['risk_sources']=[dict(source=ref('cprt_declaration'),source_kind='NEW_SAVED_CONDITIONAL_RISK_DECLARATION',risk_chain='automotive')]
    row['gaps']=[gap for gap in row['gaps'] if gap!='NO_BUSINESS_RISK_CLASSIFICATION_ADJUDICATED']
    row['gaps'].append('SAVED_REVIEW_POSTDATES_WINDOW_START_NO_EARLY_AVAILABILITY_PROOF')
    row['v3_extended_provenance_reference']=dict(json_pointer='/v3_extended_provenance/0')
    unchanged=[r for r in rows if r['ticker']!='CPRT'];before=[r for r in old['rows'] if r['ticker']!='CPRT']
    require(canonical(unchanged)==canonical(before),'Other100 rows must remain exact')
    candidates=[r for r in rows if r['coordinate'] is not None and r['risk_chain'] is not None]
    missing=[r for r in rows if r['coordinate'] is None];unassigned=[r for r in rows if r['coordinate'] is not None and r['risk_chain'] is None]
    require(len(candidates)==22 and len({r['coordinate']['security_id'] for r in candidates})==22 and len(missing)==79 and not unassigned,'Derived22/79/0 candidate denominator')
    value=deepcopy(old);value.pop('source_hashes',None)
    value.update(schema='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V3',rows=rows,input_references={k:ref(k) for k in BOUND},
        parent_v2_input_references=deepcopy(old['input_references']),
        v3_extended_provenance=[dict(ticker='CPRT',original_row_reference=ref('parent_wiring','/rows/'+str(position)),original_row=original,
            increment_source=ref('cprt_declaration'),complete_increment_evidence=deepcopy(declaration),new_window_assumption=deepcopy(row['new_assumption']),
            saved_review_selection_date=declaration['saved_review_decision']['selection_date'],saved_review_selection_postdates_window_start=True,early_window_review_availability_verified=False,
            prior_facts_modified=False,numerical_or_training_admission_inferred=False)],
        unchanged_other100_exact=True,unchanged_other100_sha256=sha(canonical(unchanged)),candidate_security_count=len(candidates),
        candidate_issuer_count=len({r['coordinate']['issuer_id'] for r in candidates}),dated_coordinate_risk_unassigned_count=0,bounded_source_missing_count=len(missing),
        candidate_count_is_not_fit_column_count=True,fit_column_count=None,typed_panel_rebuilt=False)
    require(value['extended_provenance']==old['extended_provenance'],'All V2 sidecars preserved')
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
