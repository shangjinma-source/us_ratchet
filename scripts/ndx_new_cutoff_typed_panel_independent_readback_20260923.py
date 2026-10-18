"""Independent typed projection reader; never imports producer, panel core or raw oracle."""
import argparse
from copy import deepcopy
from datetime import date
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research'
SOURCE=Path(__file__).resolve()
PRODUCER=ROOT/'scripts/ndx_new_cutoff_conditional_panel_20260923.py'
PRODUCER_SHA='95bc442c379acb32b4c5d1c58a2eca6e0e2ad97bca9538249affe1a5e937236c'
CANDIDATE=BASE/'new_cutoff_conditional_panel_20260923_v1/panel.json'
CANDIDATE_SHA='15c5d9449f10abeb7379baad9fd2b117b8fb84a24582190cf01b8d5b8dd8b047'
OUTPUT=BASE/'new_cutoff_conditional_panel_20260923_v1/independent_typed_readback.json'
CORE=ROOT/'backtest/ndx_latest_conditional_panel_research.py'
CORE_SHA='0d5c031f855348577bf9ffd17acf68998c86c43a60a45a05e014dc1e1ac34b59'
BOUND={
 'wiring':('new_cutoff_identity_risk_wiring_20260923_v1/wiring.json','29da295126a93b842928d8df21142bcb846fc617b71886b2fb04507ff4adf3b4'),
 'channels':('new_cutoff_conditional_channels_20260923_v1/channels.json','3d708df6b273616edd46e06d2e2976acbc0e9fd90cc1243679ff94ca8befa3ac'),
 'audit':('new_cutoff_conditional_channels_20260923_v1/independent_raw_decimal_audit.json','a11e7fb3b9006eba71b9d254557f713a32b2615407c9b8f77e7b24a8c01a2ace'),
 'old_panel':('latest_fourteen_conditional_panel_20260919_v1/panel.json','63638aab89a75147f8d9a0eb827173a221aa81f0df7f47967f3e5a5f2fd76b61'),
}
SCOPE='CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY'
FRAMES=('returns','nominal_close','raw_volume','dollar_volume','universe')
UNIVERSE=['security_id','issuer_id','ticker','cusip','security_class','risk_chain','median_dollar_volume_usd']
PANEL_FALSE=('source_assertions_authenticated','formal_input_ready','legal_training_input_admitted','point_in_time_verified',
 'execution_authorized','promotion_allowed','historical_six_input_training_ready','strict_loader_validation_passed','fit_performed','winner_selected')
OUTER_FALSE=('old_build_called','old_numeric_values_reused','raw_prices_reconstructed','fitter_called','enumeration_performed',
 'formal_input_ready','legal_training_input_admitted','point_in_time_verified','promotion_allowed','execution_authorized',
 'strict_loader_validation_passed','full_transitive_source_closure_reverified','issuer_observation_currently_certified')
CHANNEL_FALSE=('source_assertions_authenticated','security_identity_verified','volume_units_independently_certified','complete_actions_verified',
 'exchange_calendar_verified','dividend_cash_flows_included','legal_training_input_admitted','fit_performed','point_in_time_verified','promotion_allowed')
ANCHOR_DATES={'ADBE':'2023-02-09','GOOGL':'2023-02-01','DDOG':'2023-02-14','QCOM':'2023-02-09','TXN':'2022-02-10'}
OLD_POINTER='/complete_original_evidence/0/original_provenance_row/coordinate_assumption/dated_fact/dated_as_of'
NEW_POINTER='/complete_original_evidence/0/complete_original_fact/evidence/dated_evidence'
POLICY='FROZEN_CORE_FLOAT_CLOSE_TO_DECIMAL_STR_TIMES_RAW_VOLUME_PREC50_THEN_FLOAT_DOLLAR_AND_MEDIAN;SAVED_DECIMAL_DOLLAR_VALIDATED_WITH_CORE_TOLERANCE'


