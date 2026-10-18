"""Append saved batch channels; preserve all sealed parent numeric columns and evidence."""
import argparse
from copy import deepcopy
from decimal import Context,localcontext,Decimal
import math
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
OUTPUT=BASE/'bulk_conditional_panel_20261003_v1/panel.json'
BOUND={
 'wiring':('bulk_conditional_wiring_20261003_v1/wiring.json','e4f4328043254667ff334ebc7aaf0fe530d451339f5b9d4b1ba0a20c37b9b8a5'),
 'wiring_publication':('bulk_conditional_wiring_20261003_v1/publication.json','7f9ba6d89271fded96727e4dbfdd08ccc58ff249d352fddf5f97a8366f345e12'),
 'parent_wiring':('new_cutoff_identity_risk_wiring_20260925_v6/wiring.json','1252cddfd4274ce8ce1f6a50c7e356fb790f45309bdd7146d71d317a754fd0fd'),
 'parent_panel':('new_cutoff_conditional_panel_20260925_v6/panel.json','d5feacbfbe85d38fd8c66aef9dc30686316cfd1c7ccaf4eafb58cc8c5e26e269'),
 'parent_readback':('new_cutoff_conditional_panel_20260925_v6/independent_increment_readback.json','6229a3655bb4d73c9d113d941f9dbec149da047c113be92193559cf5dbbd0717'),
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
        require(canonical(frame_payload(left))==canonical(frame_payload(right)),'Original twenty-four frame changed: '+name)
        proof[name]=dict(original_sha256=sha(canonical(frame_payload(left))),projected_sha256=sha(canonical(frame_payload(right))),exact=True)
    return proof


SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection',
 'v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection',
 'v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection')
INNER='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1'

