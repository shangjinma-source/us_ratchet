"""Append ORLY only; preserve the sealed twenty-two-column parent and all four prior sidecars."""
import argparse
from copy import deepcopy
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
OUTPUT=BASE/'new_cutoff_conditional_panel_20260925_v5/panel.json'
BOUND={
 'wiring':('new_cutoff_identity_risk_wiring_20260925_v5/wiring.json','4889b642f2700256487eaf2753d303f1a35dbb6941c1080a0b7eca0ec51e1636'),
 'parent_panel':('new_cutoff_conditional_panel_20260925_v4/panel.json','c50856ad47fdc0c1eeebccf06f7d2a788cd68bfbde325296f8913242b2585c1d'),
 'parent_readback':('new_cutoff_conditional_panel_20260925_v4/independent_increment_readback.json','ea44004b9475c9e284a2652a379dd6aabd89f8a23c1e52eec49e48d673b297a2'),
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
    require(all(p not in sources or sources[p]==h for p,h in LOADED.items()),'Loaded source conflict')
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
        require(canonical(frame_payload(left))==canonical(frame_payload(right)),'Original twenty-two frame changed: '+name)
        proof[name]=dict(original_sha256=sha(canonical(frame_payload(left))),projected_sha256=sha(canonical(frame_payload(right))),exact=True)
    return proof


def selected_mapping_v5(panel,security_ids):
    require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V5' and panel['scope']==core.SCOPE,'Explicit V5 schema required')
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
    require(w['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V5' and parent['schema']=='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V4','Versioned parents')
    require(type(w['candidate_security_count']) is int and w['candidate_security_count']==24 and
        type(w['candidate_issuer_count']) is int and w['candidate_issuer_count']==23 and w['fit_column_count'] is None,
        'Conditional candidate24/23 is not a typed-column count')
    require(all(d['promotion_allowed'] is False for d in docs.values()),'Parent authority')
    require(readback['schema']=='NEW_CUTOFF_TYPED_PANEL_INCREMENT_INDEPENDENT_READBACK_V4' and readback['status']=='PASSED' and
        readback['candidate_reference']==ref('parent_panel') and readback['panel_content_sha256']==parent['panel']['panel_content_sha256'] and
        readback['full_original101_and_incremental_sidecars_compared'] is True and readback['original_twenty_one_five_frames_exact'] is True,'Saved complete parent audit')
    require(w['input_references']['parent_wiring']==parent['input_references']['wiring'] and
        parent['input_references']['channels']==ref('channels') and parent['input_references']['channel_audit']==ref('channel_audit'),'Parent lineage')
    require(audit['candidate_reference']==ref('channels') and audit['status']=='PASSED' and type(audit['completed']) is int and audit['completed']==101,'Saved channel audit')
    calendar=ch['calendar'];require(w['calendar']==calendar and len(calendar)==127 and calendar[0]=='2026-03-20' and calendar[-1]=='2026-09-21','Unchanged127 calendar')
    names=[r['ticker'] for r in w['rows']]
    require(len(names)==len(set(names))==101 and all([r['ticker'] for r in rows]==names for rows in
        (ch['rows'],audit['details'],parent['original_evidence_and_projection'],parent['panel']['observed_provenance_and_missing'])),'Exact101 order')
    prior={r['ticker']:r['wiring_row'] for r in parent['original_evidence_and_projection']}
    for item in parent['incremental_evidence_and_projection']+parent['v3_incremental_evidence_and_projection']+parent['v4_incremental_evidence_and_projection']:prior[item['ticker']]=item['complete_wiring_row']
    require([r for r in w['rows'] if r['ticker']!='ORLY']==[prior[t] for t in names if t!='ORLY'],'Other100 wiring exact')
    require(len(w['v5_extended_provenance'])==1,'Single ORLY extension')
    ext=w['v5_extended_provenance'][0];row=one(w['rows'],'ORLY')
    require(ext['ticker']=='ORLY' and ext['original_row']==prior['ORLY'] and ext['prior_facts_modified'] is False and
        ext['early_window_review_availability_verified'] is False and ext['saved_review_selection_date']=='2026-07-13','Original ORLY and late review preserved')
    declaration=ext['complete_increment_evidence']
    require(declaration['schema']=='ORLY_CONDITIONAL_DATED_IDENTITY_RISK_V1' and
        declaration['publication_date'] is None and declaration['publication_date_verified'] is False and
        declaration['action_or_signature_date_used_as_publication'] is False and
        declaration['action_date']==declaration['signature_date']=='2025-06-09' and
        declaration['annual_fetched_at']=='2026-07-15T06:38:30+00:00' and
        declaration['form_received_at']=='2026-09-24T17:37:33.511356+00:00','Action/signature and late receipts not publication')
    visual=declaration['complete_visual_transcription'];capture=declaration['complete_capture_evidence']
    require(visual['visual_transcription_is_not_text_parser_output'] is True and visual['publication_date'] is None and
        visual['cusip_original_text']=='67103H 107' and visual['cusip']=='67103H107' and visual['ein_used_as_cik'] is False and
        capture['occ_local_pdf_available'] is False and capture['occ_failure_is_identity_source'] is False and
        type(capture['occ_receipt']['http_status']) is int and capture['occ_receipt']['http_status']==403 and
        declaration['original_faq_registry_event']['cusip'] is None and declaration['original_faq_registry_event']['publication_date'] is None,
        'Visual transcription, failed OCC and old FAQ null remain')
    require(declaration['saved_review_decision']['selection_date']=='2026-07-13' and
        declaration['early_window_review_availability_verified'] is False and declaration['early_window_local_evidence_available'] is False and
        declaration['direct_single_document_cusip_cik_proof'] is False and ext['early_window_local_evidence_available'] is False,'Late cross-document declaration')
    require(row['coordinate']['security_id']=='security:0000898173:67103H107' and row['risk_chain']=='automotive' and
        ext['original_row']['coordinate'] is None and ext['original_row']['risk_chain'] is None,'Explicit ORLY conditional coordinate and risk')
    require(row['coordinate']==declaration['coordinate'] and row['coordinate']['issuer_id']=='issuer:0000898173' and
        row['coordinate']['cusip']=='67103H107' and row['coordinate']['security_class']=='Common Stock','Exact common-stock coordinate')
    require(row['v5_extended_provenance_reference']==dict(json_pointer='/v5_extended_provenance/0'),'ORLY extension pointer')
    for i,(r,c,a) in enumerate(zip(w['rows'],ch['rows'],audit['details'])):
        require(r['channel_reference']==ref('channels','/rows/'+str(i)) and r['channel_audit_reference']==ref('channel_audit','/details/'+str(i)) and
            r['channel_row_sha256']==sha(encode(c)) and r['independent_channel_detail']==a,'Exact saved numeric evidence')
    require(w['extended_provenance']==[item['complete_extended_provenance'] for item in parent['incremental_evidence_and_projection']],'V2 sidecars preserved')
    require(w['v3_extended_provenance']==[item['complete_extended_provenance'] for item in parent['v3_incremental_evidence_and_projection']],'V3 sidecar preserved')
    require(w['v4_extended_provenance']==[item['complete_extended_provenance'] for item in parent['v4_incremental_evidence_and_projection']],'V4 sidecar preserved')
    return calendar

def append_orly(before,numbers,coordinate,risk_chain):
    require(numbers[3] is None and numbers[2] is not None,'ORLY numerical gate did not pass')
    panel=deepcopy(before);require('ORLY' not in before['returns'].columns and 'CRWD' not in before['returns'].columns,'Parent cannot contain increments')
    sequences=dict(returns=numbers[0],nominal_close=numbers[1],raw_volume=numbers[2]['volumes'],dollar_volume=numbers[2]['dollars'])
    for name,values in sequences.items():
        require(len(values)==len(panel[name]),'Increment shape')
        panel[name]['ORLY']=pd.Series(values,index=panel[name].index,dtype='int64' if name=='raw_volume' else 'float64')
        panel[name]=panel[name].reindex(sorted(panel[name].columns),axis=1)
    newrow=dict(coordinate,risk_chain=risk_chain,median_dollar_volume_usd=numbers[2]['median'])
    panel['universe']=pd.concat([panel['universe'],pd.DataFrame([newrow],columns=panel['universe'].columns)],ignore_index=True).sort_values('security_id').reset_index(drop=True)
    return panel,original_frame_proof(before,panel)


def assemble(docs):
    calendar=validate_sources(docs);parent=docs['parent_panel'];w=docs['wiring'];before=codec.typed_decode(parent['panel'])
    require(before['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V4' and core.panel_digest(before)==before['panel_content_sha256'] and
        before['conditional_security_count']==22 and before['conditional_issuer_count']==21,'Sealed22/21 parent checksum')
    require(before['nominal_close'].index.tolist()==pd.DatetimeIndex(calendar).tolist() and all(before[k] is False for k in core.FALSE),'Parent calendar/permissions')
    channel=one(docs['channels']['rows'],'ORLY')['channel_input'];cr=one(docs['channels']['rows'],'CRWD')['channel_input']
    require(cr['liquidity']['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN' and 'CRWD' not in before['returns'].columns,'CRWD remains blocked')
    assertion=dict(channel_sha256=core.canonical_sha(channel),passed=True,source_references=[ref('channels'),ref('channel_audit')])
    with localcontext(Context(prec=80)):numbers=core.channel_values(channel,assertion,'ORLY',calendar,calendar[-1])
    row=one(w['rows'],'ORLY');ext=w['v5_extended_provenance'][0]
    panel,proof=append_orly(before,numbers,row['coordinate'],row['risk_chain'])
    gap=one(panel['observed_provenance_and_missing'],'ORLY');oldgap=deepcopy(gap);coord=row['coordinate']
    declaration=ext['complete_increment_evidence']
    anchor=declaration['action_date']
    require(anchor=='2025-06-09','ORLY action-date anchor')
    require(coord['issuer_id']==gap['observed_issuer_id'],'Observed issuer differs')
    coordinate=dict(coord,dated_fact=dict(coord,dated_as_of=anchor,date_role='ORGANIZATIONAL_ACTION_DATE_NOT_PUBLICATION_OR_JOINT_AVAILABILITY',publication_date=None,source_references=[ref('wiring')]),scope=core.SCOPE,
        latest_interval_verified=False,provider_binding_verified=False,assumed_window=deepcopy(row['new_assumed_window']))
    risk=dict(scope=core.SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,
        historical_labels=[row['risk_chain']],risk_chain=row['risk_chain'],source_references=[ref('wiring')],source_kind='NEW_CONDITIONAL_DATED_IDENTITY_AND_SAVED_RISK_DECLARATION')
    gap.update(coordinate_assumption=coordinate,risk_assumption=risk,included_in_conditional_panel=True,blocking_reasons=[])
    increment=dict(ticker='ORLY',wiring_reference=ref('wiring','/rows/'+str([r['ticker'] for r in w['rows']].index('ORLY'))),
        complete_wiring_row=deepcopy(row),complete_extended_provenance=deepcopy(ext),original_gap=oldgap,new_gap=deepcopy(gap),
        dated_anchor_value=anchor,dated_anchor_role='VISUALLY_TRANSCRIBED_ORGANIZATIONAL_ACTION_DATE_NOT_PUBLICATION_OR_JOINT_AVAILABILITY',
        publication_date=None,publication_date_verified=False,action_date=anchor,signature_date=declaration['signature_date'],action_or_signature_date_used_as_publication=False,
        annual_fetched_at=declaration['annual_fetched_at'],form_received_at=declaration['form_received_at'],
        saved_review_selection_date='2026-07-13',early_window_review_availability_verified=False,early_window_local_evidence_available=False,numerical_column_added=True)
    old100=[r for r in before['observed_provenance_and_missing'] if r['ticker']!='ORLY']
    require(old100==[r for r in panel['observed_provenance_and_missing'] if r['ticker']!='ORLY'],'Other100 gaps unchanged')
    panel.update(schema='LATEST_CONDITIONAL_TYPED_PANEL_V5',conditional_security_count=len(panel['universe']),conditional_issuer_count=panel['universe'].issuer_id.nunique())
    require((panel['conditional_security_count'],panel['conditional_issuer_count'])==(23,22),'Derived23 typed SIDs/22 issuers')
    panel['panel_content_sha256']=core.panel_digest(panel)
    for sid in panel['universe'].security_id.tolist():selected_mapping_v5(panel,[sid])
    encoded=codec.typed_encode(panel);require(core.panel_digest(codec.typed_decode(encoded))==panel['panel_content_sha256'],'V5 codec roundtrip')
    return dict(schema='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V5',scope=core.SCOPE,panel=encoded,
        original_evidence_and_projection=deepcopy(parent['original_evidence_and_projection']),incremental_evidence_and_projection=deepcopy(parent['incremental_evidence_and_projection']),
        v3_incremental_evidence_and_projection=deepcopy(parent['v3_incremental_evidence_and_projection']),
        v4_incremental_evidence_and_projection=deepcopy(parent['v4_incremental_evidence_and_projection']),
        v5_incremental_evidence_and_projection=[increment],original22_frame_exact_proof=proof,original100_gap_exact_sha256=sha(canonical(old100)),original100_gap_exact=True,
        input_references={k:ref(k) for k in BOUND},source_coordinate_candidate_count=w['candidate_security_count'],
        actual_panel_security_count=panel['conditional_security_count'],actual_panel_issuer_count=panel['conditional_issuer_count'],independently_audited_parent_reused=True,
        incremental_numeric_channels_calculated=['ORLY'],raw_volume_blocked_candidates=['CRWD'],numeric_projection_policy=deepcopy(parent['numeric_projection_policy']),
        issuer_observation_basis=deepcopy(parent['issuer_observation_basis']),source_decimal_quote_values_retained_in_new_channels=True,old_numeric_values_preserved_exactly=True,
        mapping_interface='selected_mapping_v5; V1_V2_V3_V4_SELECTED_MAPPING_INCOMPATIBLE_BY_SCHEMA',**dict.fromkeys(FALSE,False))

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
