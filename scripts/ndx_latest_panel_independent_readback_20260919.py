"""Saved panel readback: reconstruct frames from sealed channels, never assemble or fit."""
import argparse
import copy
import gzip
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from scripts import ndx_latest_conditional_channels_independent_audit_20260919 as saved
BASE=ROOT/'data/cache/research'
OWNER=ROOT/'scripts/ndx_latest_conditional_panel_20260919.py'
OWNER_SHA='49a8b9374c2a994e7a3175609da436532b4aeb6d8d6a62042bab02f98c36bd20'
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
FALSE=('source_assertions_authenticated','formal_input_ready','legal_training_input_admitted','point_in_time_verified',
       'execution_authorized','promotion_allowed','historical_six_input_training_ready','strict_loader_validation_passed','fit_performed','winner_selected')
SCOPE='CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(saved.__file__).resolve())}


def exact(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def ref(key):
    p,h=ANCHORS[key];return dict(path=str(BASE/p),sha256=h)


def frame_payload(frame):
    return dict(type='dataframe',index_kind=type(frame.index).__name__,
        index=[v.isoformat() for v in frame.index] if isinstance(frame.index,pd.DatetimeIndex) else frame.index.tolist(),
        columns=frame.columns.tolist(),dtypes=[str(v) for v in frame.dtypes],data=frame.values.tolist())


def coordinate_fact(ticker,fact,key,calendar):
    if key=='four':
        day=datetime.strptime(fact['sec_filed_as_of_date'],'%Y%m%d').date().isoformat()
        sid=fact['security_id'];issuer='issuer:'+fact['issuer_cik'];title=fact['security_class_cover']
    elif key=='seven':
        day=fact['evidence']['memo_date'] if ticker=='FTNT' else fact['evidence']['dated_readback']['filing_date']
        sid=fact['security_id'];issuer=fact['issuer_id'];title=fact['security_class']
    else:
        day=datetime.strptime(fact['memo_document_date'],'%B %d, %Y').date().isoformat()
        sid=fact['conditional_research_security_id'];issuer=fact['issuer_id'];title=fact['security_class']
    fields=dict(ticker=ticker,security_id=sid,issuer_id=issuer,cusip=fact['cusip'],security_class=title)
    return dict(**fields,scope=SCOPE,latest_interval_verified=False,provider_binding_verified=False,
        assumed_window=dict(first=calendar[0],last=calendar[-1]),
        dated_fact=dict(**fields,dated_as_of=day,source_references=[ref(key)]))


def inspect(value,docs,wrappers,cover_periods):
    """Pure independent comparison, supplied hard references are verified by build."""
    calendar=docs['observed']['observed_reference_calendar'][-127:]
    if len(calendar)!=127 or calendar[-1]!='2026-09-17' or calendar!=sorted(set(calendar)):
        raise ValueError('Hard latest date contract differs')
    proposals={r['ticker']:r for r in docs['fifteen']['rows']}
    coordinates={};risks={};supplemental={};channels={};assertions={};missing=[]
    for ticker in sorted(TICKERS):
        key='two' if ticker in ('NFLX','PANW') else 'four' if ticker in ('AMAT','AVGO','CDNS','GOOG') else 'seven'
        fact,=[r for r in docs[key]['rows'] if r['ticker']==ticker]
        coordinate=coordinate_fact(ticker,fact,key,calendar);coordinates[ticker]=coordinate
        proposal=proposals[ticker]
        risks[ticker]=dict(scope=SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,
            historical_labels=[proposal['risk_chain_candidate']],risk_chain=proposal['risk_chain_candidate'],
            source_kind=proposal['risk_source_kind'],source_references=[ref('fifteen')])
        supplemental[ticker]=dict(date_role='SELECTED_DATED_FACT_ANCHOR_NOT_JOINT_AVAILABILITY',
            selected_dated_anchor=coordinate['dated_fact']['dated_as_of'],
            complete_original_fact=copy.deepcopy(fact),separately_observed_cover_period=cover_periods.get(ticker),
            distinct_filing_period_event_receipt_dates_preserved=True,joint_historical_availability_inferred=False,
            original_risk_plan_row=copy.deepcopy(proposal))
    for entry,task in zip(docs['index']['entries'],docs['plan']['tasks']):
        wrapper=wrappers[task['ticker']]
        if task['mode']=='BLOCKED':continue
        channel=wrapper['result'];ticker=task['ticker'];channels[ticker]=channel
        assertions[ticker]=dict(channel_sha256=digest(channel),passed=True,
            source_references=[ref('audit'),dict(path=entry['path'],sha256=entry['sha256'])])
    for observed in docs['observed']['rows']:
        ticker=observed['ticker'];reasons=[]
        if ticker not in channels:reasons.append('NO_COMPLETE_CONDITIONAL_CHANNEL')
        elif channels[ticker]['liquidity']['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN':reasons.append('BLOCKED_VOLUME_UNIT_UNKNOWN')
        elif channels[ticker]['liquidity']['numerical_threshold_passed'] is False:reasons.append('BELOW_ORIGINAL_LIQUIDITY_THRESHOLD')
        if ticker not in coordinates:reasons.append('NO_EXPLICIT_DATED_COORDINATE_ASSUMPTION')
        if ticker not in risks:reasons.append('NO_EXPLICIT_RESEARCH_RISK_ASSUMPTION')
        missing.append(dict(ticker=ticker,observed_issuer_id=observed['conditional_issuer_id'],included_in_conditional_panel=not reasons,
            blocking_reasons=reasons,coordinate_assumption=coordinates.get(ticker),risk_assumption=risks.get(ticker),
            channel_audit_assertion=assertions.get(ticker),source_assertions_authenticated=False,legal_training_input_admitted=False))
    if len(missing)!=101 or {r['ticker'] for r in missing if r['included_in_conditional_panel']}!=TICKERS:
        raise ValueError('Complete observed cohort or evidence-selected subset differs')
    columns=sorted(TICKERS);index=pd.DatetimeIndex(calendar)
    frames={}
    definitions={'returns':('price_returns','price_return',126,index[1:],'float64'),
                 'nominal_close':('price_rows','nominal_close',127,index,'float64'),
                 'raw_volume':('liquidity','raw_volume',63,index[-63:],'int64'),
                 'dollar_volume':('liquidity','dollar_volume',63,index[-63:],'float64')}
    for name,(section,field,count,dates,dtype) in definitions.items():
        values={}
        for ticker in columns:
            rows=channels[ticker][section] if section!='liquidity' else channels[ticker]['liquidity']['rows']
            if len(rows)!=count or [r['session'] for r in rows]!=[d.date().isoformat() for d in dates]:raise ValueError('Original saved channel dates differ')
            if name=='returns' and [r['previous_session'] for r in rows]!=calendar[:-1]:raise ValueError('Original predecessor differs')
            if name=='raw_volume' and any(type(r[field]) is not int for r in rows):raise ValueError('Original volume type differs')
            values[ticker]=[r[field] for r in rows]
        frames[name]=pd.DataFrame(values,index=dates,dtype=dtype)
    universe=[]
    for ticker in columns:
        c=coordinates[ticker]
        universe.append({**{k:c[k] for k in ('security_id','issuer_id','ticker','cusip','security_class')},
            'risk_chain':risks[ticker]['risk_chain'],'median_dollar_volume_usd':float(channels[ticker]['liquidity']['median_dollar_volume_usd'])})
    frames['universe']=pd.DataFrame(sorted(universe,key=lambda r:r['security_id']),columns=['security_id','issuer_id','ticker','cusip','security_class','risk_chain','median_dollar_volume_usd'])
    expected=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V1',scope=SCOPE,cutoff='2026-09-17',**frames,
        observed_provenance_and_missing=missing,observed_security_count=101,observed_issuer_count=100,
        conditional_security_count=9,conditional_issuer_count=9,candidate_cardinality_not_fixed=True,
        one_security_per_issuer_per_portfolio_required=True,historical_evaluation_505_rows_available=False,**dict.fromkeys(FALSE,False))
    checksum={}
    for key,item in expected.items():
        checksum[key]=dict(columns=list(item.columns),index=[str(x) for x in item.index],index_type=type(item.index).__name__,
            dtypes=[str(x) for x in item.dtypes],data=item.values.tolist()) if isinstance(item,pd.DataFrame) else item
    expected['panel_content_sha256']=digest(checksum)
    encoded={k:frame_payload(v) if isinstance(v,pd.DataFrame) else v for k,v in expected.items()}
    if not exact(value['panel'],encoded):raise ValueError('Saved typed values, index types, provenance or content checksum differ')
    if not exact(value['supplemental_dated_and_risk_provenance'],supplemental):raise ValueError('Distinct dates or full original fact metadata differ')
    fixed=dict(schema='SOURCE_BOUND_LATEST_NINE_CONDITIONAL_PANEL_V1',input_references={k:ref(k) for k in ANCHORS},
        subset_selection_basis='DATED_COORDINATE_AND_DECLARED_RISK_AND_LIQUIDITY_EVIDENCE_NOT_RETURN_RANKING',
        target_cardinality_fixed=False,source_bytes_bound=True,source_point_in_time_verified=False,
        legal_training_input_admitted=False,historical_six_input_training_ready=False,fit_performed=False,execution_authorized=False,winner_selected=False,promotion_allowed=False)
    if any(not exact(value.get(k),v) for k,v in fixed.items()) or set(value)!=set(fixed)|{'panel','supplemental_dated_and_risk_provenance','historical_expected_source_hashes','archive_resolution'}:
        raise ValueError('Outer scope or exact field contract differs')
    return dict(observed_rows=101,numeric_channels=96,conditional_securities=9,returns_cells=1134,nominal_close_cells=1143,
        volume_cells=567,dollar_volume_cells=567,all_four_numeric_frames_reconstructed=True,
        universe_and_all_101_gap_rows_reconstructed=True,rangeindex_and_panel_checksum_verified=True,
        distinct_dates_and_original_facts_verified=True)


def build(path,sha256):
    if OWNER_SHA is None:raise ValueError('Await externally frozen producer SHA')
    sources=dict(LOADED);sources[str(OWNER)]=OWNER_SHA
    value=saved.read(dict(path=str(Path(path).resolve()),sha256=sha256),sources)
    docs={key:saved.read(ref(key),sources) for key in ANCHORS}
    expected_sources=dict(value['historical_expected_source_hashes'])
    if expected_sources.get(str(OWNER))!=OWNER_SHA:raise ValueError('Saved producer source differs')
    for key in ANCHORS:
        if expected_sources.get(ref(key)['path'])!=ref(key)['sha256']:raise ValueError('Required hard source missing')
    required={str(ROOT/'backtest/ndx_latest_conditional_panel_research.py'):'0d5c031f855348577bf9ffd17acf68998c86c43a60a45a05e014dc1e1ac34b59'}
    for doc in docs.values():
        for field in ('source_hashes','historical_expected_source_hashes'):
            if field in doc:archive.merge(required,doc[field])
    if any(expected_sources.get(p)!=h for p,h in required.items()):raise ValueError('Inherited source closure omitted or re-signed')
    if archive.verify_expected_sources(expected_sources,archive.load_contract())!=value['archive_resolution']:raise ValueError('Original source archive partition differs')
    archive.merge(sources,expected_sources)
    folder=Path(ref('index')['path']).parent
    saved.validate_index(docs['index'],ANCHORS['plan'][1],folder,docs['plan']['tasks'])
    audit=docs['audit']
    if (audit['schema']!='LATEST_CONDITIONAL_CHANNELS_INDEPENDENT_AUDIT_V1' or audit['plan']!=ref('plan') or audit['index']!=ref('index')
        or type(audit['completed']) is not int or audit['completed']!=101 or audit['numerical_channels']!=96 or audit['blocked_history_or_price']!=5 or len(audit['details'])!=101):raise ValueError('Hard independent audit lineage differs')
    if any(audit[k] is not False for k in ('owner_numerical_kernel_called','security_identity_verified','complete_actions_verified','fit_performed','legal_training_input_admitted','point_in_time_verified','promotion_allowed')):raise ValueError('Independent audit authority differs')
    wrappers={}
    for entry,task,detail in zip(docs['index']['entries'],docs['plan']['tasks'],audit['details']):
        wrapped=saved.read(dict(path=entry['path'],sha256=entry['sha256']),sources)
        saved.validate_wrapper(wrapped,task,ANCHORS['plan'][1])
        marker=saved.read(dict(path=str(folder/(task['ticker']+'.started.json')),sha256=entry['started_sha256']),sources)
        if not exact(marker,dict(schema='LATEST_CHANNEL_ATTEMPT_V1',plan_sha256=ANCHORS['plan'][1],task=task,attempt_count=1)):
            raise ValueError('Task exclusive marker differs')
        if detail['ticker']!=task['ticker'] or detail['status']!=wrapped['status'] or detail['reason']!=task['reason']:
            raise ValueError('Per-task independent audit relation differs')
        if task['mode']=='BLOCKED':
            if detail['audit'] is not None:raise ValueError('Blocked task has numerical audit')
        else:
            result=wrapped['result'];a=detail['audit']
            if a['ticker']!=task['ticker'] or a['price_count']!=127 or a['return_count']!=126 or a['liquidity_status']!=result['liquidity']['status']:raise ValueError('Individual numerical audit differs')
        wrappers[task['ticker']]=wrapped
    ftnt=next(r for r in docs['seven']['rows'] if r['ticker']=='FTNT');cover=Path(ftnt['evidence']['cover_path']).resolve()
    if str(cover) not in sources or archive.drift.file_sha(cover)!=sources[str(cover)]:raise ValueError('FTNT cover source differs')
    raw=cover.read_bytes();raw=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    soup=BeautifulSoup(raw,'html.parser')
    periods=[dict(context=n.get('contextref'),original_text=n.get_text(' ',strip=True)) for n in soup.find_all() if n.get('name','').lower()=='dei:documentperiodenddate']
    details=inspect(value,docs,wrappers,{'FTNT':periods})
    partition=archive.verify_expected_sources(sources,archive.load_contract())
    return dict(schema='LATEST_CONDITIONAL_PANEL_INDEPENDENT_READBACK_V1',panel_reference=dict(path=str(Path(path).resolve()),sha256=sha256),
        details=details,historical_expected_source_hashes=sources,archive_resolution=partition,
        saved_channel_oracle_reference=ref('audit'),raw_oracle_repeated=False,producer_assemble_called=False,
        fitter_called=False,point_in_time_verified=False,legal_training_input_admitted=False,promotion_allowed=False)


def publish_verified(path,value):
    if value.get('schema')!='LATEST_CONDITIONAL_PANEL_INDEPENDENT_READBACK_V1' or any(value.get(k) is not False for k in ('raw_oracle_repeated','producer_assemble_called','fitter_called','point_in_time_verified','legal_training_input_admitted','promotion_allowed')):
        raise ValueError('Independent report scope differs')
    required=dict(LOADED)
    required[str(OWNER)]=OWNER_SHA
    required.update({ref(k)['path']:ref(k)['sha256'] for k in ANCHORS})
    required[value['panel_reference']['path']]=value['panel_reference']['sha256']
    if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in required.items()):raise ValueError('Publication required source missing or changed')
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source drift')
    result=saved.recipe.exclusive_publish(path,value)
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source drift after publication')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--panel',required=True);parser.add_argument('--panel-sha256',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(publish_verified(args.output,build(args.panel,args.panel_sha256))))