def saved_channel_projection(value,calendar):
    """Reuse saved returns/closes/volume. Only project typed dollar-volume rounding."""
    require(value['schema']=='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1' and value['calendar']==calendar and value['cutoff']==calendar[-1], 'Saved channel contract')
    require(all(value[k] is False for k in core.CHANNEL_FALSE),'No numeric authority upgrade')
    prices,returns,liquid=value['price_rows'],value['price_returns'],value['liquidity']
    require(len(calendar)==127 and len(prices)==127 and len(returns)==126 and [r['session'] for r in prices]==calendar,'127/126 coverage')
    closes=[r['nominal_close'] for r in prices];ret=[r['price_return'] for r in returns]
    require(all(type(v) is float and math.isfinite(v) and v>0 for v in closes) and all(type(v) is float and math.isfinite(v) and v>-1 for v in ret),'Original finite float cells')
    require(all(r['previous_session']==calendar[i] and r['session']==calendar[i+1] for i,r in enumerate(returns)),'Adjacent saved return dates')
    if liquid['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN':return None,'BLOCKED_VOLUME_UNIT_UNKNOWN'
    require(liquid['status']=='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE' and type(liquid['numerical_threshold_passed']) is bool and len(liquid['rows'])==63,'Original volume gate')
    require(type(value['minimum_median_dollar_volume_usd']) is int and value['minimum_median_dollar_volume_usd']==50000000,'Original threshold unchanged')
    volumes=[r['raw_volume'] for r in liquid['rows']]
    require([r['session'] for r in liquid['rows']]==calendar[-63:] and all(type(v) is int and 0<v<2**63 for v in volumes),'63 exact int volume rows')
    with localcontext(Context(prec=50)):
        dollars=[Decimal(str(c))*v for c,v in zip(closes[-63:],volumes)];median=sorted(dollars)[31]
        if median<50000000 or liquid['numerical_threshold_passed'] is False:return None,'BELOW_ORIGINAL_LIQUIDITY_THRESHOLD'
    return (ret,closes,dict(volumes=volumes,dollars=[float(x) for x in dollars],median=float(median))),None

def selected_mapping_bulk(panel,security_ids):
    require(panel['schema']==INNER and panel['scope']==core.SCOPE and all(panel[k] is False for k in core.FALSE),'Versioned conditional mapping')
    require(core.panel_digest(panel)==panel['panel_content_sha256'],'Panel checksum')
    require(type(security_ids) is list and security_ids and len(set(security_ids))==len(security_ids),'Unique requested SID')
    universe=panel['universe'].to_dict('records');by={r['security_id']:r for r in universe}
    require(len(by)==len(universe) and all(s in by for s in security_ids),'Known unique SID')
    out={s:{k:by[s][k] for k in ('ticker','issuer_id','risk_chain')} for s in security_ids}
    require(len({r['issuer_id'] for r in out.values()})==len(out),'One security per issuer per portfolio')
    require(all(r['ticker'] in panel['returns'].columns and type(r['risk_chain']) is str and r['risk_chain'] for r in out.values()),'Selected ticker/risk missing')
    return out

def assemble(docs):
    w,oldw,parent,readback,ch,audit=(docs[k] for k in ('wiring','parent_wiring','parent_panel','parent_readback','channels','channel_audit'))
    publication=docs['wiring_publication']
    require(publication['schema']=='BULK_CONDITIONAL_WIRING_PUBLICATION_V1' and publication['status']=='PUBLISHED_CONDITIONAL_METADATA_ONLY' and publication['wiring_reference']==ref('wiring') and publication['source_hashes']==w['source_hashes'],'Wiring receipt differs')
    require(w['schema']=='BULK_CONDITIONAL_IDENTITY_RISK_WIRING_V1' and parent['schema']=='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V6','Versioned parents')
    require(all(d['promotion_allowed'] is False for d in docs.values()),'Parent authority')
    require(w['input_references']['parent']==ref('parent_wiring') and parent['input_references']['wiring']==ref('parent_wiring'),'Parent wiring lineage')
    require(readback['schema']=='NEW_CUTOFF_TYPED_PANEL_INCREMENT_INDEPENDENT_READBACK_V6' and readback['status']=='PASSED' and readback['candidate_reference']==ref('parent_panel') and readback['panel_content_sha256']==parent['panel']['panel_content_sha256'] and readback['full_original101_and_incremental_sidecars_compared'] is True,'Sealed parent readback')
    require(parent['input_references']['channels']==ref('channels') and parent['input_references']['channel_audit']==ref('channel_audit') and audit['candidate_reference']==ref('channels') and audit['status']=='PASSED' and type(audit['completed']) is int and audit['completed']==101,'Sealed numeric linkage')
    require(type(w['candidate_security_count']) is int and w['candidate_security_count']==78 and type(w['candidate_issuer_count']) is int and w['candidate_issuer_count']==77 and w['fit_column_count'] is None,'Candidate counts are not typed counts')
    calendar=ch['calendar'];require(w['calendar']==oldw['calendar']==calendar and len(calendar)==127 and calendar[0]=='2026-03-20' and calendar[-1]=='2026-09-21','Original calendar')
    names=[r['ticker'] for r in oldw['rows']]
    require(len(set(names))==len(names)==101 and all([r['ticker'] for r in rows]==names for rows in (w['rows'],ch['rows'],audit['details'])),'101 denominator/order')
    extensions=w['bulk_extended_provenance'];newnames=[e['ticker'] for e in extensions]
    require(len(newnames)==len(set(newnames))==53,'53 unique increments')
    for k in ('extended_provenance','v3_extended_provenance','v4_extended_provenance','v5_extended_provenance','v6_extended_provenance'):
        require(w[k]==oldw[k],'Original sidecars changed')
    for i,(row,old,channel,detail) in enumerate(zip(w['rows'],oldw['rows'],ch['rows'],audit['details'])):
        if row['ticker'] not in newnames:require(row==old,'Nonincrement wiring changed')
        else:require(old['coordinate'] is None and row['coordinate'] is not None,'Increment requires prior null')
        require(row['channel_reference']==ref('channels','/rows/'+str(i)) and row['channel_audit_reference']==ref('channel_audit','/details/'+str(i)) and row['channel_row_sha256']==sha(encode(channel)) and row['independent_channel_detail']==detail,'Original numerical evidence differs')
    before=codec.typed_decode(parent['panel']);require(before['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V6' and core.panel_digest(before)==before['panel_content_sha256'] and len(before['universe'])==24 and before['universe'].issuer_id.nunique()==23 and all(before[k] is False for k in core.FALSE),'Frozen24/23 parent')
    require(before['nominal_close'].index.tolist()==pd.DatetimeIndex(calendar).tolist() and [r['ticker'] for r in before['observed_provenance_and_missing']]==names,'Parent dates/full gaps')
    require('CRWD' not in before['returns'].columns and one(ch['rows'],'CRWD')['channel_input']['liquidity']['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN','CRWD remains blocked')
    panel=deepcopy(before);increments=[];new_universe=[];added=[];blocked={}
    for ticker in newnames:
        row=one(w['rows'],ticker);channel=one(ch['rows'],ticker)
        gap=one(panel['observed_provenance_and_missing'],ticker);oldgap=deepcopy(gap)
        require(row['coordinate']['issuer_id']==gap['observed_issuer_id'],'Observed issuer mismatch')
        gap.update(coordinate_assumption=dict(row['coordinate'],scope=core.SCOPE,dated_fact=None,dated_evidence_role='BULK_CROSS_DOCUMENT_CONDITIONAL_LINK_NOT_JOINT_DATED_PROOF',latest_interval_verified=False,provider_binding_verified=False,assumed_window=deepcopy(row['new_assumption']['window']),source_references=[ref('wiring')]),risk_assumption=dict(scope=core.SCOPE,risk_chain=row['risk_chain'],latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,source_kind='BULK_SAVED_CONDITIONAL_SEC_EVIDENCE_LINK',source_references=[ref('wiring')]),included_in_conditional_panel=True,blocking_reasons=[])
        require(ticker not in before['returns'].columns,'Only new channels')
        require(channel['status'] in {'CONDITIONAL_NUMERIC_RESULT','BLOCKED_PRICE_INPUT'},'Known original channel state')
        values,reason=(saved_channel_projection(channel['channel_input'],calendar) if channel['status']=='CONDITIONAL_NUMERIC_RESULT' else (None,'BLOCKED_PRICE_INPUT'))
        if reason is not None:
            blocked[ticker]=reason;gap.update(included_in_conditional_panel=False,blocking_reasons=[reason])
            increments.append(dict(ticker=ticker,complete_wiring_row=deepcopy(row),complete_extended_provenance=deepcopy(one(extensions,ticker)),original_gap=oldgap,new_gap=deepcopy(gap),numerical_column_added=False,blocking_reason=reason,early_window_review_availability_verified=False))
            continue
        added.append(ticker)
        coordinate=row['coordinate'];require(coordinate['ticker']==ticker and type(row['risk_chain']) is str and row['risk_chain'],'Conditional coordinate/risk required')
        for name,numbers in dict(returns=values[0],nominal_close=values[1],raw_volume=values[2]['volumes'],dollar_volume=values[2]['dollars']).items():
            require(len(numbers)==len(panel[name]),'New column shape');panel[name][ticker]=pd.Series(numbers,index=panel[name].index,dtype='int64' if name=='raw_volume' else 'float64')
        new_universe.append(dict(coordinate,risk_chain=row['risk_chain'],median_dollar_volume_usd=values[2]['median']))
        increments.append(dict(ticker=ticker,complete_wiring_row=deepcopy(row),complete_extended_provenance=deepcopy(one(extensions,ticker)),original_gap=oldgap,new_gap=deepcopy(gap),numerical_column_added=True,early_window_review_availability_verified=False))
    for name in FRAMES[:-1]:panel[name]=panel[name].reindex(sorted(panel[name].columns),axis=1)
    panel['universe']=pd.concat([panel['universe'],pd.DataFrame(new_universe,columns=panel['universe'].columns)],ignore_index=True).sort_values('security_id').reset_index(drop=True)
    require(panel['universe'].security_id.is_unique and panel['universe'].ticker.is_unique,'No duplicate SID/ticker')
    proof=original_frame_proof(before,panel);oldother=[r for r in before['observed_provenance_and_missing'] if r['ticker'] not in newnames]
    require(oldother==[r for r in panel['observed_provenance_and_missing'] if r['ticker'] not in newnames],'Other48 gaps changed')
    panel.update(schema=INNER,conditional_security_count=len(panel['universe']),conditional_issuer_count=panel['universe'].issuer_id.nunique())
    require(panel['conditional_security_count']==24+len(added),'Derived actual column count')
    panel['panel_content_sha256']=core.panel_digest(panel);encoded=codec.typed_encode(panel)
    require(core.panel_digest(codec.typed_decode(encoded))==panel['panel_content_sha256'],'Typed roundtrip')
    return dict(schema='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1',scope=core.SCOPE,panel=encoded,**{k:deepcopy(parent[k]) for k in SIDECARS},bulk_incremental_evidence_and_projection=increments,original24_frame_exact_proof=proof,original48_gap_exact=True,original48_gap_exact_sha256=sha(canonical(oldother)),input_references={k:ref(k) for k in BOUND},source_coordinate_candidate_count=78,actual_panel_security_count=panel['conditional_security_count'],actual_panel_issuer_count=panel['conditional_issuer_count'],expected_all_numeric_gates_pass_counts=dict(securities=77,issuers=76),incremental_numeric_channels_projected=added,new_numeric_blocks=blocked,saved_returns_closes_volumes_reused_exactly=True,typed_dollar_volume_projection_policy='DECIMAL_STR_SAVED_FLOAT_CLOSE_TIMES_VOLUME_PREC50_THEN_FLOAT_MEDIAN_SAME_DOMAIN',raw_volume_blocked_candidates=['CRWD'],parent_numeric_projection_policy_preserved=deepcopy(parent['numeric_projection_policy']),numeric_projection_policy='SAVED_RETURNS_CLOSES_VOLUMES_REUSED;NEW_DOLLARS_DECIMAL_STR_FLOAT_CLOSE_TIMES_INT_VOLUME_PREC50;NO_SAVED_DECIMAL_OR_RETURN_ORACLE_RECHECK',typed_projection_not_raw_quote_rebuild=True,saved_numeric_audit_assertions_reused_not_reexecuted=True,issuer_observation_basis=deepcopy(parent['issuer_observation_basis']),old_numeric_values_preserved_exactly=True,mapping_interface='selected_mapping_bulk; OLD_SCHEMA_MAPPINGS_INCOMPATIBLE',**dict.fromkeys(FALSE,False))

def read_inputs():
    require(all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'Actual pins pending')
    sources=dict(LOADED);guard(sources);docs={}
    for role in BOUND:
        r=ref(role)
        if role=='wiring':require({p.name for p in Path(r['path']).parent.iterdir()}=={'started.json','wiring.json','publication.json'},'Failed/incomplete wiring namespace')
        raw=Path(r['path']).read_bytes();require(sha(raw)==r['sha256'],'Consumed source hash differs');docs[role]=codec.loads(raw);sources[r['path']]=r['sha256']
    guard(sources);return docs,sources

def build():
    docs,sources=read_inputs();result=assemble(docs);result['source_hashes']=sources;guard(sources);return result

def write_new(path,value):
    raw=encode(value)
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Write readback');return sha(raw)

def publish():
    require(not OUTPUT.parent.exists(),'Fixed namespace exists; no retry')
    docs,sources=read_inputs();guard(sources);OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT.parent/'started.json',dict(source_hashes=sources,retry_allowed=False))
        value=assemble(docs);value['source_hashes']=sources;guard(sources)
        digest=write_new(OUTPUT,value);guard(value['source_hashes'])
        receipt=write_new(OUTPUT.parent/'publication.json',dict(schema='BULK_CONDITIONAL_PANEL_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_PANEL_ONLY',panel_reference=dict(path=str(OUTPUT),sha256=digest),source_hashes=value['source_hashes'],**dict.fromkeys(FALSE,False)))
        guard(value['source_hashes']);require(sha(OUTPUT.read_bytes())==digest and sha((OUTPUT.parent/'publication.json').read_bytes())==receipt and {p.name for p in OUTPUT.parent.iterdir()}=={'started.json','panel.json','publication.json'},'Final namespace/readback')
        return dict(path=str(OUTPUT),sha256=digest,publication_sha256=receipt)
    except Exception as error:
        write_new(OUTPUT.parent/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');require(parser.parse_args().publish,'Explicit --publish required');print(json.dumps(publish()))
