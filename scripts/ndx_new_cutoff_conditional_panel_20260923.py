"""Typed conditional panel projection from new audited channels and saved assumptions."""
import argparse
from copy import deepcopy
from datetime import date
from decimal import Context, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import pandas as pd

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
sys.path.insert(0,str(ROOT))
from backtest import ndx_latest_conditional_panel_research as core
CORE=Path(core.__file__).resolve();CORE_SHA='0d5c031f855348577bf9ffd17acf68998c86c43a60a45a05e014dc1e1ac34b59'
OUTPUT=BASE/'new_cutoff_conditional_panel_20260923_v1/panel.json'
LOADED={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (SOURCE,CORE,Path(pd.__file__).resolve())}
BOUND={
 'wiring':('new_cutoff_identity_risk_wiring_20260923_v1/wiring.json','29da295126a93b842928d8df21142bcb846fc617b71886b2fb04507ff4adf3b4'),
 'channels':('new_cutoff_conditional_channels_20260923_v1/channels.json','3d708df6b273616edd46e06d2e2976acbc0e9fd90cc1243679ff94ca8befa3ac'),
 'audit':('new_cutoff_conditional_channels_20260923_v1/independent_raw_decimal_audit.json','a11e7fb3b9006eba71b9d254557f713a32b2615407c9b8f77e7b24a8c01a2ace'),
 'old_panel':('latest_fourteen_conditional_panel_20260919_v1/panel.json','63638aab89a75147f8d9a0eb827173a221aa81f0df7f47967f3e5a5f2fd76b61'),
}
FRAMES=('returns','nominal_close','raw_volume','dollar_volume','universe')
FALSE=('old_build_called','old_numeric_values_reused','raw_prices_reconstructed','fitter_called','enumeration_performed',
 'formal_input_ready','legal_training_input_admitted','point_in_time_verified','promotion_allowed','execution_authorized',
 'strict_loader_validation_passed','full_transitive_source_closure_reverified','issuer_observation_currently_certified')
NEW_ANCHORS={
 'ADBE':('/complete_original_evidence/0/complete_original_fact/evidence/dated_evidence/evidence/dated_evidence/facts/filing_date','2023-02-09'),
 'GOOGL':('/complete_original_evidence/0/complete_original_fact/evidence/dated_evidence/evidence/dated_evidence/facts/filing_date','2023-02-01'),
 'DDOG':('/complete_original_evidence/0/complete_original_fact/evidence/dated_evidence/filing_date','2023-02-14'),
 'QCOM':('/complete_original_evidence/0/complete_original_fact/evidence/dated_evidence/filing_date','2023-02-09'),
 'TXN':('/complete_original_evidence/0/complete_original_fact/evidence/dated_evidence/filing_date','2022-02-10'),
}


def require(ok,message):
    if not ok:raise ValueError(message)


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key');result[key]=value
    return result


def loads(raw):
    def reject(value):raise ValueError('Nonfinite JSON literal')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject)


def encode(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def ref(role):
    relative,digest=BOUND[role];return dict(path=str(BASE/relative),sha256=digest)


def pointer(value,path):
    for token in path.strip('/').split('/'):
        token=token.replace('~1','/').replace('~0','~')
        value=value[int(token)] if isinstance(value,list) else value[token]
    return value


def guard(sources):
    require(LOADED[str(CORE)]==CORE_SHA,'Loaded core differs')
    for path,digest in {**sources,**LOADED}.items():require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'Source bytes changed')


def typed_encode(panel):
    result=deepcopy(panel)
    for name in FRAMES:
        frame=panel[name]
        require(isinstance(frame,pd.DataFrame),'DataFrame required')
        kind='DatetimeIndex' if isinstance(frame.index,pd.DatetimeIndex) else 'RangeIndex' if isinstance(frame.index,pd.RangeIndex) else None
        require(kind is not None,'Canonical typed index required')
        result[name]=dict(type='dataframe',index_kind=kind,index=[value.isoformat() for value in frame.index] if kind=='DatetimeIndex' else frame.index.tolist(),
            columns=frame.columns.tolist(),dtypes=[str(dtype) for dtype in frame.dtypes],data=frame.values.tolist())
    return result


