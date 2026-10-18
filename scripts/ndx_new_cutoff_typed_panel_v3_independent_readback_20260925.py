"""Independent CPRT-only projection audit; frozen twenty columns are compared, not rebuilt."""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
sys.path.insert(0,str(ROOT))
from scripts import ndx_new_cutoff_typed_panel_independent_readback_20260923 as codec

PRODUCER=ROOT/'scripts/ndx_new_cutoff_conditional_panel_v3_20260925.py'
PRODUCER_SHA='7fdf6f6323d10a00525af88ef133c9fc525207ed2951b251695a81f3590d7a7e'
CANDIDATE=BASE/'new_cutoff_conditional_panel_20260925_v3/panel.json'
CANDIDATE_SHA='f577d69c27925f56a25a1e32c771eb36cdb47f9d0732dc235c767b99fdf18e0b'
OUTPUT=CANDIDATE.parent/'independent_increment_readback.json'
CORE=ROOT/'backtest/ndx_latest_conditional_panel_research.py'
CORE_SHA='0d5c031f855348577bf9ffd17acf68998c86c43a60a45a05e014dc1e1ac34b59'
CODEC_SHA='0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'
PRODUCER_CODEC=ROOT/'scripts/ndx_new_cutoff_conditional_panel_20260923.py'
PRODUCER_CODEC_SHA='95bc442c379acb32b4c5d1c58a2eca6e0e2ad97bca9538249affe1a5e937236c'
BOUND={
 'wiring':('new_cutoff_identity_risk_wiring_20260925_v3/wiring.json','eba66e35c70a2614504b0d52e27628f81c501cb2e4f218cb0c93be03a0e376ef'),
 'parent_panel':('new_cutoff_conditional_panel_20260924_v2/panel.json','6dcd97bd87dfabab272dc50f9ac7d06e11410e1bf63d305596317236a348d412'),
 'parent_readback':('new_cutoff_conditional_panel_20260924_v2/independent_increment_readback.json','975fc921977a1295cc70f6d3b0a9eda0e4ac7864895a76551f815ab89888b283'),
 'channels':('new_cutoff_conditional_channels_20260923_v1/channels.json','3d708df6b273616edd46e06d2e2976acbc0e9fd90cc1243679ff94ca8befa3ac'),
 'channel_audit':('new_cutoff_conditional_channels_20260923_v1/independent_raw_decimal_audit.json','a11e7fb3b9006eba71b9d254557f713a32b2615407c9b8f77e7b24a8c01a2ace'),
}
LOADED={**codec.LOADED,str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
FALSE=('producer_called','panel_core_called','old_raw_oracle_called','old_typed_audit_repeated',
 'old_twenty_numeric_channels_recomputed','http_performed','fit_performed','point_in_time_verified',
 'legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified')


def require(ok,message):
    if not ok:raise ValueError(message)


def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])


def merged_sources(sources):
    result=dict(sources)
    for mapping in (LOADED,codec.LOADED):
        for path,h in mapping.items():
            require(path not in result or result[path]==h,'Source conflict');result[path]=h
    return result


def guard(sources):
    require(LOADED[str(Path(codec.__file__).resolve())]==CODEC_SHA,'Frozen independent codec differs')
    for path,digest in merged_sources(sources).items():
        require(codec.sha(Path(path).read_bytes())==digest,'Source drift: '+path)


def verify_candidate(candidate,documents,producer_sources):
    require(candidate['source_hashes']==producer_sources,'Exact producer source map required')
    decoded=codec.decode_frames(candidate['panel'])
    expected=reconstruct_increment(documents)
    require(codec.canonical({k:v for k,v in candidate.items() if k!='source_hashes'})==codec.canonical(expected),
        'Full increment, preserved frames, gaps or sidecars differ')
    return decoded


def one(rows,ticker):
    selected=[row for row in rows if row['ticker']==ticker]
    require(len(selected)==1,'Unique source ticker required');return selected[0]


def frame_payload(frame):
    return dict(index=[str(value) for value in frame.index],index_kind=type(frame.index).__name__,
        columns=frame.columns.tolist(),dtypes=[str(value) for value in frame.dtypes],data=frame.values.tolist())


