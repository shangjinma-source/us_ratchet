"""Independent PCAR-only projection audit; frozen nineteen columns are compared, not rebuilt."""
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

PRODUCER=ROOT/'scripts/ndx_new_cutoff_conditional_panel_v2_20260924.py'
PRODUCER_SHA='a7a815c179e39de7678f1cb90da7488ee0157e8de636d768ac96f01b03f1f9b1'
CANDIDATE=BASE/'new_cutoff_conditional_panel_20260924_v2/panel.json'
CANDIDATE_SHA='6dcd97bd87dfabab272dc50f9ac7d06e11410e1bf63d305596317236a348d412'
OUTPUT=CANDIDATE.parent/'independent_increment_readback.json'
CORE=ROOT/'backtest/ndx_latest_conditional_panel_research.py'
CORE_SHA='0d5c031f855348577bf9ffd17acf68998c86c43a60a45a05e014dc1e1ac34b59'
CODEC_SHA='0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'
PRODUCER_CODEC=ROOT/'scripts/ndx_new_cutoff_conditional_panel_20260923.py'
PRODUCER_CODEC_SHA='95bc442c379acb32b4c5d1c58a2eca6e0e2ad97bca9538249affe1a5e937236c'
BOUND={
 'wiring':('new_cutoff_identity_risk_wiring_20260924_v2/wiring.json','d374ee81bb6c9f0003f20a4c4e4a819b2a01cbbd638af43974baf64c9cd571df'),
 'parent_panel':('new_cutoff_conditional_panel_20260923_v1/panel.json','15c5d9449f10abeb7379baad9fd2b117b8fb84a24582190cf01b8d5b8dd8b047'),
 'parent_readback':('new_cutoff_conditional_panel_20260923_v1/independent_typed_readback.json','f3e55a68487c78f42d5b4dd7da12461177d472edcab89499697bbaa405c66fa8'),
 'channels':('new_cutoff_conditional_channels_20260923_v1/channels.json','3d708df6b273616edd46e06d2e2976acbc0e9fd90cc1243679ff94ca8befa3ac'),
 'channel_audit':('new_cutoff_conditional_channels_20260923_v1/independent_raw_decimal_audit.json','a11e7fb3b9006eba71b9d254557f713a32b2615407c9b8f77e7b24a8c01a2ace'),
}
LOADED={**codec.LOADED,str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
FALSE=('producer_called','panel_core_called','old_raw_oracle_called','old_typed_audit_repeated',
 'old_nineteen_numeric_channels_recomputed','http_performed','fit_performed','point_in_time_verified',
 'legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified')


def require(ok,message):
    if not ok:raise ValueError(message)


def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])