def sha(raw):return hashlib.sha256(raw).hexdigest()
LOADED={str(p):sha(p.read_bytes()) for p in (SOURCE,Path(pd.__file__).resolve())}


def require(ok,message):
    if not ok:raise ValueError(message)


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def pretty(v):return (json.dumps(v,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def ref(role):return {'path':str(BASE/BOUND[role][0]),'sha256':BOUND[role][1]}


def loads(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    def fail(value):raise ValueError('Nonfinite JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=fail)


def pointer(value,path):
    for part in path.strip('/').split('/'):
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def finite(v):
    require(type(v) in (int,float,str,Decimal),'Nonboolean numeric required')
    x=Decimal(str(v));require(x.is_finite(),'Finite decimal required');return x


def as_float(v):
    x=float(v);require(math.isfinite(x),'Float overflow');return x


def channel_numbers(channel,calendar):
    """Recreate typed boundary from audited channel fields, not original provider raw."""
    require(channel['schema']=='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1' and channel['calendar']==calendar and channel['cutoff']==calendar[-1],'Channel calendar differs')
    require(all(channel.get(k) is False for k in CHANNEL_FALSE),'Channel authority upgraded')
    prices=channel['price_rows'];returns=channel['price_returns']
    require(len(prices)==127 and len(returns)==126 and [r['session'] for r in prices]==calendar,'127/126 adjacency required')
    closes=[finite(r['nominal_close']) for r in prices]
    require(all(x>0 for x in closes),'Positive prices required')
    values=[]
    with localcontext(Context(prec=50)):
        for i,row in enumerate(returns):
            require(row['previous_session']==calendar[i] and row['session']==calendar[i+1],'Return adjacency differs')
            require(type(row['declared_share_ratio']) is str,'Ratio text required')
            ratio=Fraction(row['declared_share_ratio']);require(ratio>0,'Positive ratio required')
            calculated=closes[i+1]*Decimal(ratio.numerator)/Decimal(ratio.denominator)/closes[i]-1
            saved=finite(row['price_return'])
            require(saved>-1 and abs(saved-calculated)<=Decimal('1e-12'),'Audited typed return mismatch')
            values.append(as_float(saved))
        liquidity=channel['liquidity']
        if liquidity['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN':
            require(all(liquidity[k] is None for k in ('rows','median_dollar_volume_usd','numerical_threshold_passed')),'Blocked liquidity has values')
            return values,list(map(as_float,closes)),None,'BLOCKED_VOLUME_UNIT_UNKNOWN'
        require(liquidity['status']=='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE' and len(liquidity['rows'])==63,'63 volume rows required')
        dollars=[];volumes=[]
        for day,close,row in zip(calendar[-63:],closes[-63:],liquidity['rows']):
            volume=row['raw_volume'];require(type(volume) is int and volume>0 and row['session']==day,'Raw volume/date invalid')
            dollar=close*volume
            require(abs(finite(row['dollar_volume'])-dollar)<=max(Decimal('1e-8'),abs(dollar)*Decimal('1e-12')),'Dollar tolerance differs')
            dollars.append(dollar);volumes.append(volume)
        median=sorted(dollars)[31]
        require(type(channel['minimum_median_dollar_volume_usd']) is int and channel['minimum_median_dollar_volume_usd']==50000000,'Threshold differs')
        require(abs(finite(liquidity['median_dollar_volume_usd'])-median)<=max(Decimal('1e-8'),abs(median)*Decimal('1e-12')) and liquidity['numerical_threshold_passed'] is (median>=50000000),'Median threshold differs')
        if median<50000000:return values,list(map(as_float,closes)),None,'BELOW_ORIGINAL_LIQUIDITY_THRESHOLD'
        return values,list(map(as_float,closes)),dict(volumes=volumes,dollars=list(map(as_float,dollars)),median=as_float(median)),None


def encode_frames(panel):
    result=deepcopy(panel)
    for name in FRAMES:
        f=panel[name]
        result[name]=dict(type='dataframe',index_kind='RangeIndex' if name=='universe' else 'DatetimeIndex',
          index=f.index.tolist() if name=='universe' else [v.isoformat() for v in f.index],columns=f.columns.tolist(),
          dtypes=[str(v) for v in f.dtypes],data=f.values.tolist())
    return result


def checksum(panel):
    value={}
    for key,item in panel.items():
        if key=='panel_content_sha256':continue
        value[key]=(dict(columns=item.columns.tolist(),index=[str(x) for x in item.index],index_type=type(item.index).__name__,
            dtypes=[str(x) for x in item.dtypes],data=item.values.tolist()) if isinstance(item,pd.DataFrame) else item)
    return sha(canonical(value))


def decode_frames(panel):
    result=deepcopy(panel)
    for name in FRAMES:
        item=panel[name]
        require(set(item)=={'type','index_kind','index','columns','dtypes','data'} and item['type']=='dataframe','Exact frame schema')
        columns=item['columns'];days=item['index'];rows=item['data'];dtypes=item['dtypes']
        require(len(columns)==len(set(columns))==len(dtypes) and all(type(c) is str and c for c in columns),'Unique columns')
        require(len(rows)==len(days) and all(type(r) is list and len(r)==len(columns) for r in rows),'Rectangular frame')
        if name=='universe':
            require(item['index_kind']=='RangeIndex' and all(type(x) is int for x in days) and days==list(range(len(days))),'Canonical universe index')
            require(columns==UNIVERSE and dtypes==['object']*6+['float64'],'Universe types')
            require(all(all(type(v) is str and v for v in r[:6]) and type(r[6]) is float and math.isfinite(r[6]) for r in rows),'Universe cell types')
            index=pd.RangeIndex(len(days))
        else:
            require(item['index_kind']=='DatetimeIndex' and days==sorted(set(days)) and all(type(x) is str and x==date.fromisoformat(x[:10]).isoformat()+'T00:00:00' for x in days),'Midnight ordered clock')
            dtype='int64' if name=='raw_volume' else 'float64'
            require(dtypes==[dtype]*len(columns),'Numerical dtypes')
            require(all(type(v) is int if dtype=='int64' else type(v) is float and math.isfinite(v) for r in rows for v in r),'Exact numeric cell type')
            index=pd.DatetimeIndex(days)
        frame=pd.DataFrame(rows,index=index,columns=columns)
        for col,dtype in zip(columns,dtypes):frame[col]=frame[col].astype(dtype)
        result[name]=frame
    require(canonical(encode_frames(result))==canonical(panel),'Codec roundtrip mismatch')
    require(checksum(result)==panel['panel_content_sha256'],'Mutation checksum mismatch')
    return result


def projections(docs):
    """Only source labels/sidecars here; no old numeric frame is consumed."""
    w,c,a,old=(docs[k] for k in ('wiring','channels','audit','old_panel'))
    require(all(d['promotion_allowed'] is False for d in docs.values()),'Parent permissions')
    require(w['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V1' and c['schema']=='NEW_CUTOFF_CONDITIONAL_CHANNELS_V1' and a['schema']=='NEW_CUTOFF_CHANNELS_INDEPENDENT_RAW_DECIMAL_AUDIT_V1' and a['status']=='PASSED' and type(a['completed']) is int and a['completed']==101,'Parent schemas')
    require(w['input_references']['channels']==ref('channels') and w['input_references']['audit']==ref('audit') and w['input_references']['panel']==ref('old_panel') and a['candidate_reference']==ref('channels'),'Parent reference binding')
    calendar=c['calendar'];require(calendar==w['calendar'] and len(calendar)==127 and calendar==sorted(set(calendar)) and calendar[0]=='2026-03-20' and calendar[-1]=='2026-09-21','127 calendar')
    oldrows=old['panel']['observed_provenance_and_missing'];tickers=[r['ticker'] for r in w['rows']]
    require(len(tickers)==len(set(tickers))==101 and all([r['ticker'] for r in rows]==tickers for rows in (oldrows,c['rows'],a['details'])),'101 same-order denominator')
    require(len({r['observed_issuer_id'] for r in oldrows})==100,'100 observed issuers')
    coordinates={};risks={};assertions={};numeric={};sidecars=[]
    for i,(row,channel,detail,observed) in enumerate(zip(w['rows'],c['rows'],a['details'],oldrows)):
        t=row['ticker']
        require(row['channel_reference']==dict(ref('channels'),json_pointer='/rows/'+str(i)) and row['channel_audit_reference']==dict(ref('audit'),json_pointer='/details/'+str(i)),'Exact row pointers')
        require(row['channel_row_sha256']==sha(pretty(channel)) and row['independent_channel_detail']==detail and detail['status']==channel['status'] and detail['reasons']==channel['reasons'],'Full row audit binding')
        if channel['status']=='CONDITIONAL_NUMERIC_RESULT':
            require(detail['decoded_sha256']==channel['raw_decoded_sha256'],'Raw audit hash')
            numeric[t]=channel['channel_input'];assertions[t]=dict(channel_sha256=sha(canonical(numeric[t])),passed=True,source_references=[ref('channels'),ref('audit')])
        else:require(channel['status']=='BLOCKED_PRICE_INPUT' and channel['channel_input'] is None,'Blocked numeric absent')
        side=dict(ticker=t,wiring_row=deepcopy(row),wiring_reference=dict(ref('wiring'),json_pointer='/rows/'+str(i)),
          observed_issuer_reference=dict(ref('old_panel'),json_pointer='/panel/observed_provenance_and_missing/'+str(i)+'/observed_issuer_id'))
        sidecars.append(side)
        if row['identity_risk_state']!='DATED_COORDINATE_AND_LEGACY_RISK_AVAILABLE_FOR_EXPLICIT_NEW_ASSUMPTION':continue
        fields=row['coordinate'];require(set(fields)=={'security_id','issuer_id','ticker','cusip','security_class'},'Coordinate fields')
        require(fields['ticker']==t and fields['issuer_id']==observed['observed_issuer_id'] and fields['security_id']=='security:'+fields['issuer_id'].removeprefix('issuer:')+':'+fields['cusip'],'SID/issuer/ticker match')
        require(row['new_assumed_window']=={'first':calendar[0],'last':calendar[-1]},'Window assumption')
        path=OLD_POINTER;role='ORIGINAL_SELECTED_DATED_ANCHOR_ROLE_PRESERVED_NOT_JOINT_AVAILABILITY'
        if t in ANCHOR_DATES:
            path=NEW_POINTER+('/evidence/dated_evidence/facts/filing_date' if t in ('ADBE','GOOGL') else '/filing_date')
            role='ORIGINAL_FILING_DATE_NOT_JOINT_INFORMATION_AVAILABILITY'
        day=pointer(row,path);require(type(day) is str and date.fromisoformat(day).isoformat()==day and day<=calendar[-1],'Dated fact clock')
        if t in ANCHOR_DATES:require(day==ANCHOR_DATES[t],'Exact original dated anchor')
        side.update(dated_anchor_reference=dict(ref('wiring'),json_pointer='/rows/'+str(i)+path),dated_anchor_role=role,dated_anchor_value=day)
        coordinates[t]=dict(fields,dated_fact=dict(fields,dated_as_of=day,source_references=[ref('wiring')]),scope=SCOPE,latest_interval_verified=False,provider_binding_verified=False,assumed_window=deepcopy(row['new_assumed_window']))
        source=row['risk_sources'][0]
        if 'original_risk_assumption' in source:
            risk=deepcopy(source['original_risk_assumption']);risk['source_references']=[ref('wiring')]
        else:
            labels={v['risk_chain'] for s in row['risk_sources'] for v in s['all_saved_observations']}
            require(labels=={row['risk_chain']},'Historical risk conflict')
            risk=dict(scope=SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,historical_labels=sorted(labels),risk_chain=row['risk_chain'],source_references=[ref('wiring')],source_kind='LEGACY_LOCAL_RISK_LABEL_NOT_NEW_ADJUDICATION')
        require(risk['risk_chain']==row['risk_chain'] and set(risk['historical_labels'])=={row['risk_chain']} and risk['scope']==SCOPE and risk['latest_interval_verified'] is False and risk['continued_historical_label_is_explicit_assumption'] is True,'Risk assumption authority')
        require(risk['source_kind'] in ('INDEPENDENT_REVIEWED_DATED_BUSINESS','LEGACY_LOCAL_RISK_LABEL_NOT_NEW_ADJUDICATION'),'Risk source role')
        risks[t]=risk
    require(len(coordinates)==19 and len({v['security_id'] for v in coordinates.values()})==19 and len({v['issuer_id'] for v in coordinates.values()})==18,'19SID/18issuer candidate denominator')
    return calendar,oldrows,numeric,assertions,coordinates,risks,sidecars


def reconstruct(docs):
    calendar,oldrows,channels,assertions,coords,risks,sidecars=projections(docs)
    selected=[];gaps=[];values={}
    for row in oldrows:
        t=row['ticker'];reasons=[];numbers=None
        if t not in channels:reasons.append('NO_COMPLETE_CONDITIONAL_CHANNEL')
        else:
            numbers=channel_numbers(channels[t],calendar)
            if numbers[3]:reasons.append(numbers[3])
        if t not in coords:reasons.append('NO_EXPLICIT_DATED_COORDINATE_ASSUMPTION')
        if t not in risks:reasons.append('NO_EXPLICIT_RESEARCH_RISK_ASSUMPTION')
        gaps.append(dict(ticker=t,observed_issuer_id=row['observed_issuer_id'],included_in_conditional_panel=not reasons,blocking_reasons=reasons,
          coordinate_assumption=deepcopy(coords.get(t)),risk_assumption=deepcopy(risks.get(t)),channel_audit_assertion=deepcopy(assertions.get(t)),source_assertions_authenticated=False,legal_training_input_admitted=False))
        if not reasons:
            selected.append({**{k:coords[t][k] for k in UNIVERSE[:5]},'risk_chain':risks[t]['risk_chain'],'median_dollar_volume_usd':numbers[2]['median']});values[t]=numbers
    cols=sorted(values);clock=pd.DatetimeIndex(calendar)
    panel=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V1',scope=SCOPE,cutoff='2026-09-21',
      returns=pd.DataFrame({t:values[t][0] for t in cols},index=clock[1:],dtype='float64'),
      nominal_close=pd.DataFrame({t:values[t][1] for t in cols},index=clock,dtype='float64'),
      raw_volume=pd.DataFrame({t:values[t][2]['volumes'] for t in cols},index=clock[-63:],dtype='int64'),
      dollar_volume=pd.DataFrame({t:values[t][2]['dollars'] for t in cols},index=clock[-63:],dtype='float64'),
      universe=pd.DataFrame(sorted(selected,key=lambda r:r['security_id']),columns=UNIVERSE),
      observed_provenance_and_missing=gaps,observed_security_count=101,observed_issuer_count=100,
      conditional_security_count=len(selected),conditional_issuer_count=len({r['issuer_id'] for r in selected}),
      candidate_cardinality_not_fixed=True,one_security_per_issuer_per_portfolio_required=True,historical_evaluation_505_rows_available=False,
      **dict.fromkeys(PANEL_FALSE,False))
    panel['panel_content_sha256']=checksum(panel)
    return dict(schema='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1',scope=SCOPE,panel=encode_frames(panel),
      original_evidence_and_projection=sidecars,input_references={k:ref(k) for k in BOUND},
      issuer_observation_basis='SAVED_101_ISSUER_COORDINATES_CONDITIONALLY_REUSED_NOT_NEW_QUOTE_LIST_CIK_CERTIFICATION',
      source_coordinate_candidate_count=19,actual_panel_security_count=len(selected),source_decimal_quote_values_retained_in_new_channels=True,
      numeric_projection_policy=POLICY,**dict.fromkeys(OUTER_FALSE,False))


def verify_candidate(candidate,docs,producer_sources):
    require(candidate['source_hashes']==producer_sources,'Exact direct producer source map')
    decoded=decode_frames(candidate['panel'])
    expected=reconstruct(docs)
    actual={k:v for k,v in candidate.items() if k!='source_hashes'}
    require(canonical(actual)==canonical(expected),'Full typed frames/gaps/sidecar/authority comparison differs')
    return decoded


def guard(sources):
    for path,digest in {**sources,**LOADED}.items():require(sha(Path(path).read_bytes())==digest,'Source drift: '+path)


def build():
    require(PRODUCER_SHA is not None and CANDIDATE_SHA is not None,'Actual producer/candidate anchors pending')
    sources=dict(LOADED);docs={}
    guard(sources)
    producer_sources={str(PRODUCER):PRODUCER_SHA,str(CORE):CORE_SHA,str(Path(pd.__file__).resolve()):LOADED[str(Path(pd.__file__).resolve())]}
    for role in BOUND:
        r=ref(role);raw=Path(r['path']).read_bytes();require(sha(raw)==r['sha256'],'Consumed parent bytes differ')
        docs[role]=loads(raw);sources[r['path']]=r['sha256'];producer_sources[r['path']]=r['sha256']
    sources.update(producer_sources)
    raw=CANDIDATE.read_bytes();require(sha(raw)==CANDIDATE_SHA,'Hard candidate differs');sources[str(CANDIDATE)]=CANDIDATE_SHA
    guard(sources)
    candidate=loads(raw);decoded=verify_candidate(candidate,docs,producer_sources)
    report=dict(schema='NEW_CUTOFF_TYPED_PANEL_INDEPENDENT_READBACK_V1',status='PASSED',
      candidate_reference=dict(path=str(CANDIDATE),sha256=CANDIDATE_SHA),producer_reference=dict(path=str(PRODUCER),sha256=PRODUCER_SHA),
      input_references={k:ref(k) for k in BOUND},source_hashes=sources,panel_content_sha256=decoded['panel_content_sha256'],
      independently_rebuilt_frames=list(FRAMES),full_101_gap_and_sidecar_compared=True,typed_roundtrip_exact=True,
      observed_security_count=101,conditional_security_count=decoded['conditional_security_count'],conditional_issuer_count=decoded['conditional_issuer_count'],
      frame_shapes={k:list(decoded[k].shape) for k in FRAMES},reconstruction_count=1,
      producer_called=False,panel_core_called=False,old_raw_oracle_called=False,
      http_performed=False,fit_performed=False,**dict.fromkeys(OUTER_FALSE,False))
    guard(sources);return report


def publish():
    require(not OUTPUT.exists(),'Independent audit already exists')
    require(OUTPUT.parent.is_dir() and {p.name for p in OUTPUT.parent.iterdir()}=={'panel.json'},'Exact producer-only namespace required')
    value=build();guard(value['source_hashes']);raw=pretty(value)
    with OUTPUT.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw,'Audit output readback differs')
    require({p.name for p in OUTPUT.parent.iterdir()}=={'panel.json',OUTPUT.name},'Unexpected audit namespace entry')
    return dict(path=str(OUTPUT),sha256=sha(raw))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');a=p.parse_args()
    require(a.publish,'Explicit --publish required');print(json.dumps(publish()))
