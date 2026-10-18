"""Independent saved 14-channel readback; never import the panel producer or fitter."""
import argparse
import copy
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_latest_panel_independent_readback_20260919 as prior
archive=prior.archive
BASE=prior.BASE
PANEL=dict(path=str(BASE/'latest_fourteen_conditional_panel_20260919_v1/panel.json'),sha256='63638aab89a75147f8d9a0eb827173a221aa81f0df7f47967f3e5a5f2fd76b61')
OLD=dict(path=str(BASE/'latest_conditional_panel_20260919_v1/panel.json'),sha256='06f917bcdf67a92bc0135ce7c1a5ac28e5ad8bac15823ed85968bfe744811ec0')
AUDIT=dict(path=str(BASE/'latest_conditional_panel_20260919_v1/independent_readback.json'),sha256='fe2742de54d20602045a55a80b196c0961b40af846993c7a471c66b318373a2e')
FIVE=dict(path=str(BASE/'five_additional_conditional_identities_20260919_v1/identities.json'),sha256='aa8a2e5a68b538de97f22ed9ab849cac840043c1c5f9ec0c333786110d1d52d4')
OWNER=ROOT/'scripts/ndx_latest_fourteen_conditional_panel_20260919.py'
OWNER_SHA='b231418888fc8b7588b3565a8498574dadbb3410d68d7a46827fe312b9d6d384'
ADDED={'FAST','ODFL','DXCM','AMZN','LRCX'}
FALSE=('raw_oracle_repeated','producer_assemble_called','fitter_called','point_in_time_verified','legal_training_input_admitted','promotion_allowed')
DETAILS=dict(observed_rows=101,numeric_channels=96,conditional_securities=14,added_securities=5,
    returns_cells=1764,nominal_close_cells=1778,volume_cells=882,dollar_volume_cells=882,
    old9_all_frames_provenance_and_supplemental_exact=True,new5_numeric_frames_coordinates_and_risks_reconstructed=True,
    all_101_gap_rows_reconstructed=True,rangeindex_and_panel_checksum_verified=True,distinct_dates_and_original_facts_verified=True)
