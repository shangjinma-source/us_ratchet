"""Append one PCAR typed column; preserve sealed nineteen-column parent exactly."""
import argparse
from copy import deepcopy
from datetime import datetime
from decimal import Context,localcontext
import hashlib
import json
import os
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_latest_conditional_panel_research as core
from scripts import ndx_new_cutoff_conditional_panel_20260923 as codec
SOURCE=Path(__file__).resolve();BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'new_cutoff_conditional_panel_20260924_v2/panel.json'
BOUND={
 'wiring':('new_cutoff_identity_risk_wiring_20260924_v2/wiring.json','d374ee81bb6c9f0003f20a4c4e4a819b2a01cbbd638af43974baf64c9cd571df'),
 'parent_panel':('new_cutoff_conditional_panel_20260923_v1/panel.json','15c5d9449f10abeb7379baad9fd2b117b8fb84a24582190cf01b8d5b8dd8b047'),
 'parent_readback':('new_cutoff_conditional_panel_20260923_v1/independent_typed_readback.json','f3e55a68487c78f42d5b4dd7da12461177d472edcab89499697bbaa405c66fa8'),
 'channels':('new_cutoff_conditional_channels_20260923_v1/channels.json','3d708df6b273616edd46e06d2e2976acbc0e9fd90cc1243679ff94ca8befa3ac'),
 'channel_audit':('new_cutoff_conditional_channels_20260923_v1/independent_raw_decimal_audit.json','a11e7fb3b9006eba71b9d254557f713a32b2615407c9b8f77e7b24a8c01a2ace'),
}
CODE_PINS={str(Path(core.__file__).resolve()):'0d5c031f855348577bf9ffd17acf68998c86c43a60a45a05e014dc1e1ac34b59',
 str(Path(codec.__file__).resolve()):'95bc442c379acb32b4c5d1c58a2eca6e0e2ad97bca9538249affe1a5e937236c'}
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(core.__file__).resolve(),Path(codec.__file__).resolve(),Path(pd.__file__).resolve())}
FRAMES=('returns','nominal_close','raw_volume','dollar_volume','universe')
FALSE=('formal_input_ready','legal_training_input_admitted','point_in_time_verified','promotion_allowed','execution_authorized',
 'strict_loader_validation_passed','fit_performed','enumeration_performed','raw_oracle_called','old_panel_assemble_called','old_numeric_values_recomputed',
 'http_performed','full_transitive_source_closure_reverified','issuer_observation_currently_certified')