def guard(sources):
    require(LOADED[str(Path(codec.__file__).resolve())]==CODEC_SHA,'Frozen independent codec differs')
    for path,digest in {**sources,**LOADED}.items():
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
    require(parent['schema']=='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and
        previous['schema']=='NEW_CUTOFF_TYPED_PANEL_INDEPENDENT_READBACK_V1' and previous['status']=='PASSED', 'Audited parent schemas')
    require(previous['candidate_reference']==ref('parent_panel') and previous['full_101_gap_and_sidecar_compared'] is True and
        previous['typed_roundtrip_exact'] is True and type(previous['reconstruction_count']) is int and previous['reconstruction_count']==1,'Complete parent audit required')
    require(all(document['promotion_allowed'] is False for document in documents.values()),'Parent authority changed')
    before=codec.decode_frames(parent['panel']);panel=deepcopy(before)
    require(before['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V1' and before['conditional_security_count']==19 and
        before['conditional_issuer_count']==18 and previous['panel_content_sha256']==before['panel_content_sha256'],'Original nineteen required')
    require(all(before[key] is False for key in codec.PANEL_FALSE),'Panel authority changed')
    calendar=channels['calendar']
    require(wiring['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V2' and wiring['calendar']==calendar and
        calendar==[value.date().isoformat() for value in before['nominal_close'].index],'Same channel calendar')
    require(wiring['input_references']['original_wiring']==parent['input_references']['wiring'] and
        wiring['input_references']['channels']==ref('channels') and wiring['input_references']['audit']==ref('channel_audit') and
        audit['candidate_reference']==ref('channels') and audit['status']=='PASSED' and type(audit['completed']) is int and audit['completed']==101,'Parent lineage')
    original_rows=[item['wiring_row'] for item in parent['original_evidence_and_projection']]
    tickers=[row['ticker'] for row in original_rows]
    require(len(tickers)==len(set(tickers))==101 and all([row['ticker'] for row in rows]==tickers for rows in
        (wiring['rows'],channels['rows'],audit['details'],before['observed_provenance_and_missing'])),'Full101 ordering')
    require([row for row in wiring['rows'] if row['ticker'] not in ('PCAR','CRWD')]==
        [row for row in original_rows if row['ticker'] not in ('PCAR','CRWD')],'Other99 original wiring differs')
    require(wiring['candidate_security_count']==21 and wiring['candidate_issuer_count']==20,'Candidate denominator differs')
    for i,(row,channel,detail) in enumerate(zip(wiring['rows'],channels['rows'],audit['details'])):
        require(row['channel_reference']==dict(ref('channels'),json_pointer='/rows/'+str(i)) and
            row['channel_audit_reference']==dict(ref('channel_audit'),json_pointer='/details/'+str(i)) and
            row['channel_row_sha256']==codec.sha(codec.pretty(channel)) and row['independent_channel_detail']==detail,'Full channel audit binding')
    require(len(wiring['extended_provenance'])==2,'Exactly two source extensions')
    increments=[]
    for ticker in ('PCAR','CRWD'):
        row=one(wiring['rows'],ticker);extension=one(wiring['extended_provenance'],ticker)
        require(extension['original_row']==one(original_rows,ticker) and extension['prior_facts_modified'] is False,'Original extension row changed')
        gap=one(panel['observed_provenance_and_missing'],ticker);original_gap=deepcopy(gap)
        coordinate=row['coordinate'];require(coordinate['issuer_id']==gap['observed_issuer_id'],'Conditional observed issuer mismatch')
        if ticker=='PCAR':
            require(coordinate['security_id']=='security:0000075362:693718108' and row['risk_chain']=='automotive','PCAR coordinate/risk differs')
            fact=row['complete_original_evidence'][0]['complete_original_fact'];require(fact['risk_chain'] is None,'PCAR historical null changed')
            anchor=datetime.strptime(fact['dated_memo_facts'][0]['publication_date_text'],'%B %d, %Y').date().isoformat()
            require(anchor=='2023-01-05','Original PCAR memo date differs')
            role='ORIGINAL_MEMO_PUBLICATION_DATE_NOT_JOINT_AVAILABILITY';kind='NEW_CONDITIONAL_ANALYST_JUDGMENT'
        else:
            require(coordinate['security_id']=='security:0001535527:22788C105' and coordinate['security_class']=='CLASS_A_COMMON' and row['risk_chain']=='cybersecurity','CRWD coordinate/risk differs')
            anchor=extension['complete_increment_evidence']['memo_publication_date']
            require(anchor=='2026-06-09' and calendar[0]<anchor and extension['early_window_evidence_available'] is False,'CRWD early-window authority changed')
            blocked=one(channels['rows'],ticker)['channel_input']['liquidity']
            require(blocked['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN' and all(blocked[key] is None for key in ('rows','median_dollar_volume_usd','numerical_threshold_passed')),'CRWD volume must stay blocked')
            role='LATE_MEMO_PUBLICATION_NOT_EARLY_WINDOW_PROOF';kind='HISTORICAL_REVIEWED_BUSINESS_MATCH_WITH_CROSS_DOCUMENT_IDENTITY'
        require(row['new_assumed_window']=={'first':calendar[0],'last':calendar[-1]},'Explicit current assumption required')
        gap.update(coordinate_assumption=dict(coordinate,dated_fact=dict(coordinate,dated_as_of=anchor,source_references=[ref('wiring')]),
            scope=codec.SCOPE,latest_interval_verified=False,provider_binding_verified=False,assumed_window=deepcopy(row['new_assumed_window'])),
            risk_assumption=dict(scope=codec.SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,
                historical_labels=[row['risk_chain']],risk_chain=row['risk_chain'],source_references=[ref('wiring')],source_kind=kind),
            included_in_conditional_panel=ticker=='PCAR',blocking_reasons=[] if ticker=='PCAR' else ['BLOCKED_VOLUME_UNIT_UNKNOWN'])
        increments.append(dict(ticker=ticker,wiring_reference=dict(ref('wiring'),json_pointer='/rows/'+str(tickers.index(ticker))),
            complete_wiring_row=deepcopy(row),complete_extended_provenance=deepcopy(extension),original_gap=original_gap,new_gap=deepcopy(gap),
            dated_anchor_value=anchor,dated_anchor_role=role,early_window_evidence_available=False if ticker=='CRWD' else None,numerical_column_added=ticker=='PCAR'))
    channel=one(channels['rows'],'PCAR')['channel_input']
    require(channel['ticker']=='PCAR','PCAR numerical channel required')
    numbers=codec.channel_numbers(channel,calendar)
    require(numbers[3] is None and numbers[2] is not None,'PCAR numerical gate failed')
    sequences=dict(returns=numbers[0],nominal_close=numbers[1],raw_volume=numbers[2]['volumes'],dollar_volume=numbers[2]['dollars'])
    for name,values in sequences.items():
        require('PCAR' not in panel[name].columns and 'CRWD' not in panel[name].columns,'Increment already in parent')
        panel[name]['PCAR']=codec.pd.Series(values,index=panel[name].index,dtype='int64' if name=='raw_volume' else 'float64')
        panel[name]=panel[name].reindex(sorted(panel[name].columns),axis=1)
    pcar=one(wiring['rows'],'PCAR')
    records=before['universe'].to_dict('records')+[dict(pcar['coordinate'],risk_chain='automotive',median_dollar_volume_usd=numbers[2]['median'])]
    panel['universe']=codec.pd.DataFrame(sorted(records,key=lambda row:row['security_id']),columns=codec.UNIVERSE)
    proof={}
    for name in codec.FRAMES:
        original=before[name]
        projected=(panel[name].set_index('security_id',drop=False).loc[original['security_id'].tolist()].reset_index(drop=True)
            if name=='universe' else panel[name].loc[:,original.columns])
        require(codec.canonical(frame_payload(original))==codec.canonical(frame_payload(projected)),'Original frame changed')
        digest=codec.sha(codec.canonical(frame_payload(original)))
        proof[name]=dict(original_sha256=digest,projected_sha256=digest,exact=True)
    panel.update(schema='LATEST_CONDITIONAL_TYPED_PANEL_V2',conditional_security_count=len(records),conditional_issuer_count=len({row['issuer_id'] for row in records}))
    panel['panel_content_sha256']=codec.checksum(panel)
    old99=[row for row in before['observed_provenance_and_missing'] if row['ticker'] not in ('PCAR','CRWD')]
    outer_false=('formal_input_ready','legal_training_input_admitted','point_in_time_verified','promotion_allowed','execution_authorized',
        'strict_loader_validation_passed','fit_performed','enumeration_performed','raw_oracle_called','old_panel_assemble_called','old_numeric_values_recomputed',
        'http_performed','full_transitive_source_closure_reverified','issuer_observation_currently_certified')
    return dict(schema='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V2',scope=codec.SCOPE,panel=codec.encode_frames(panel),
        original_evidence_and_projection=deepcopy(parent['original_evidence_and_projection']),incremental_evidence_and_projection=increments,
        original19_frame_exact_proof=proof,original99_gap_exact_sha256=codec.sha(codec.canonical(old99)),original99_gap_exact=True,
        input_references={role:ref(role) for role in BOUND},source_coordinate_candidate_count=wiring['candidate_security_count'],
        actual_panel_security_count=len(records),actual_panel_issuer_count=panel['conditional_issuer_count'],
        independently_audited_parent_reused=True,incremental_numeric_channels_calculated=['PCAR'],raw_volume_blocked_candidates=['CRWD'],
        numeric_projection_policy=parent['numeric_projection_policy'],issuer_observation_basis=parent['issuer_observation_basis'],
        source_decimal_quote_values_retained_in_new_channels=True,old_numeric_values_preserved_exactly=True,
        mapping_interface='selected_mapping_v2; V1_SELECTED_MAPPING_INCOMPATIBLE_BY_SCHEMA',**dict.fromkeys(outer_false,False))


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
    result=dict(schema='NEW_CUTOFF_TYPED_PANEL_INCREMENT_INDEPENDENT_READBACK_V2',status='PASSED',
        candidate_reference=dict(path=str(CANDIDATE),sha256=CANDIDATE_SHA),
        producer_reference=dict(path=str(PRODUCER),sha256=PRODUCER_SHA),
        input_references={role:ref(role) for role in BOUND},source_hashes=sources,
        panel_content_sha256=decoded['panel_content_sha256'],
        observed_security_count=101,observed_issuer_count=100,
        conditional_security_count=decoded['conditional_security_count'],conditional_issuer_count=decoded['conditional_issuer_count'],
        frame_shapes={name:list(decoded[name].shape) for name in codec.FRAMES},
        independently_recomputed_tickers=['PCAR'],increment_reconstruction_count=1,
        original_nineteen_five_frames_exact=True,unchanged_other99_gaps_exact=True,
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