LOADED=dict(prior.LOADED)
LOADED[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def read(reference,sources):return prior.saved.read(reference,sources)
def exact(a,b):return prior.exact(a,b)


def decode(frame):
    if frame['type']!='dataframe':raise ValueError('Dataframe payload required')
    if frame['index_kind']=='DatetimeIndex':index=pd.DatetimeIndex(frame['index'])
    elif frame['index_kind']=='RangeIndex':
        if frame['index']!=list(range(len(frame['data']))) or any(type(v) is not int for v in frame['index']):raise ValueError('Exact RangeIndex required')
        index=pd.RangeIndex(len(frame['data']))
    else:raise ValueError('Known exact index kind required')
    value=pd.DataFrame(frame['data'],index=index,columns=frame['columns'])
    for column,dtype in zip(frame['columns'],frame['dtypes']):value[column]=value[column].astype(dtype)
    if not exact(prior.frame_payload(value),frame):raise ValueError('Typed payload loses data on restoration')
    return value


def inspect(value,old,facts,proposals,wrappers):
    """Independent reconstruction from externally bound documents, with no I/O."""
    expected=copy.deepcopy(old['panel']);supplemental=copy.deepcopy(old['supplemental_dated_and_risk_provenance'])
    frames={name:decode(expected[name]) for name in prior.FRAMES}
    calendar=[d.date().isoformat() for d in frames['nominal_close'].index]
    if len(calendar)!=127 or calendar[-1]!='2026-09-17' or len(set(calendar))!=127:raise ValueError('Hard 127-session calendar required')
    if len(facts['rows'])!=5 or {r['ticker'] for r in facts['rows']}!=ADDED:raise ValueError('Exact five facts required')
    allrows=expected['observed_provenance_and_missing'];by_ticker={r['ticker']:r for r in allrows}
    if len(allrows)!=101 or len(by_ticker)!=101:raise ValueError('Full observed cohort required')
    definitions={'returns':('price_returns','price_return',126,calendar[1:],'float64'),
        'nominal_close':('price_rows','nominal_close',127,calendar,'float64'),
        'raw_volume':('liquidity','raw_volume',63,calendar[-63:],'int64'),
        'dollar_volume':('liquidity','dollar_volume',63,calendar[-63:],'float64')}
    universe=frames['universe'].to_dict('records')
    for fact in facts['rows']:
        ticker=fact['ticker'];channel=wrappers[ticker]['result'];proposal,=[r for r in proposals['rows'] if r['ticker']==ticker]
        if fact['issuer_id']!=by_ticker[ticker]['observed_issuer_id'] or fact['conditional_research_security_id']!='security:'+fact['issuer_id'].split(':')[1]+':'+fact['cusip']:raise ValueError('Explicit same issuer/CUSIP coordinate required')
        if ticker=='LRCX' and (fact['minimum_conditional_date']!='2024-10-03' or fact['cusip']!='512807306' or fact['old_cusip_not_joined']!='512807108' or calendar[0]<'2024-10-03'):raise ValueError('LRCX post-action identity floor differs')
        if channel['liquidity']['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN' or channel['liquidity']['numerical_threshold_passed'] is not True:raise ValueError('Conditional liquidity eligibility differs')
        for name,(section,field,count,days,dtype) in definitions.items():
            rows=channel[section] if section!='liquidity' else channel['liquidity']['rows']
            if len(rows)!=count or [r['session'] for r in rows]!=days:raise ValueError('Complete source channel dates differ')
            if name=='returns' and [r['previous_session'] for r in rows]!=calendar[:-1]:raise ValueError('Source predecessor differs')
            numbers=[r[field] for r in rows]
            if name=='raw_volume':
                if any(type(v) is not int or v<0 for v in numbers):raise ValueError('Exact raw volume unit required')
            elif any(isinstance(v,bool) or not math.isfinite(float(v)) for v in numbers):raise ValueError('Finite channel values required')
            frames[name][ticker]=pd.Series(numbers,index=frames[name].index,dtype=dtype)
        period=fact['original_cover_fields']['dei:documentperiodenddate']
        day=datetime.strptime(' '.join(period['original_text'].split()).replace(' ,',','),'%B %d, %Y').date().isoformat()
        fields=dict(ticker=ticker,security_id=fact['conditional_research_security_id'],issuer_id=fact['issuer_id'],cusip=fact['cusip'],security_class=fact['security_class'])
        coordinate=dict(**fields,scope=prior.SCOPE,latest_interval_verified=False,provider_binding_verified=False,assumed_window=dict(first=calendar[0],last=calendar[-1]),dated_fact=dict(**fields,dated_as_of=day,source_references=[FIVE]))
        risk=dict(scope=prior.SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,historical_labels=[proposal['risk_chain_candidate']],risk_chain=proposal['risk_chain_candidate'],source_kind=proposal['risk_source_kind'],source_references=[prior.ref('fifteen')])
        row=by_ticker[ticker]
        if row['channel_audit_assertion']['channel_sha256']!=prior.digest(channel):raise ValueError('Saved channel audit digest differs')
        row.update(included_in_conditional_panel=True,blocking_reasons=[],coordinate_assumption=coordinate,risk_assumption=risk)
        universe.append(dict(**fields,risk_chain=risk['risk_chain'],median_dollar_volume_usd=float(channel['liquidity']['median_dollar_volume_usd'])))
        supplemental[ticker]=dict(date_role='SELECTED_DATED_FACT_ANCHOR_NOT_JOINT_AVAILABILITY',selected_dated_anchor=day,complete_original_fact=copy.deepcopy(fact),separately_observed_cover_period=copy.deepcopy(period),distinct_filing_period_event_receipt_dates_preserved=True,joint_historical_availability_inferred=False,original_risk_plan_row=copy.deepcopy(proposal),selected_anchor_kind='COVER_PERIOD_END_NOT_PUBLICATION_OR_JOINT_AVAILABILITY')
    columns=sorted(prior.TICKERS|ADDED)
    for name in definitions:frames[name]=frames[name][columns]
    frames['universe']=pd.DataFrame(sorted(universe,key=lambda r:r['security_id']),columns=frames['universe'].columns)
    if len({r['issuer_id'] for r in universe})!=14:raise ValueError('Unique conditional issuer denominator differs')
    expected.update(frames);expected.update(conditional_security_count=14,conditional_issuer_count=14)
    expected.pop('panel_content_sha256')
    checksum={k:dict(columns=list(v.columns),index=[str(x) for x in v.index],index_type=type(v.index).__name__,dtypes=[str(x) for x in v.dtypes],data=v.values.tolist()) if isinstance(v,pd.DataFrame) else v for k,v in expected.items()}
    expected['panel_content_sha256']=prior.digest(checksum)
    encoded={k:prior.frame_payload(v) if isinstance(v,pd.DataFrame) else v for k,v in expected.items()}
    fixed=dict(schema='SOURCE_BOUND_LATEST_FOURTEEN_CONDITIONAL_PANEL_V1',original_nine_reference=OLD,old9_audit_reference=AUDIT,five_identity_reference=FIVE,
        original_nine_numeric_cells_and_assumptions_exact=True,previous_fit_results_reused=False,subset_selection_basis='DATED_COORDINATE_AND_DECLARED_RISK_AND_LIQUIDITY_EVIDENCE_NOT_RETURN_RANKING',
        **dict.fromkeys(('target_cardinality_fixed','source_point_in_time_verified','legal_training_input_admitted','historical_six_input_training_ready','fit_performed','execution_authorized','winner_selected','promotion_allowed'),False))
    if set(value)!=set(fixed)|{'panel','supplemental_dated_and_risk_provenance','historical_expected_source_hashes','archive_resolution'} or any(not exact(value[k],v) for k,v in fixed.items()):raise ValueError('Outer exact scope differs')
    if not exact(value['panel'],encoded) or not exact(value['supplemental_dated_and_risk_provenance'],supplemental):raise ValueError('Independent fourteen reconstruction differs')
    return dict(DETAILS)


def build(path,sha256):
    reference=dict(path=str(Path(path).resolve()),sha256=sha256)
    if not exact(reference,PANEL):raise ValueError('Exact sealed fourteen panel required')
    sources=dict(LOADED);archive.merge(sources,{str(OWNER):OWNER_SHA})
    value=read(reference,sources);old=read(OLD,sources);audit=read(AUDIT,sources);facts=read(FIVE,sources)
    if audit['schema']!='LATEST_CONDITIONAL_PANEL_INDEPENDENT_READBACK_V1' or not exact(audit['panel_reference'],OLD) or any(audit[k] is not False for k in FALSE):raise ValueError('Hard old audit differs')
    for doc in (old,audit,facts):
        for field in ('historical_expected_source_hashes','source_hashes'):
            if field in doc:archive.merge(sources,doc[field])
    required=dict(sources)
    # The reviewed artifact cannot contain its own bytes digest; that external
    # reference remains mandatory in this reader's independently bound closure.
    excluded={str(Path(__file__).resolve()),reference['path']}
    if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in required.items() if p not in excluded):raise ValueError('Inherited source missing/re-signed')
    archive.merge(sources,value['historical_expected_source_hashes'])
    contract=archive.load_contract()
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],contract)!=value['archive_resolution']:raise ValueError('Saved archive partition differs')
    archive.verify_expected_sources(sources,contract)
    proposals=read(prior.ref('fifteen'),sources);plan=read(prior.ref('plan'),sources);index=read(prior.ref('index'),sources)
    prior.saved.validate_index(index,prior.ANCHORS['plan'][1],Path(prior.ref('index')['path']).parent,plan['tasks'])
    wrappers={}
    for entry,task in zip(index['entries'],plan['tasks']):
        if task['ticker'] not in ADDED:continue
        wrapped=read(dict(path=entry['path'],sha256=entry['sha256']),sources)
        prior.saved.validate_wrapper(wrapped,task,prior.ANCHORS['plan'][1]);wrappers[task['ticker']]=wrapped
    details=inspect(value,old,facts,proposals,wrappers)
    partition=archive.verify_expected_sources(sources,archive.load_contract())
    result=dict(schema='LATEST_FOURTEEN_CONDITIONAL_PANEL_INDEPENDENT_READBACK_V1',panel_reference=PANEL,old9_reference=OLD,old9_audit_reference=AUDIT,five_identity_reference=FIVE,
        details=details,historical_expected_source_hashes=sources,archive_resolution=partition,**dict.fromkeys(FALSE,False))
    validate_report(result);return result


def validate_report(value):
    fixed=dict(schema='LATEST_FOURTEEN_CONDITIONAL_PANEL_INDEPENDENT_READBACK_V1',panel_reference=PANEL,old9_reference=OLD,old9_audit_reference=AUDIT,five_identity_reference=FIVE,details=DETAILS,**dict.fromkeys(FALSE,False))
    if set(value)!=set(fixed)|{'historical_expected_source_hashes','archive_resolution'} or any(not exact(value[k],v) for k,v in fixed.items()):raise ValueError('Exact independent report contract differs')


def publish_verified(path,value):
    validate_report(value)
    # Rebuild the source-bound readback, not the producer panel or any fitted result.
    if not exact(value,build(PANEL['path'],PANEL['sha256'])):raise ValueError('Audit source/result omitted or altered')
    result=prior.saved.recipe.exclusive_publish(path,value)
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source drift after publication')
    validate_report(value);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--panel',required=True);parser.add_argument('--panel-sha256',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(publish_verified(args.output,build(args.panel,args.panel_sha256))))