def require(ok,message):
    if not ok:raise ValueError(message)


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def encode(v):return (json.dumps(v,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def ref(role,pointer=None):
    p,h=BOUND[role];r=dict(path=str(BASE/p),sha256=h)
    if pointer is not None:r['json_pointer']=pointer
    return r


def guard(sources):
    require(all(LOADED[p]==h for p,h in CODE_PINS.items()),'Loaded frozen helper hash differs')
    for p,h in {**sources,**LOADED}.items():require(sha(Path(p).read_bytes())==h,'Source drift')


def one(rows,ticker):
    found=[r for r in rows if r['ticker']==ticker];require(len(found)==1,'Unique ticker required');return found[0]


def frame_payload(frame):
    return dict(index=[str(v) for v in frame.index],index_kind=type(frame.index).__name__,columns=frame.columns.tolist(),dtypes=[str(v) for v in frame.dtypes],data=frame.values.tolist())


def original_frame_proof(before,after):
    proof={}
    for name in FRAMES:
        left=before[name]
        if name=='universe':
            require(after[name]['security_id'].is_unique,'Duplicate SID')
            right=after[name].set_index('security_id',drop=False).loc[left['security_id'].tolist()].reset_index(drop=True)
        else:right=after[name].loc[:,left.columns]
        require(canonical(frame_payload(left))==canonical(frame_payload(right)),'Original nineteen frame changed: '+name)
        proof[name]=dict(original_sha256=sha(canonical(frame_payload(left))),projected_sha256=sha(canonical(frame_payload(right))),exact=True)
    return proof


def selected_mapping_v2(panel,security_ids):
    require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V2' and panel['scope']==core.SCOPE,'Explicit V2 schema required')
    require(all(panel.get(k) is False for k in core.FALSE),'Conditional panel permissions')
    require(panel['panel_content_sha256']==core.panel_digest(panel),'Panel checksum differs')
    require(type(security_ids) is list and security_ids and len(set(security_ids))==len(security_ids),'Explicit unique SID selection')
    rows=panel['universe'].to_dict('records');by={r['security_id']:r for r in rows}
    require(len(by)==len(rows) and all(s in by for s in security_ids),'Unknown SID')
    result={s:{k:by[s][k] for k in ('ticker','issuer_id','risk_chain')} for s in security_ids}
    require(len({v['issuer_id'] for v in result.values()})==len(result),'One security per issuer per portfolio')
    require(all(v['ticker'] in panel['returns'].columns and type(v['risk_chain']) is str and v['risk_chain'] for v in result.values()),'Selected typed/risk coordinate missing')
    return result


def validate_sources(docs):
    w,parent,readback,ch,audit=(docs[k] for k in ('wiring','parent_panel','parent_readback','channels','channel_audit'))
    require(w['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V2' and parent['schema']=='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1','Versioned parents')
    require(all(d['promotion_allowed'] is False for d in docs.values()),'Parent authority')
    require(readback['status']=='PASSED' and readback['candidate_reference']==ref('parent_panel') and readback['panel_content_sha256']==parent['panel']['panel_content_sha256'],'Parent independent readback binding')
    require(w['input_references']['channels']==ref('channels') and w['input_references']['audit']==ref('channel_audit') and audit['candidate_reference']==ref('channels') and audit['status']=='PASSED' and audit['completed']==101,'Channel references')
    require(parent['input_references']['channels']==ref('channels') and parent['input_references']['audit']==ref('channel_audit'),'Parent same numeric cutoff')
    require(w['input_references']['original_wiring']==parent['input_references']['wiring'],'Wiring lineage')
    calendar=ch['calendar'];require(w['calendar']==calendar and len(calendar)==127 and calendar[0]=='2026-03-20' and calendar[-1]=='2026-09-21','Calendar unchanged')
    names=[r['ticker'] for r in w['rows']];require(len(names)==len(set(names))==101,'101 denominator')
    oldside=parent['original_evidence_and_projection']
    require(all([r['ticker'] for r in rows]==names for rows in (ch['rows'],audit['details'],oldside,parent['panel']['observed_provenance_and_missing'])),'101 ordered parents')
    originals=[x['wiring_row'] for x in oldside]
    original19=[r for r in originals if r['identity_risk_state']=='DATED_COORDINATE_AND_LEGACY_RISK_AVAILABLE_FOR_EXPLICIT_NEW_ASSUMPTION']
    current19=[r for r in w['rows'] if r['ticker'] in {r['ticker'] for r in original19}]
    proof=w['original19_exact_proof']
    require(len(original19)==19 and canonical(original19)==canonical(current19) and proof['original_rows_sha256']==proof['new_rows_sha256']==sha(canonical(original19)) and proof['exact'] is True,'Actual original nineteen exact proof')
    require(canonical([r for r in originals if r['ticker'] not in ('PCAR','CRWD')])==canonical([r for r in w['rows'] if r['ticker'] not in ('PCAR','CRWD')]),'Other99 wiring changed')
    require(len(w['extended_provenance'])==2 and {e['ticker'] for e in w['extended_provenance']}=={'PCAR','CRWD'},'Two increments')
    for t in ('PCAR','CRWD'):
        ext=one(w['extended_provenance'],t);row=one(w['rows'],t)
        require(ext['original_row']==one(originals,t) and ext['prior_facts_modified'] is False and ext['numerical_or_training_admission_inferred'] is False,'Full original increment provenance')
        require(row['extended_provenance_reference']=={'json_pointer':'/extended_provenance/'+str(w['extended_provenance'].index(ext))},'Extension pointer')
        require(row['new_assumed_window']=={'first':calendar[0],'last':calendar[-1]},'Increment window')
    for i,(r,c,a) in enumerate(zip(w['rows'],ch['rows'],audit['details'])):
        require(r['channel_reference']==ref('channels','/rows/'+str(i)) and r['channel_audit_reference']==ref('channel_audit','/details/'+str(i)),'Exact increment channel references')
        require(r['channel_row_sha256']==sha(encode(c)) and r['independent_channel_detail']==a,'No numeric evidence change')
    p=one(w['rows'],'PCAR');c=one(w['rows'],'CRWD');pc=one(w['extended_provenance'],'PCAR');cc=one(w['extended_provenance'],'CRWD')
    require(p['risk_chain']=='automotive' and p['coordinate']['security_id']=='security:0000075362:693718108' and pc['complete_increment_evidence']['conditional_assigned_risk_chain']=='automotive','PCAR explicit judgment')
    require(p['complete_original_evidence'][0]['complete_original_fact']['risk_chain'] is None,'Original PCAR null risk preserved')
    require(c['risk_chain']=='cybersecurity' and c['coordinate']['security_id']=='security:0001535527:22788C105' and c['coordinate']['security_class']=='CLASS_A_COMMON','CRWD separate class/SID')
    require(cc['early_window_evidence_available'] is False and cc['complete_increment_evidence']['memo_publication_date']=='2026-06-09' and cc['complete_increment_evidence']['volume_status']=='BLOCKED_VOLUME_UNIT_UNKNOWN','CRWD late memo and volume')
    return calendar


def append_pcar(before,numbers,coordinate,risk_chain):
    require(numbers[3] is None and numbers[2] is not None,'PCAR numerical gate did not pass')
    panel=deepcopy(before);require('PCAR' not in before['returns'].columns and 'CRWD' not in before['returns'].columns,'Parent cannot contain increments')
    sequences=dict(returns=numbers[0],nominal_close=numbers[1],raw_volume=numbers[2]['volumes'],dollar_volume=numbers[2]['dollars'])
    for name,values in sequences.items():
        require(len(values)==len(panel[name]),'Increment shape')
        panel[name]['PCAR']=pd.Series(values,index=panel[name].index,dtype='int64' if name=='raw_volume' else 'float64')
        panel[name]=panel[name].reindex(sorted(panel[name].columns),axis=1)
    newrow=dict(coordinate,risk_chain=risk_chain,median_dollar_volume_usd=numbers[2]['median'])
    panel['universe']=pd.concat([panel['universe'],pd.DataFrame([newrow],columns=panel['universe'].columns)],ignore_index=True).sort_values('security_id').reset_index(drop=True)
    return panel,original_frame_proof(before,panel)


def assemble(docs):
    calendar=validate_sources(docs);parent=docs['parent_panel'];w=docs['wiring']
    before=codec.typed_decode(parent['panel'])
    require(before['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V1' and core.panel_digest(before)==before['panel_content_sha256'],'Original checksum')
    require(before['conditional_security_count']==19 and before['conditional_issuer_count']==18 and before['nominal_close'].index.tolist()==pd.DatetimeIndex(calendar).tolist(),'Original nineteen calendar')
    require(all(before[k] is False for k in core.FALSE),'Original conditional flags')
    pc=one(docs['channels']['rows'],'PCAR')['channel_input'];cr=one(docs['channels']['rows'],'CRWD')['channel_input']
    require(cr['liquidity']['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN' and all(cr['liquidity'][k] is None for k in ('rows','median_dollar_volume_usd','numerical_threshold_passed')),'CRWD blocked values unchanged')
    assertion=dict(channel_sha256=core.canonical_sha(pc),passed=True,source_references=[ref('channels'),ref('channel_audit')])
    with localcontext(Context(prec=80)):numbers=core.channel_values(pc,assertion,'PCAR',calendar,calendar[-1])
    row=one(w['rows'],'PCAR');panel,proof=append_pcar(before,numbers,row['coordinate'],row['risk_chain'])
    increments=[]
    for ticker in ('PCAR','CRWD'):
        row=one(w['rows'],ticker);ext=one(w['extended_provenance'],ticker);gap=one(panel['observed_provenance_and_missing'],ticker);oldgap=deepcopy(gap)
        if ticker=='PCAR':
            anchor_text=row['complete_original_evidence'][0]['complete_original_fact']['dated_memo_facts'][0]['publication_date_text']
            anchor=datetime.strptime(anchor_text,'%B %d, %Y').date().isoformat()
            anchor_role='ORIGINAL_MEMO_PUBLICATION_DATE_NOT_JOINT_AVAILABILITY'
            source_kind='NEW_CONDITIONAL_ANALYST_JUDGMENT'
        else:
            anchor=ext['complete_increment_evidence']['memo_publication_date'];anchor_role='LATE_MEMO_PUBLICATION_NOT_EARLY_WINDOW_PROOF'
            source_kind='HISTORICAL_REVIEWED_BUSINESS_MATCH_WITH_CROSS_DOCUMENT_IDENTITY'
        coord=row['coordinate'];coordinate=dict(coord,dated_fact=dict(coord,dated_as_of=anchor,source_references=[ref('wiring')]),scope=core.SCOPE,
          latest_interval_verified=False,provider_binding_verified=False,assumed_window=deepcopy(row['new_assumed_window']))
        risk=dict(scope=core.SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,
          historical_labels=[row['risk_chain']],risk_chain=row['risk_chain'],source_references=[ref('wiring')],source_kind=source_kind)
        require(coord['issuer_id']==gap['observed_issuer_id'],'Increment observed issuer differs')
        gap.update(coordinate_assumption=coordinate,risk_assumption=risk,included_in_conditional_panel=ticker=='PCAR',
          blocking_reasons=[] if ticker=='PCAR' else ['BLOCKED_VOLUME_UNIT_UNKNOWN'])
        increments.append(dict(ticker=ticker,wiring_reference=ref('wiring','/rows/'+str([r['ticker'] for r in w['rows']].index(ticker))),
          complete_wiring_row=deepcopy(row),complete_extended_provenance=deepcopy(ext),original_gap=oldgap,new_gap=deepcopy(gap),
          dated_anchor_value=anchor,dated_anchor_role=anchor_role,early_window_evidence_available=False if ticker=='CRWD' else None,
          numerical_column_added=ticker=='PCAR'))
    old99=[r for r in before['observed_provenance_and_missing'] if r['ticker'] not in ('PCAR','CRWD')]
    new99=[r for r in panel['observed_provenance_and_missing'] if r['ticker'] not in ('PCAR','CRWD')]
    require(canonical(old99)==canonical(new99),'99 gap rows changed')
    panel.update(schema='LATEST_CONDITIONAL_TYPED_PANEL_V2',conditional_security_count=len(panel['universe']),conditional_issuer_count=panel['universe'].issuer_id.nunique())
    panel['panel_content_sha256']=core.panel_digest(panel)
    for sid in panel['universe'].security_id.tolist():selected_mapping_v2(panel,[sid])
    encoded=codec.typed_encode(panel);require(core.panel_digest(codec.typed_decode(encoded))==panel['panel_content_sha256'],'V2 codec roundtrip')
    return dict(schema='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V2',scope=core.SCOPE,panel=encoded,
      original_evidence_and_projection=deepcopy(parent['original_evidence_and_projection']),incremental_evidence_and_projection=increments,
      original19_frame_exact_proof=proof,original99_gap_exact_sha256=sha(canonical(old99)),original99_gap_exact=True,
      input_references={k:ref(k) for k in BOUND},source_coordinate_candidate_count=w['candidate_security_count'],
      actual_panel_security_count=panel['conditional_security_count'],actual_panel_issuer_count=panel['conditional_issuer_count'],
      independently_audited_parent_reused=True,incremental_numeric_channels_calculated=['PCAR'],raw_volume_blocked_candidates=['CRWD'],
      numeric_projection_policy=parent['numeric_projection_policy'],issuer_observation_basis=parent['issuer_observation_basis'],
      source_decimal_quote_values_retained_in_new_channels=True,old_numeric_values_preserved_exactly=True,
      mapping_interface='selected_mapping_v2; V1_SELECTED_MAPPING_INCOMPATIBLE_BY_SCHEMA',**dict.fromkeys(FALSE,False))


def build():
    sources=dict(LOADED);guard(sources);docs={}
    for role in BOUND:
        r=ref(role);raw=Path(r['path']).read_bytes();require(sha(raw)==r['sha256'],'Consumed parent bytes changed')
        docs[role]=codec.loads(raw);sources[r['path']]=r['sha256']
    result=assemble(docs);result['source_hashes']=sources;guard(sources);return result


def publish():
    require(not OUTPUT.parent.exists(),'Fixed namespace already exists')
    value=build();guard(value['source_hashes']);raw=encode(value)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw and {p.name for p in OUTPUT.parent.iterdir()}=={'panel.json'},'Publication readback differs')
    return dict(path=str(OUTPUT),sha256=sha(raw))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');a=p.parse_args()
    require(a.publish,'Explicit --publish required');print(json.dumps(publish()))
