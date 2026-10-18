"""Source-bound nine-coordinate research panel, preserving all 101 observed gaps."""
import argparse,copy,gzip,hashlib,json,sys
from datetime import datetime
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_latest_conditional_panel_research as core
from backtest import ndx_root_price_archive_contract_research as archive
from scripts import ndx_latest_conditional_channels_independent_audit_20260919 as batch
from scripts import ndx_latest_fifteen_coordinate_plan_20260919 as planning
from scripts import ndx_seven_dated_identity_assembly_20260919 as seven
from scripts import ndx_nflx_panw_conditional_identity_20260919 as two
BASE=ROOT/'data/cache/research'
CORE_SHA='0d5c031f855348577bf9ffd17acf68998c86c43a60a45a05e014dc1e1ac34b59'
ANCHORS={
 'plan':('latest_conditional_channels_20260919_v1/plan.json','440851a7b7a944a52a7a3d978f4430cf5d0d3f2e4a0553d76c6170c4df45379e'),
 'index':('latest_conditional_channels_20260919_v1/tasks/index_6b031ed505bb2553928c5e662222e6015183d013be8e259c2f0510e0fa8b89a8.json','0296915fdd34b8027c45a1052d648e6f7697842a649468ccc27fdba47bbb326a'),
 'audit':('latest_conditional_channels_20260919_v1/independent_raw_decimal_audit.json','9ab1922b3b37c6926d85596bb99ed08787e92403afa6e8f45452654649530eaa'),
 'fifteen':('latest_security_source_inventory_20260919_v1/fifteen_coordinate_plan.json','cac8f58e3db3278279ba8968e365911b52d06f72a5a504359e5c07b08e999d67'),
 'two':('nflx_panw_conditional_identity_20260919_v1/identities.json','9731a10723cf13970c47ea43ab2e141dfbaa1d4f46d778530fc8efdde1246132'),
 'seven':('seven_dated_identity_assembly_20260919_v1/identities.json','ed810b2fc1626e05f3c1edee10212645dad37435461b8b7e8d01dcba1354e7c2'),
 'four':('four_issuer_filing_identity_20260912_v1/dated_identity_adjudication.json','a70551b92c2154b9b1efe5eadb35b1f3c0f34b1c9a858506e3a2085df888d8a4'),
 'observed':('latest_all_ndx_conditional_manifest_20260919_v1/manifest.json','be842f56db29f989af87885079c8807334089b36334c4c8c743d9ab2c33007e2')}
TICKERS={'AMAT','ADI','CDNS','AVGO','FTNT','GOOG','BKR','NFLX','PANW'}
FRAMES=('returns','nominal_close','raw_volume','dollar_volume','universe')
LOADED={str(Path(m.__file__).resolve()):archive.drift.file_sha(m.__file__) for m in (core,archive,batch,planning,seven,two)}
LOADED[str(Path(__file__).resolve())]=archive.drift.file_sha(__file__)


def reference(key):
    p,h=ANCHORS[key];return dict(path=str(BASE/p),sha256=h)


def typed_encode(panel):
    result=copy.deepcopy(panel)
    for name in FRAMES:
        frame=panel[name]
        result[name]=dict(type='dataframe',index_kind='DatetimeIndex' if isinstance(frame.index,pd.DatetimeIndex) else 'RangeIndex' if isinstance(frame.index,pd.RangeIndex) else 'Index',
            index=[x.isoformat() for x in frame.index] if isinstance(frame.index,pd.DatetimeIndex) else frame.index.tolist(),
            columns=frame.columns.tolist(),dtypes=[str(d) for d in frame.dtypes],data=frame.values.tolist())
    return result


def typed_decode(value):
    result=copy.deepcopy(value)
    for name in FRAMES:
        item=value[name]
        if set(item)!={'type','index_kind','index','columns','dtypes','data'} or item['type']!='dataframe' or item['index_kind'] not in ('DatetimeIndex','RangeIndex','Index'):raise ValueError('Exact typed frame required')
        if len(set(item['columns']))!=len(item['columns']) or len(item['columns'])!=len(item['dtypes']):raise ValueError('Unique typed columns required')
        if item['index_kind']=='RangeIndex':
            numbers=item['index']
            if any(type(v) is not int for v in numbers):raise ValueError('Exact integer range index required')
            step=numbers[1]-numbers[0] if len(numbers)>1 else 1
            if step==0:raise ValueError('Nonzero range index step required')
            index=pd.RangeIndex(numbers[0],numbers[-1]+step,step) if numbers else pd.RangeIndex(0)
            if index.tolist()!=numbers:raise ValueError('Contiguous range index required')
        else:index=pd.DatetimeIndex(item['index']) if item['index_kind']=='DatetimeIndex' else pd.Index(item['index'])
        frame=pd.DataFrame(item['data'],columns=item['columns'],index=index)
        for col,dtype in zip(item['columns'],item['dtypes']):frame[col]=frame[col].astype(dtype)
        result[name]=frame
    if not batch.exact(typed_encode(result),value):raise ValueError('Typed payload failed exact roundtrip')
    return result