def typed_decode(value):
    result=deepcopy(value)
    for name in FRAMES:
        item=value[name]
        require(set(item)=={'type','index_kind','index','columns','dtypes','data'} and item['type']=='dataframe','Exact typed keys required')
        columns=item['columns'];days=item['index'];dtypes=item['dtypes']
        require(len(columns)==len(set(columns))==len(dtypes) and all(type(col) is str and col for col in columns),'Unique string columns required')
        require(len(item['data'])==len(days) and all(type(row) is list and len(row)==len(columns) for row in item['data']),'Frame shape differs')
        if name=='universe':
            require(item['index_kind']=='RangeIndex' and all(type(v) is int for v in days) and days==list(range(len(days))),'Canonical RangeIndex required')
            require(columns==['security_id','issuer_id','ticker','cusip','security_class','risk_chain','median_dollar_volume_usd'] and dtypes==['object']*6+['float64'],'Universe dtype contract differs')
            require(all(all(type(v) is str and v for v in row[:6]) and type(row[6]) in (int,float) and math.isfinite(row[6]) for row in item['data']),'Universe cell type differs')
            index=pd.RangeIndex(len(days))
        else:
            require(item['index_kind']=='DatetimeIndex' and days==sorted(set(days)) and all(type(day) is str and day==date.fromisoformat(day[:10]).isoformat()+'T00:00:00' for day in days),'Canonical unique midnight dates required')
            dtype='int64' if name=='raw_volume' else 'float64'
            require(dtypes==[dtype]*len(columns),'Numeric dtype differs')
            require(all(type(v) is int if dtype=='int64' else type(v) in (int,float) and math.isfinite(v) for row in item['data'] for v in row),'Nonboolean numeric cells required')
            index=pd.DatetimeIndex(days)
        frame=pd.DataFrame(item['data'],columns=columns,index=index)
        for column,dtype in zip(columns,dtypes):frame[column]=frame[column].astype(dtype)
        result[name]=frame
    require(encode(typed_encode(result))==encode(value),'Typed payload exact roundtrip differs')
    return result


