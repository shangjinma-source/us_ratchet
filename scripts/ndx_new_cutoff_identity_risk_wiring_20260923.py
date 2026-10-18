"""Reference-only dated coordinate/risk wiring. No price, identity certification or fit."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

SOURCE=Path(__file__).resolve();BASE=SOURCE.parents[1]/'data/cache/research'
OUTPUT=BASE/'new_cutoff_identity_risk_wiring_20260923_v1/wiring.json'
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BOUND={
 'panel':('latest_fourteen_conditional_panel_20260919_v1/panel.json','63638aab89a75147f8d9a0eb827173a221aa81f0df7f47967f3e5a5f2fd76b61'),
 'legacy':('legacy_twelve_conditional_identity_20260923_v1/identities.json','82ad1d271f3bd0fb3906647f808c0a9c9f81270ab7e29f7f6c626fbf8e9db8db'),
 'facts':('pcar_cprt_conditional_identity_20260923_v1/facts.json','e187cea1c8df1a8e87a156abbcebef402c23ea711d871e2387f17dac19b60402'),
 'observation':('current_quote_list_observation_20260923_v1/observation.json','a6d8899fb2bc22f755ecd721271ed173f24a0b959b6ff8da9c96985f940fa990'),
 'completeness':('new_cutoff_completeness_20260923_v1/manifest.json','d4b16c34ea81e6925dc8cb1d0f56cfdb80731aa7078c64bfd734b4fb375cfbd1'),
 'bridge':('new_cutoff_event_policy_20260923_v1/bridge.json','d2f7824197cb30c119eb8297d6dda784e33ff2589010e36f63d4e9850267d7bd'),
 'channels':('new_cutoff_conditional_channels_20260923_v1/channels.json','3d708df6b273616edd46e06d2e2976acbc0e9fd90cc1243679ff94ca8befa3ac'),
 'audit':('new_cutoff_conditional_channels_20260923_v1/independent_raw_decimal_audit.json','a11e7fb3b9006eba71b9d254557f713a32b2615407c9b8f77e7b24a8c01a2ace'),
}
PANEL_TICKERS={'ADI','AMAT','LRCX','CDNS','FAST','ODFL','AMZN','NFLX','DXCM','FTNT','PANW','GOOG','BKR','AVGO'}
EXTRA_TICKERS={'ADBE','DDOG','GOOGL','QCOM','TXN'}
OVERLAP={'ADI','AVGO','BKR','FTNT','GOOG'}
FALSE=('identity_interval_verified','provider_binding_verified','risk_interval_verified','point_in_time_verified',
 'historical_membership_verified','complete_corporate_actions_verified','legal_training_input_admitted','promotion_allowed',
 'fit_performed','execution_authorized','http_performed','prices_recomputed','old_build_called','original_windows_extended',
 'full_transitive_source_closure_reverified')
COMMON_GAPS=['NEW_WINDOW_SECURITY_CONTINUITY_UNVERIFIED','PROVIDER_CHANNEL_TO_SECURITY_BINDING_UNVERIFIED',
 'NEW_WINDOW_RISK_LABEL_VALIDITY_UNVERIFIED','POINT_IN_TIME_MEMBERSHIP_UNVERIFIED','COMPLETE_CORPORATE_ACTIONS_UNVERIFIED']


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


def ref(role,pointer=None):
    relative,digest=BOUND[role];result=dict(path=str(BASE/relative),sha256=digest)
    if pointer is not None:result['json_pointer']=pointer
    return result


def guard(sources):
    require(hashlib.sha256(SOURCE.read_bytes()).hexdigest()==LOADED_SHA,'Loaded source changed')
    for path,digest in sources.items():require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'Bound source changed')


def coordinate(row):
    fields=('security_id','issuer_id','ticker','cusip','security_class')
    value={key:row[key] for key in fields}
    require(all(type(v) is str and v and v==v.strip() for v in value.values()),'Explicit coordinate strings required')
    issuer=value['issuer_id'];require(issuer.startswith('issuer:') and len(issuer)==17 and issuer[7:].isdigit(),'Issuer coordinate differs')
    require(value['security_id']=='security:'+issuer[7:]+':'+value['cusip'],'SID/issuer/CUSIP mismatch')
    return value


def assemble(docs):
    panel=docs['panel'];legacy=docs['legacy'];facts=docs['facts'];observation=docs['observation']
    channels=docs['channels'];audit=docs['audit'];complete=docs['completeness'];bridge=docs['bridge']
    require(all(doc.get('promotion_allowed') is False for doc in docs.values()),'Source scope upgraded')
    members=observation['observed_symbols']
    require(len(members)==len(set(members))==101 and [row['symbol'] for row in observation['rows']]==members,'Exact observed101 required')
    require(not {'TEAM','ENPH','TSM','QQQ','SPY'}&set(members),'Nonmember cannot enter101')
    require(channels['schema']=='NEW_CUTOFF_CONDITIONAL_CHANNELS_V1' and audit['schema']=='NEW_CUTOFF_CHANNELS_INDEPENDENT_RAW_DECIMAL_AUDIT_V1' and
        audit['status']=='PASSED' and type(audit['completed']) is int and audit['completed']==101 and audit['candidate_reference']==ref('channels'),'Exact completed channel audit required')
    require(audit['raw_decimal_fraction_oracle_used'] is True,'Independent oracle required')
    for role in ('bridge','completeness'):
        require(channels['input_references'][role]==ref(role) and audit['input_references'][role]==ref(role),'Channel audit input differs')
    calendar=complete['observed_reference_calendar_127']
    require(len(calendar)==127 and calendar==sorted(set(calendar)) and calendar[0]=='2026-03-20' and calendar[-1]=='2026-09-21' and
        channels['calendar']==bridge['observed_reference_calendar_127']==calendar,'New observed window differs')
    require([row['ticker'] for row in complete['rows']]==members+['TSM','QQQ','SPY'],'104 completeness denominator differs')
    for rows in (channels['rows'],audit['details'],bridge['rows']):require([row['ticker'] for row in rows]==members,'Channel row order differs')
    table=panel['panel']['universe'];require(table['type']=='dataframe' and len(table['columns'])==len(set(table['columns'])),'Typed old universe required')
    require(all(len(row)==len(table['columns']) for row in table['data']),'Old universe width differs')
    universe=[dict(zip(table['columns'],row)) for row in table['data']]
    require(len(universe)==14 and {row['ticker'] for row in universe}==PANEL_TICKERS,'Hard old14 membership differs')
    original_rows=panel['panel']['observed_provenance_and_missing']
    require(len(original_rows)==len({row['ticker'] for row in original_rows})==101,'Old provenance denominator differs')
    provenance={row['ticker']:(index,row) for index,row in enumerate(original_rows)}
    candidates={}
    for row in universe:
        ticker=row['ticker'];coord=coordinate(row);index,original=provenance[ticker]
        require(original['included_in_conditional_panel'] is True,'Old candidate not included')
        oldcoord=original['coordinate_assumption'];risk=original['risk_assumption']
        require(coordinate(oldcoord)==coord and risk['risk_chain']==row['risk_chain'],'Panel coordinate/risk sources disagree')
        require(oldcoord['assumed_window']==dict(first='2026-03-18',last='2026-09-17') and
            oldcoord['latest_interval_verified'] is False and oldcoord['provider_binding_verified'] is False and risk['latest_interval_verified'] is False,'Old interval must remain unverified')
        candidates[ticker]=dict(coordinate=coord,risk_chain=row['risk_chain'],original_windows=[deepcopy(oldcoord['assumed_window'])],
            complete_original_evidence=[dict(source=ref('panel','/panel/observed_provenance_and_missing/'+str(index)),
                original_provenance_row=deepcopy(original),supplemental_provenance=deepcopy(panel['supplemental_dated_and_risk_provenance'][ticker]))],
            risk_sources=[dict(source=ref('panel','/panel/observed_provenance_and_missing/'+str(index)+'/risk_assumption'),original_risk_assumption=deepcopy(risk))])
    require(len(legacy['rows'])==12 and len({row['ticker'] for row in legacy['rows']})==12,'Legacy12 denominator differs')
    history={}
    for day,mapping in legacy['selected_risk_chains_by_decision'].items():
        for sid,label in mapping.items():
            require(type(label) is str and label,'Explicit saved risk label required')
            history.setdefault(sid,[]).append(dict(observation_date=day,risk_chain=label))
    overlap=set();added=set()
    for index,row in enumerate(legacy['rows']):
        ticker=row['ticker']
        if ticker not in members:continue
        coord=coordinate(row);risk_history=sorted(history.get(coord['security_id'],[]),key=lambda item:item['observation_date'])
        labels={item['risk_chain'] for item in risk_history};require(len(labels)==1,'Missing or conflicting legacy risk history')
        require(row['continuous_interval_verified'] is False and row['point_in_time_verified'] is False and row['provider_binding_verified'] is False,'Legacy scope upgraded')
        if ticker=='TXN':
            dated=row['evidence']['dated_evidence']
            require(dated['filing_date']=='2022-02-10' and dated['event_date']=='2021-12-31' and
                dated['accession']=='0001104659-22-018703','TXN dated fact must not be backdated or modernized')
        label=next(iter(labels));evidence=dict(source=ref('legacy','/rows/'+str(index)),complete_original_fact=deepcopy(row))
        risk=dict(source=ref('legacy','/selected_risk_chains_by_decision'),security_id=coord['security_id'],
            source_kind='SAVED_2023_LANE_RISK_OBSERVATIONS_NOT_NEW_ADJUDICATION',all_saved_observations=risk_history)
        if ticker in candidates:
            current=candidates[ticker];require(current['coordinate']==coord and current['risk_chain']==label,'Overlapping identity/class/risk conflict')
            overlap.add(ticker);current['complete_original_evidence'].append(evidence);current['risk_sources'].append(risk)
            current['original_windows'].append(deepcopy(legacy['conditional_window']))
        else:
            added.add(ticker);candidates[ticker]=dict(coordinate=coord,risk_chain=label,original_windows=[deepcopy(legacy['conditional_window'])],
                complete_original_evidence=[evidence],risk_sources=[risk])
    require(overlap==OVERLAP and added==EXTRA_TICKERS,'Five overlaps/new additions differ')
    require(len(candidates)==19 and len({row['coordinate']['security_id'] for row in candidates.values()})==19 and
        len({row['coordinate']['issuer_id'] for row in candidates.values()})==18,'19SID/18issuer denominator differs')
    require(candidates['GOOG']['coordinate']['security_id']=='security:0001652044:02079K107' and
        candidates['GOOGL']['coordinate']['security_id']=='security:0001652044:02079K305','GOOG/GOOGL separate classes required')
    lrcx=panel['supplemental_dated_and_risk_provenance']['LRCX']['complete_original_fact']
    require(candidates['LRCX']['coordinate']['cusip']=='512807306' and lrcx['old_cusip_not_joined']=='512807108' and
        lrcx['minimum_conditional_date']=='2024-10-03' and lrcx['old_security_continuity_inferred'] is False,'LRCX post-action boundary differs')
    require(facts['risk_chain_assigned'] is False and len(facts['rows'])==2 and {row['ticker'] for row in facts['rows']}=={'PCAR','CPRT'},'Two unassigned-risk facts required')
    extra={}
    for index,row in enumerate(facts['rows']):
        require(row['risk_chain'] is None and row['risk_chain_assigned'] is False and row['direct_single_document_cusip_cik_proof'] is False,'PCAR/CPRT risk or direct proof upgraded')
        coord=coordinate({**row,'security_id':row['conditional_research_security_id']})
        extra[row['ticker']]=dict(coordinate=coord,risk_chain=None,original_windows=[],risk_sources=[],
            complete_original_evidence=[dict(source=ref('facts','/rows/'+str(index)),complete_original_fact=deepcopy(row))])
    rows=[]
    for index,ticker in enumerate(members):
        channel=channels['rows'][index];detail=audit['details'][index]
        require(detail['status']==channel['status'] and detail['reasons']==channel['reasons'],'Channel independent detail differs')
        require(detail['promotion_allowed'] is False and detail['legal_training_input_admitted'] is False and detail['security_identity_verified'] is False,'Audit authority upgraded')
        if channel['status']=='CONDITIONAL_NUMERIC_RESULT':
            require(detail['decoded_sha256']==channel['raw_decoded_sha256'] and detail['price_count']==len(channel['quote_rows'])==127 and
                detail['return_count']==len(channel['channel_input']['price_returns'])==126 and
                detail['liquidity_status']==channel['channel_input']['liquidity']['status'],'Audited numerical row linkage differs')
        else:require(channel['status']=='BLOCKED_PRICE_INPUT' and channel['quote_rows'] is None and channel['channel_input'] is None,'Blocked channel must retain gap')
        source=candidates.get(ticker,extra.get(ticker));gaps=list(COMMON_GAPS)+list(channel['reasons'])
        if ticker in candidates:state='DATED_COORDINATE_AND_LEGACY_RISK_AVAILABLE_FOR_EXPLICIT_NEW_ASSUMPTION'
        elif ticker in extra:state='DATED_COORDINATE_RISK_UNASSIGNED';gaps.append('NO_BUSINESS_RISK_CLASSIFICATION_ADJUDICATED')
        else:state='NOT_ASSEMBLED_FROM_THIS_BOUNDED_SOURCE_SET';gaps.append('NO_DATED_COORDINATE_AND_RISK_ASSEMBLED_FROM_SELECTED_SOURCES')
        rows.append(dict(ticker=ticker,observed_row=deepcopy(observation['rows'][index]),identity_risk_state=state,
            coordinate=None if source is None else deepcopy(source['coordinate']),risk_chain=None if source is None else source['risk_chain'],
            original_windows=[] if source is None else deepcopy(source['original_windows']),
            complete_original_evidence=[] if source is None else deepcopy(source['complete_original_evidence']),
            risk_sources=[] if source is None else deepcopy(source['risk_sources']),
            new_assumed_window=dict(first=calendar[0],last=calendar[-1]),
            new_assumption='DATED_COORDINATE_CLASS_AND_SAVED_RISK_LABEL_PERSIST_ONLY_AS_CONDITIONAL_RESEARCH_ASSUMPTION' if ticker in candidates else None,
            channel_reference=ref('channels','/rows/'+str(index)),channel_audit_reference=ref('audit','/details/'+str(index)),
            channel_row_sha256=hashlib.sha256(encode(channel)).hexdigest(),new_channel_status=channel['status'],
            independent_channel_detail=deepcopy(detail),gaps=gaps,**dict.fromkeys(FALSE,False)))
    return dict(schema='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V1',scope='REFERENCE_ONLY_CONDITIONAL_RESEARCH_WIRING',
        observed_member_count=101,capture_queue_count=104,candidate_security_count=19,candidate_issuer_count=18,
        dated_coordinate_risk_unassigned_count=2,bounded_source_missing_count=80,one_security_per_issuer_per_portfolio_required=True,
        additional_roles=deepcopy(channels['additional_roles']),candidate_cutoff='2026-09-21',calendar=deepcopy(calendar),
        rows=rows,input_references={role:ref(role) for role in BOUND},old_panel_price_or_liquidity_values_reused=False,**dict.fromkeys(FALSE,False))


def build():
    sources={str(SOURCE):LOADED_SHA};docs={};guard(sources)
    for role in BOUND:
        reference=ref(role);raw=Path(reference['path']).read_bytes()
        require(hashlib.sha256(raw).hexdigest()==reference['sha256'],'Consumed source bytes differ')
        sources[reference['path']]=reference['sha256'];docs[role]=loads(raw)
    result=assemble(docs);result['source_hashes']=sources;guard(sources);return result


def publish():
    require(not OUTPUT.parent.exists(),'Fresh fixed wiring namespace required')
    value=build();guard(value['source_hashes']);raw=encode(value)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw,'Published bytes differ')
    require({path.name for path in OUTPUT.parent.iterdir()}=={'wiring.json'},'Unexpected namespace entry')
    return dict(path=str(OUTPUT),sha256=hashlib.sha256(raw).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required');print(json.dumps(publish()))