def coordinate_from_fact(ticker,fact,source_key,calendar,cover_period=None):
    if source_key=='four':
        anchor=datetime.strptime(fact['sec_filed_as_of_date'],'%Y%m%d').date().isoformat()
        sid=fact['security_id'];iid='issuer:'+fact['issuer_cik'];title=fact['security_class_cover']
    elif source_key=='seven':
        e=fact['evidence'];anchor=e['memo_date'] if ticker=='FTNT' else e['dated_readback']['filing_date']
        sid=fact['security_id'];iid=fact['issuer_id'];title=fact['security_class']
    elif source_key=='two':
        anchor=datetime.strptime(fact['memo_document_date'],'%B %d, %Y').date().isoformat()
        sid=fact['conditional_research_security_id'];iid=fact['issuer_id'];title=fact['security_class']
    else:raise ValueError('Only hard dated evidence categories supported')
    fields=dict(ticker=ticker,security_id=sid,issuer_id=iid,cusip=fact['cusip'],security_class=title)
    return dict(**fields,scope=core.SCOPE,latest_interval_verified=False,provider_binding_verified=False,
        assumed_window=dict(first=calendar[0],last=calendar[-1]),
        dated_fact=dict(**fields,dated_as_of=anchor,source_references=[reference(source_key)]))


def supplemental_provenance(fact,coordinate,plan_row,cover_period=None):
    return dict(date_role='SELECTED_DATED_FACT_ANCHOR_NOT_JOINT_AVAILABILITY',
        selected_dated_anchor=coordinate['dated_fact']['dated_as_of'],complete_original_fact=copy.deepcopy(fact),
        separately_observed_cover_period=cover_period,distinct_filing_period_event_receipt_dates_preserved=True,
        joint_historical_availability_inferred=False,original_risk_plan_row=copy.deepcopy(plan_row))