def project_inputs(docs):
    wiring=docs['wiring'];channels=docs['channels'];audit=docs['audit'];old=docs['old_panel']
    require(all(doc['promotion_allowed'] is False for doc in docs.values()),'Input authority upgraded')
    require(wiring['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V1' and channels['schema']=='NEW_CUTOFF_CONDITIONAL_CHANNELS_V1' and
        audit['schema']=='NEW_CUTOFF_CHANNELS_INDEPENDENT_RAW_DECIMAL_AUDIT_V1' and audit['status']=='PASSED' and type(audit['completed']) is int and audit['completed']==101,'Exact new input schemas required')
    require(wiring['input_references']['channels']==ref('channels') and wiring['input_references']['audit']==ref('audit') and
        wiring['input_references']['panel']==ref('old_panel') and audit['candidate_reference']==ref('channels'),'Hard input reference differs')
    calendar=channels['calendar'];require(calendar==wiring['calendar'] and len(calendar)==127 and calendar[0]=='2026-03-20' and calendar[-1]=='2026-09-21','New calendar differs')
    old_rows=old['panel']['observed_provenance_and_missing'];members=[row['ticker'] for row in wiring['rows']]
    require(len(members)==len(set(members))==101 and [row['ticker'] for row in old_rows]==members,'Saved and new101 exact order differs')
    require([row['ticker'] for row in channels['rows']]==[row['ticker'] for row in audit['details']]==members,'New channel/audit order differs')
    observed=[dict(ticker=row['ticker'],issuer_id=row['observed_issuer_id']) for row in old_rows]
    require(len({row['issuer_id'] for row in observed})==100,'Saved observed issuer denominator differs')
    numeric={};assertions={};coordinates={};risks={};evidence=[]
    for index,(row,channel,detail) in enumerate(zip(wiring['rows'],channels['rows'],audit['details'])):
        ticker=row['ticker'];require(row['channel_reference']==dict(ref('channels'),json_pointer='/rows/'+str(index)) and
            row['channel_audit_reference']==dict(ref('audit'),json_pointer='/details/'+str(index)),'Wiring row pointer differs')
        require(row['channel_row_sha256']==hashlib.sha256(encode(channel)).hexdigest() and row['independent_channel_detail']==detail and
            detail['status']==channel['status'] and detail['reasons']==channel['reasons'],'Wiring channel/audit content differs')
        if channel['status']=='CONDITIONAL_NUMERIC_RESULT':
            require(detail['decoded_sha256']==channel['raw_decoded_sha256'],'Audited raw hash differs')
            numeric[ticker]=deepcopy(channel['channel_input'])
            assertions[ticker]=dict(channel_sha256=core.canonical_sha(numeric[ticker]),passed=True,source_references=[ref('channels'),ref('audit')])
        else:require(channel['status']=='BLOCKED_PRICE_INPUT' and channel['channel_input'] is None,'Blocked channel must remain absent')
        sidecar=dict(ticker=ticker,wiring_row=deepcopy(row),wiring_reference=dict(ref('wiring'),json_pointer='/rows/'+str(index)),
            observed_issuer_reference=dict(ref('old_panel'),json_pointer='/panel/observed_provenance_and_missing/'+str(index)+'/observed_issuer_id'))
        evidence.append(sidecar)
        if row['identity_risk_state']!='DATED_COORDINATE_AND_LEGACY_RISK_AVAILABLE_FOR_EXPLICIT_NEW_ASSUMPTION':continue
        coord=row['coordinate'];require(coord['issuer_id']==observed[index]['issuer_id'],'Candidate issuer differs from saved observation')
        require(row['new_assumed_window']==dict(first=calendar[0],last=calendar[-1]),'Wiring conditional window differs')
        if ticker in NEW_ANCHORS:
            path,expected=NEW_ANCHORS[ticker];anchor=pointer(row,path);require(anchor==expected,'Original new candidate filing anchor differs')
            role='ORIGINAL_FILING_DATE_NOT_JOINT_INFORMATION_AVAILABILITY'
        else:
            path='/complete_original_evidence/0/original_provenance_row/coordinate_assumption/dated_fact/dated_as_of'
            anchor=pointer(row,path);role='ORIGINAL_SELECTED_DATED_ANCHOR_ROLE_PRESERVED_NOT_JOINT_AVAILABILITY'
        sidecar['dated_anchor_reference']=dict(ref('wiring'),json_pointer='/rows/'+str(index)+path)
        sidecar['dated_anchor_role']=role;sidecar['dated_anchor_value']=anchor
        coordinates[ticker]=dict(coord,dated_fact=dict(coord,dated_as_of=anchor,source_references=[ref('wiring')]),scope=core.SCOPE,
            latest_interval_verified=False,provider_binding_verified=False,assumed_window=deepcopy(row['new_assumed_window']))
        original=row['risk_sources'][0]
        if 'original_risk_assumption' in original:
            risk=deepcopy(original['original_risk_assumption']);require(risk['risk_chain']==row['risk_chain'],'Original risk differs')
            risk['source_references']=[ref('wiring')]
        else:
            labels={item['risk_chain'] for source in row['risk_sources'] for item in source['all_saved_observations']}
            require(labels=={row['risk_chain']},'All historical risk dates must agree')
            risk=dict(scope=core.SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,
                historical_labels=sorted(labels),risk_chain=row['risk_chain'],source_references=[ref('wiring')],source_kind='LEGACY_LOCAL_RISK_LABEL_NOT_NEW_ADJUDICATION')
        risks[ticker]=risk
    require(len(coordinates)==19 and set(coordinates)==set(risks),'19 candidates must retain explicit assumptions; inclusion is derived later')
    return dict(observed_rows=observed,calendar=calendar,cutoff='2026-09-21',channels=numeric,channel_audits=assertions,
                coordinate_assumptions=coordinates,risk_assumptions=risks),evidence


def assemble(docs):
    arguments,evidence=project_inputs(docs)
    with localcontext(Context(prec=80)):panel=core.assemble_conditional_panel(**arguments)
    encoded=typed_encode(panel);decoded=typed_decode(encoded)
    require(core.panel_digest(decoded)==decoded['panel_content_sha256'],'Panel checksum differs after typed roundtrip')
    for sid in decoded['universe']['security_id'].tolist():core.selected_mapping(decoded,[sid])
    return dict(schema='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1',scope=core.SCOPE,panel=encoded,
        original_evidence_and_projection=evidence,input_references={role:ref(role) for role in BOUND},
        issuer_observation_basis='SAVED_101_ISSUER_COORDINATES_CONDITIONALLY_REUSED_NOT_NEW_QUOTE_LIST_CIK_CERTIFICATION',
        source_coordinate_candidate_count=19,actual_panel_security_count=panel['conditional_security_count'],
        source_decimal_quote_values_retained_in_new_channels=True,old_numeric_values_reused=False,
        numeric_projection_policy='FROZEN_CORE_FLOAT_CLOSE_TO_DECIMAL_STR_TIMES_RAW_VOLUME_PREC50_THEN_FLOAT_DOLLAR_AND_MEDIAN;SAVED_DECIMAL_DOLLAR_VALIDATED_WITH_CORE_TOLERANCE',
        **{key:False for key in FALSE if key!='old_numeric_values_reused'})


def build():
    sources=dict(LOADED);guard(sources);docs={}
    for role in BOUND:
        reference=ref(role);raw=Path(reference['path']).read_bytes()
        require(hashlib.sha256(raw).hexdigest()==reference['sha256'],'Consumed source SHA differs')
        sources[reference['path']]=reference['sha256'];docs[role]=loads(raw)
    value=assemble(docs);value['source_hashes']=sources;guard(sources);return value


def publish():
    require(not OUTPUT.parent.exists(),'Fresh fixed namespace required')
    value=build();guard(value['source_hashes']);raw=encode(value)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw,'Published bytes differ')
    require({path.name for path in OUTPUT.parent.iterdir()}=={'panel.json'},'Unexpected namespace entry')
    return dict(path=str(OUTPUT),sha256=hashlib.sha256(raw).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required');print(json.dumps(publish()))