def reconstruct_increment(documents):
    parent,previous,wiring,channels,audit=(documents[key] for key in ('parent_panel','parent_readback','wiring','channels','channel_audit'))
    require(parent['schema']=='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V2' and previous['schema']=='NEW_CUTOFF_TYPED_PANEL_INCREMENT_INDEPENDENT_READBACK_V2' and previous['status']=='PASSED','Audited V2 parent')
    require(previous['candidate_reference']==ref('parent_panel') and previous['original_nineteen_five_frames_exact'] is True and previous['full_original101_and_incremental_sidecars_compared'] is True and previous['typed_roundtrip_exact'] is True and type(previous['increment_reconstruction_count']) is int and previous['increment_reconstruction_count']==1,'Full saved parent audit')
    require(all(d['promotion_allowed'] is False for d in documents.values()),'No parent authority upgrade')
    before=codec.decode_frames(parent['panel']);panel=deepcopy(before)
    require(before['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V2' and type(before['conditional_security_count']) is int and before['conditional_security_count']==20 and before['conditional_issuer_count']==19 and previous['panel_content_sha256']==before['panel_content_sha256'],'Original20 panel')
    require(all(before[key] is False for key in codec.PANEL_FALSE),'Conditional parent')
    calendar=channels['calendar']
    require(wiring['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V3' and wiring['calendar']==calendar==[v.date().isoformat() for v in before['nominal_close'].index],'Exact new calendar')
    require(wiring['input_references']['parent_wiring']==parent['input_references']['wiring'] and wiring['parent_v2_input_references']['channels']==ref('channels') and wiring['parent_v2_input_references']['audit']==ref('channel_audit') and audit['candidate_reference']==ref('channels') and audit['status']=='PASSED' and type(audit['completed']) is int and audit['completed']==101,'Source lineage')
    original_rows=[item['wiring_row'] for item in parent['original_evidence_and_projection']]
    # V1 sidecars are immutable: overlay the two saved V2 extensions to recover V2 wiring rows.
    for item in parent['incremental_evidence_and_projection']:
        original_rows[[r['ticker'] for r in original_rows].index(item['ticker'])]=deepcopy(item['complete_wiring_row'])
    tickers=[r['ticker'] for r in original_rows]
    require(len(tickers)==len(set(tickers))==101 and all([r['ticker'] for r in rows]==tickers for rows in (wiring['rows'],channels['rows'],audit['details'],before['observed_provenance_and_missing'])),'Full101 exact ordering')
    require([r for r in wiring['rows'] if r['ticker']!='CPRT']==[r for r in original_rows if r['ticker']!='CPRT'],'Other100 wiring preserved')
    require(type(wiring['candidate_security_count']) is int and wiring['candidate_security_count']==22 and wiring['candidate_issuer_count']==21,'Candidate count not panel count')
    for i,(row,channel,detail) in enumerate(zip(wiring['rows'],channels['rows'],audit['details'])):
        require(row['channel_reference']==dict(ref('channels'),json_pointer='/rows/'+str(i)) and row['channel_audit_reference']==dict(ref('channel_audit'),json_pointer='/details/'+str(i)) and row['channel_row_sha256']==codec.sha(codec.pretty(channel)) and row['independent_channel_detail']==detail,'Full101 channel audit references')
    require(wiring['extended_provenance']==[v['complete_extended_provenance'] for v in parent['incremental_evidence_and_projection']],'Complete V2 sidecars retained')
    require(len(wiring['v3_extended_provenance'])==1,'Single CPRT extension')
    row=one(wiring['rows'],'CPRT');extension=one(wiring['v3_extended_provenance'],'CPRT');declaration=extension['complete_increment_evidence']
    require(extension['original_row']==one(original_rows,'CPRT') and extension['prior_facts_modified'] is False,'Original null row preserved')
    require(declaration['original_identity_fact']==row['complete_original_evidence'][0]['complete_original_fact'] and declaration['original_identity_fact']['risk_chain'] is None and declaration['original_business_fact']['assigned_risk_chain'] is None,'Historical null remains')
    require(declaration['saved_review_decision']['selection_date']=='2026-07-13' and declaration['saved_review_selection_postdates_window_start'] is True and declaration['early_window_review_availability_verified'] is False and extension['early_window_review_availability_verified'] is False,'Late review retained')
    coordinate=row['coordinate'];require(coordinate['security_id']=='security:0000900075:217204106' and coordinate['issuer_id']=='issuer:0000900075' and row['risk_chain']=='automotive','CPRT coordinate/risk')
    fact=declaration['original_identity_fact'];anchor=datetime.strptime(fact['dated_memo_facts'][0]['publication_date_text'],'%B %d, %Y').date().isoformat()
    require(anchor=='2022-11-03' and row['new_assumed_window']==dict(first=calendar[0],last=calendar[-1]),'Original memo and conditional window')
    gap=one(panel['observed_provenance_and_missing'],'CPRT');original_gap=deepcopy(gap)
    require(gap['observed_issuer_id']==coordinate['issuer_id'],'Observed issuer link')
    gap.update(coordinate_assumption=dict(coordinate,dated_fact=dict(coordinate,dated_as_of=anchor,source_references=[ref('wiring')]),scope=codec.SCOPE,latest_interval_verified=False,provider_binding_verified=False,assumed_window=deepcopy(row['new_assumed_window'])),
        risk_assumption=dict(scope=codec.SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,historical_labels=['automotive'],risk_chain='automotive',source_references=[ref('wiring')],source_kind='NEW_SAVED_CONDITIONAL_RISK_DECLARATION'),included_in_conditional_panel=True,blocking_reasons=[])
    increment=dict(ticker='CPRT',wiring_reference=dict(ref('wiring'),json_pointer='/rows/'+str(tickers.index('CPRT'))),complete_wiring_row=deepcopy(row),complete_extended_provenance=deepcopy(extension),original_gap=original_gap,new_gap=deepcopy(gap),dated_anchor_value=anchor,dated_anchor_role='ORIGINAL_MEMO_PUBLICATION_DATE_NOT_JOINT_AVAILABILITY',saved_review_selection_date='2026-07-13',early_window_review_availability_verified=False,numerical_column_added=True)
    blocked=one(channels['rows'],'CRWD')['channel_input']['liquidity']
    require(blocked['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN' and all(blocked[k] is None for k in ('rows','median_dollar_volume_usd','numerical_threshold_passed')) and one(panel['observed_provenance_and_missing'],'CRWD')['blocking_reasons']==['BLOCKED_VOLUME_UNIT_UNKNOWN'],'CRWD remains blocked')
    numbers=codec.channel_numbers(one(channels['rows'],'CPRT')['channel_input'],calendar)
    require(numbers[3] is None and numbers[2] is not None,'CPRT numerical gate')
    for name,values in dict(returns=numbers[0],nominal_close=numbers[1],raw_volume=numbers[2]['volumes'],dollar_volume=numbers[2]['dollars']).items():
        require('CPRT' not in panel[name].columns and 'CRWD' not in panel[name].columns,'No existing increment or blocked column')
        panel[name]['CPRT']=codec.pd.Series(values,index=panel[name].index,dtype='int64' if name=='raw_volume' else 'float64');panel[name]=panel[name].reindex(sorted(panel[name].columns),axis=1)
    records=before['universe'].to_dict('records')+[dict(coordinate,risk_chain='automotive',median_dollar_volume_usd=numbers[2]['median'])]
    panel['universe']=codec.pd.DataFrame(sorted(records,key=lambda r:r['security_id']),columns=codec.UNIVERSE)
    proof={}
    for name in codec.FRAMES:
        original=before[name];projected=(panel[name].set_index('security_id',drop=False).loc[original['security_id'].tolist()].reset_index(drop=True) if name=='universe' else panel[name].loc[:,original.columns])
        require(codec.canonical(frame_payload(original))==codec.canonical(frame_payload(projected)),'Original20 exact frame')
        h=codec.sha(codec.canonical(frame_payload(original)));proof[name]=dict(original_sha256=h,projected_sha256=h,exact=True)
    panel.update(schema='LATEST_CONDITIONAL_TYPED_PANEL_V3',conditional_security_count=len(records),conditional_issuer_count=len({r['issuer_id'] for r in records}));panel['panel_content_sha256']=codec.checksum(panel)
    require((panel['conditional_security_count'],panel['conditional_issuer_count'])==(21,20),'Actual21/20 derived')
    old100=[r for r in before['observed_provenance_and_missing'] if r['ticker']!='CPRT']
    outer_false=('formal_input_ready','legal_training_input_admitted','point_in_time_verified','promotion_allowed','execution_authorized','strict_loader_validation_passed','fit_performed','enumeration_performed','raw_oracle_called','old_panel_assemble_called','old_numeric_values_recomputed','http_performed','full_transitive_source_closure_reverified','issuer_observation_currently_certified')
    return dict(schema='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V3',scope=codec.SCOPE,panel=codec.encode_frames(panel),original_evidence_and_projection=deepcopy(parent['original_evidence_and_projection']),incremental_evidence_and_projection=deepcopy(parent['incremental_evidence_and_projection']),v3_incremental_evidence_and_projection=[increment],original20_frame_exact_proof=proof,original100_gap_exact_sha256=codec.sha(codec.canonical(old100)),original100_gap_exact=True,input_references={role:ref(role) for role in BOUND},source_coordinate_candidate_count=wiring['candidate_security_count'],actual_panel_security_count=len(records),actual_panel_issuer_count=panel['conditional_issuer_count'],independently_audited_parent_reused=True,incremental_numeric_channels_calculated=['CPRT'],raw_volume_blocked_candidates=['CRWD'],numeric_projection_policy=parent['numeric_projection_policy'],issuer_observation_basis=parent['issuer_observation_basis'],source_decimal_quote_values_retained_in_new_channels=True,old_numeric_values_preserved_exactly=True,mapping_interface='selected_mapping_v3; V1_V2_SELECTED_MAPPING_INCOMPATIBLE_BY_SCHEMA',**dict.fromkeys(outer_false,False))


def build():
    require(PRODUCER_SHA is not None and CANDIDATE_SHA is not None,'Actual reviewed producer/candidate anchors pending')
    sources=dict(LOADED);guard(sources);documents={}
    producer_sources={str(PRODUCER):PRODUCER_SHA,str(CORE):CORE_SHA,str(PRODUCER_CODEC):PRODUCER_CODEC_SHA,
        str(Path(codec.pd.__file__).resolve()):LOADED[str(Path(codec.pd.__file__).resolve())]}
    for role in BOUND:
        reference=ref(role);raw=Path(reference['path']).read_bytes()
        require(codec.sha(raw)==reference['sha256'],'Consumed parent bytes differ')
        documents[role]=codec.loads(raw);sources[reference['path']]=reference['sha256']
        producer_sources[reference['path']]=reference['sha256']
    sources.update(producer_sources)
    raw=CANDIDATE.read_bytes();require(codec.sha(raw)==CANDIDATE_SHA,'Hard candidate differs')
    sources[str(CANDIDATE)]=CANDIDATE_SHA;guard(sources)
    decoded=verify_candidate(codec.loads(raw),documents,producer_sources)
    result=dict(schema='NEW_CUTOFF_TYPED_PANEL_INCREMENT_INDEPENDENT_READBACK_V3',status='PASSED',
        candidate_reference=dict(path=str(CANDIDATE),sha256=CANDIDATE_SHA),
        producer_reference=dict(path=str(PRODUCER),sha256=PRODUCER_SHA),
        input_references={role:ref(role) for role in BOUND},source_hashes=sources,
        panel_content_sha256=decoded['panel_content_sha256'],
        observed_security_count=101,observed_issuer_count=100,
        conditional_security_count=decoded['conditional_security_count'],conditional_issuer_count=decoded['conditional_issuer_count'],
        frame_shapes={name:list(decoded[name].shape) for name in codec.FRAMES},
        independently_recomputed_tickers=['CPRT'],increment_reconstruction_count=1,
        original_twenty_five_frames_exact=True,unchanged_other100_gaps_exact=True,
        full_original101_and_incremental_sidecars_compared=True,typed_roundtrip_exact=True,
        **dict.fromkeys(FALSE,False))
    guard(sources);return result


def publish():
    require(not OUTPUT.exists(),'Independent increment audit already exists')
    require(OUTPUT.parent.is_dir() and {p.name for p in OUTPUT.parent.iterdir()}=={'panel.json'},'Exact producer-only namespace required')
    value=build();guard(value['source_hashes']);raw=codec.pretty(value)
    with OUTPUT.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw,'Audit output readback differs')
    require({p.name for p in OUTPUT.parent.iterdir()}=={'panel.json',OUTPUT.name},'Unexpected audit namespace')
    return dict(path=str(OUTPUT),sha256=codec.sha(raw))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required');print(json.dumps(publish()))