def build():
    if CORE_SHA is None or LOADED[str(Path(core.__file__).resolve())]!=CORE_SHA:raise ValueError('Panel core must be independently sealed first')
    sources=dict(LOADED)
    def read(ref):return batch.read(ref,sources)
    docs={k:read(reference(k)) for k in ANCHORS}
    for doc in docs.values():
        for key in ('source_hashes','historical_expected_source_hashes'):
            if key in doc:archive.merge(sources,doc[key])
    if not batch.exact(docs['fifteen'],planning.build()) or not batch.exact(docs['seven'],seven.build()) or not batch.exact(docs['two'],two.build()):raise ValueError('Original source relationship reconstruction differs')
    plan=docs['plan'];index=docs['index'];audit=docs['audit'];folder=Path(reference('index')['path']).parent
    batch.validate_index(index,ANCHORS['plan'][1],folder,plan['tasks'])
    if audit['schema']!='LATEST_CONDITIONAL_CHANNELS_INDEPENDENT_AUDIT_V1' or audit['plan']!=reference('plan') or audit['index']!=reference('index') or type(audit['completed']) is not int or audit['completed']!=101 or audit['numerical_channels']!=96 or audit['blocked_history_or_price']!=5:raise ValueError('Hard full independent audit linkage differs')
    for flag in ('owner_numerical_kernel_called','security_identity_verified','complete_actions_verified','fit_performed','legal_training_input_admitted','point_in_time_verified','promotion_allowed'):
        if audit[flag] is not False:raise ValueError('Independent audit scope differs')
    if len(audit['details'])!=101 or [d['ticker'] for d in audit['details']]!=[t['ticker'] for t in plan['tasks']]:raise ValueError('Full audited detail denominator differs')
    archive.verify_expected_sources(sources,archive.load_contract())
    channels={};assertions={}
    for entry,task,detail in zip(index['entries'],plan['tasks'],audit['details']):
        value=read(dict(path=entry['path'],sha256=entry['sha256']));batch.validate_wrapper(value,task,ANCHORS['plan'][1])
        marker=read(dict(path=str(folder/(task['ticker']+'.started.json')),sha256=entry['started_sha256']))
        if not batch.exact(marker,dict(schema='LATEST_CHANNEL_ATTEMPT_V1',plan_sha256=ANCHORS['plan'][1],task=task,attempt_count=1)):raise ValueError('Task marker differs')
        if detail['status']!=value['status'] or detail['reason']!=task['reason']:raise ValueError('Audit task relation differs')
        if task['mode']=='BLOCKED':
            if detail['audit'] is not None:raise ValueError('Blocked channel acquired audit')
            continue
        channel=value['result'];t=task['ticker'];a=detail['audit']
        if a['ticker']!=t or a['price_count']!=127 or a['return_count']!=126 or a['liquidity_status']!=channel['liquidity']['status']:raise ValueError('Full actual channel audit differs')
        channels[t]=channel;assertions[t]=dict(channel_sha256=core.canonical_sha(channel),passed=True,source_references=[reference('audit'),dict(path=entry['path'],sha256=entry['sha256'])])
    calendar=docs['observed']['observed_reference_calendar'][-127:]
    proposals={r['ticker']:r for r in docs['fifteen']['rows']};coordinates={};risks={};supplemental={}
    if set(docs['fifteen']['proposed_first_research_subset'])!={'AMAT','ADI','CDNS','AVGO','FTNT','GOOG','BKR'} or {r['ticker'] for r in docs['two']['rows']}!={'NFLX','PANW'}:raise ValueError('Exact evidence-selected cohort differs')
    for t in sorted(TICKERS):
        key='two' if t in ('NFLX','PANW') else 'four' if t in ('AMAT','AVGO','CDNS','GOOG') else 'seven'
        fact,=[r for r in docs[key]['rows'] if r['ticker']==t];period=None
        if t=='FTNT':
            p=Path(fact['evidence']['cover_path']).resolve();raw=p.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=sources[str(p)]:raise ValueError('FTNT original cover differs')
            decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            soup=BeautifulSoup(decoded,'html.parser');nodes=[n for n in soup.find_all() if n.get('name','').lower()=='dei:documentperiodenddate']
            observations=[dict(context=n.get('contextref'),original_text=n.get_text(' ',strip=True)) for n in nodes]
            symbols=[n for n in soup.find_all() if n.get('name','').lower()=='dei:tradingsymbol' and n.get_text(' ',strip=True)=='FTNT']
            if len(symbols)!=1 or not observations or {o['context'] for o in observations}!={symbols[0].get('contextref')} or len({' '.join(o['original_text'].split()) for o in observations})!=1:raise ValueError('Consistent original FTNT same-context cover period required')
            period=observations
        coordinates[t]=coordinate_from_fact(t,fact,key,calendar,period)
        p=proposals[t]
        supplemental[t]=supplemental_provenance(fact,coordinates[t],p,period)
        risks[t]=dict(scope=core.SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,
            historical_labels=[p['risk_chain_candidate']],risk_chain=p['risk_chain_candidate'],source_kind=p['risk_source_kind'],source_references=[reference('fifteen')])
    observed=[dict(ticker=r['ticker'],issuer_id=r['conditional_issuer_id']) for r in docs['observed']['rows']]
    panel=core.assemble_conditional_panel(observed_rows=observed,calendar=calendar,cutoff='2026-09-17',channels=channels,channel_audits=assertions,coordinate_assumptions=coordinates,risk_assumptions=risks)
    if set(panel['returns'].columns)!=TICKERS or panel['conditional_security_count']!=9:raise ValueError('Exact nine evidence/liquidity-supported channels required')
    encoded=typed_encode(panel);typed_decode(encoded)
    partition=archive.verify_expected_sources(sources,archive.load_contract())
    return dict(schema='SOURCE_BOUND_LATEST_NINE_CONDITIONAL_PANEL_V1',panel=encoded,supplemental_dated_and_risk_provenance=supplemental,input_references={k:reference(k) for k in ANCHORS},historical_expected_source_hashes=sources,archive_resolution=partition,
        subset_selection_basis='DATED_COORDINATE_AND_DECLARED_RISK_AND_LIQUIDITY_EVIDENCE_NOT_RETURN_RANKING',target_cardinality_fixed=False,
        source_bytes_bound=True,source_point_in_time_verified=False,legal_training_input_admitted=False,historical_six_input_training_ready=False,fit_performed=False,execution_authorized=False,winner_selected=False,promotion_allowed=False)


def verify(value):
    if value['schema']!='SOURCE_BOUND_LATEST_NINE_CONDITIONAL_PANEL_V1' or any(value[k] is not False for k in ('target_cardinality_fixed','source_point_in_time_verified','legal_training_input_admitted','historical_six_input_training_ready','fit_performed','execution_authorized','winner_selected','promotion_allowed')):raise ValueError('Conditional research boundary differs')
    required=dict(LOADED,**{str(BASE/p):h for p,h in ANCHORS.values()})
    if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in required.items()):raise ValueError('Required sources omitted')
    decoded=typed_decode(value['panel'])
    if set(decoded['returns'].columns)!=TICKERS or len(decoded['observed_provenance_and_missing'])!=101 or any(decoded[k] is not False for k in core.FALSE):raise ValueError('Full panel denominator/scope differs')
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source partition differs')
    if not batch.exact(value,build()):raise ValueError('Complete source-bound panel does not reproduce')


def publish_verified(path,value):
    verify(value);saved=batch.recipe.exclusive_publish(path,value);verify(value);return saved


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();v=build();print(json.dumps(publish_verified(a.output,v)))
