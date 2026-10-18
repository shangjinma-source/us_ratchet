"""Twelve dated security coordinates with an explicit new conditional window."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive

BASE=ROOT/'data/cache/research'
SOURCE=Path(__file__).resolve()
OUTPUT=BASE/'legacy_twelve_conditional_identity_20260923_v1'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
    (SOURCE,archive.SOURCE,Path(archive.drift.__file__).resolve())}
BOUND={
    'return_identity':('return_eight_conditional_identity_20260923_v1/identities.json','5f5bcbad2f5a3a340e0b3449b4b78ed55a44941d6402a4ee067dd779a4abaa6e'),
    'enph':('drawdown_four_input_assembly_20260923_v1/assembly.json','cb2ab027a2506a43d97e7c65494d524b1c7d7e890e7b9a2f67f863768c61aa67'),
    'facts':('legacy_five_dated_facts_20260923_v1/facts.json','418222e674eeb719b414ba9e22821c84c8dcd12f507cc4a36214b63637811336'),
    'prices':('legacy_twelve_price_only_20260923_v1/prices.json','a50c4fd387f10262527e82ad0edd2bae7b799b67e2d08cff2e4a47030a64b342'),
    'lane':('cutoff_training_lanes_20260923_v2/prepare.json','b7eaff190f3b2225db87d14fd0f7afc0cd9420536e9a4661f986f8ac319a96ba'),
}
COORDINATES={
    'ADBE':('0000796343','00724F101'),'ADI':('0000006281','032654105'),
    'AVGO':('0001730168','11135F101'),'BKR':('0001701605','05722G100'),
    'DDOG':('0001561550','23804L103'),'ENPH':('0001463101','29355A107'),
    'FTNT':('0001262039','34959E109'),'GOOG':('0001652044','02079K107'),
    'GOOGL':('0001652044','02079K305'),'QCOM':('0000804328','747525103'),
    'TEAM':('0001650372','049468101'),'TXN':('0000097476','882508104'),
}
NEW={'ADI','QCOM','DDOG','TEAM','TXN'}
CLOCK=[('2023-03-31','2023-04-03'),('2023-04-28','2023-05-01'),('2023-05-31','2023-06-01'),
    ('2023-06-30','2023-07-03'),('2023-07-31','2023-08-01'),('2023-08-31','2023-09-01')]
WINDOW=dict(start='2023-03-31',end='2023-09-01')
ASSUMPTION='NEW_EXPLICIT_107_DAY_STABILITY_ASSUMPTION_USING_DATED_FACTS_NOT_INTERVAL_CERTIFICATION'
FALSE=('new_http_performed','source_facts_reparsed','fit_performed','execution_performed','order_generation_allowed',
    'continuous_identity_interval_verified','provider_price_binding_verified','provider_binding_verified',
    'early_evidence_availability_inferred','historical_membership_verified','point_in_time_verified','promotion_allowed',
    'target_schedule_validity_verified','execution_risk_chain_union_verified','historical_full_source_closure_verified')


def require(value,message):
    if not value:raise ValueError(message)


def reference(role):
    path,sha=BOUND[role]
    require(type(sha) is str and len(sha)==64 and set(sha)<=set('0123456789abcdef'),'Reviewed hard evidence SHA required')
    return dict(path=str(BASE/path),sha256=sha)


def unique(pairs):
    value={}
    for key,item in pairs:
        require(key not in value,'Duplicate JSON field');value[key]=item
    return value


def assemble(documents):
    parent,enph,facts,prices,lane=(documents[k] for k in ('return_identity','enph','facts','prices','lane'))
    require(parent['schema']=='RETURN_EIGHT_CONDITIONAL_IDENTITY_ASSEMBLY_V1' and
        enph['schema']=='DRAWDOWN_FOUR_SECURITY_107_SESSION_CONDITIONAL_INPUT_V1' and
        facts['schema']=='LEGACY_FIVE_DATED_WEB_FACTS_V1' and
        prices['schema']=='LEGACY_TWELVE_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1' and
        lane['schema']=='CUTOFF_TRAINING_LANE_DEPENDENCY_PREPARE_V1','Exact sealed input schemas required')
    require(all(doc['point_in_time_verified'] is False and doc['promotion_allowed'] is False for doc in (parent,enph,facts,prices)) and
        lane['member_point_in_time_verified'] is False and lane['promotion_allowed'] is False,
        'Parent scope cannot be upgraded')
    require(parent['continuous_identity_interval_verified'] is False and parent['provider_price_binding_verified'] is False and
        parent['conditional_window']==WINDOW and enph['continuous_identity_interval_verified'] is False,
        'Preserve parent conditional identity boundaries')
    enph_identity=enph['identity_projection']
    require(enph_identity['enph_original_conditional_window']==dict(start='2023-03-31',end='2023-05-01') and
        enph_identity['enph_original_interval_certification_extended'] is False and enph_identity['conditional_window']==WINDOW,
        'ENPH original 21-day boundary cannot be extended as certification')
    fact_flags=('full_tool_response_preserved','local_full_http_body_available','local_http_original_bytes_available',
        'historical_identity_interval_verified','provider_binding_verified','point_in_time_verified','promotion_allowed',
        'trading_allowed','order_submission_allowed')
    require(all(facts[k] is False for k in fact_flags) and len(facts['rows'])==facts['security_count']==5 and
        {r['ticker'] for r in facts['rows']}==NEW,'Exact five bounded factual observations required')
    rows=[]
    for ticker,(cik,cusip) in sorted(COORDINATES.items()):
        role='facts' if ticker in NEW else 'enph' if ticker=='ENPH' else 'return_identity'
        original_rows=facts['rows'] if role=='facts' else enph_identity['rows'] if role=='enph' else parent['rows']
        found=[r for r in original_rows if r['ticker']==ticker]
        require(len(found)==1,'Unique dated ticker observation required')
        original=deepcopy(found[0]);sid=f'security:{cik}:{cusip}'
        require((original['subject_cik'],original['cusip'])==(cik,cusip),'Dated subject CIK/CUSIP differs')
        if role=='facts':
            require(all(original[k] is False for k in fact_flags) and original['continuous_identity_interval'] is None,
                'Factual evidence may not imply an interval')
            cover=original['local_cover_context']
            require(cover['subject_cik']==cik and cover['ticker']==ticker and cover['cusip_directly_verified_from_cover'] is False,
                'Separate local cover is identity context, not direct CUSIP evidence')
            title=cover['security_class']
            if ticker in ('DDOG','TEAM'):
                require(original['subject_cik_directly_in_cusip_document'] is False and
                    original['subject_cik_evidence']=='SEPARATE_LOCAL_COVER_NAME_CLASS_CONTEXT_NOT_IN_13F_TABLE' and
                    original['reporter_cik']=='0001357550' and original['subject_cik']!=original['reporter_cik'] and
                    original['old_issuer_or_class_conversion_verified'] is False and 'Class A' in title,
                    '13F reporter is not the subject issuer; Class A is not a conversion proof')
            if ticker=='TEAM':
                require(cover['issuer_name'].upper()=='ATLASSIAN CORPORATION' and original['cusip']=='049468101',
                    'TEAM Corporation/Class A may not be replaced with old issuer or class')
            if ticker=='TXN':
                require(original['filing_date']=='2022-02-10' and original['event_date']=='2021-12-31' and
                    original['accession']=='0001104659-22-018703','TXN older dated evidence cannot become a 2023 fact')
        else:
            require(original['security_id']==sid and original['issuer_id']==f'issuer:{cik}' and
                all(original[k] is False for k in ('continuous_interval_verified','provider_binding_verified','point_in_time_verified')),
                'Inherited dated SID or scope differs')
            title=original['security_class']
        require(type(title) is str and ('Class C' in title if ticker=='GOOG' else 'Class A' in title if ticker in ('GOOGL','BKR','DDOG','TEAM')
            else 'common' in title.lower()),'Dated share class differs')
        rows.append(dict(ticker=ticker,subject_cik=cik,cusip=cusip,security_id=sid,issuer_id=f'issuer:{cik}',security_class=title,
            evidence=dict(source_role=role,parent_reference=reference(role),dated_evidence=original,
                original_conditional_window=deepcopy(enph_identity['enph_original_conditional_window']) if ticker=='ENPH' else
                    deepcopy(parent['conditional_window']) if role=='return_identity' else None),
            continuous_interval_verified=False,provider_binding_verified=False,point_in_time_verified=False))
    by_sid={r['security_id']:r for r in rows};calendar=prices['calendar']
    require(len(rows)==len(by_sid)==12 and len({r['issuer_id'] for r in rows})==11,'Twelve SID and eleven issuer denominator required')
    require(len(calendar)==107 and calendar==sorted(set(calendar)) and calendar[0]==WINDOW['start'] and calendar[-1]==WINDOW['end'] and
        calendar==enph['calendar'] and prices['session_count']==107 and prices['ticker_count']==12 and
        prices['price_cell_count']==2568 and prices['tickers']==sorted(COORDINATES),'Hard price calendar/ticker denominator differs')
    require([(d['cutoff'],d['execution_date']) for d in lane['decisions']]==CLOCK,'Exact six lane clocks required')
    union=set();choices=[]
    for decision in lane['decisions']:
        candidates=decision['lanes']['LEGACY_TARGET_DISTANCE'];require(len(candidates)==1,'Unique saved LEGACY choice required')
        chosen=candidates[0];selected=chosen['selected'];day=decision['cutoff'];execution=decision['execution_date']
        require(day in calendar and calendar.index(day)+1<len(calendar) and calendar[calendar.index(day)+1]==execution,
            'Next observed execution session required')
        require(set(selected)<=set(by_sid) and len({r['issuer_id'] for r in selected.values()})==len(selected) and
            len(selected)==chosen['holding_count'],'Each decision needs unique issuers and exact selected cardinality')
        for sid,row in selected.items():
            require(all(row[k]==by_sid[sid][k] for k in ('ticker','issuer_id')),'Lane selected identity differs from dated evidence')
        union.update(selected);choices.append(dict(decision_date=day,execution_date=execution,saved_candidate=deepcopy(chosen)))
    require(union==set(by_sid),'Exact complete six-choice SID union required')
    return dict(schema='LEGACY_TWELVE_CONDITIONAL_IDENTITY_ASSEMBLY_V1',rows=rows,security_count=12,distinct_issuer_count=11,
        calendar=deepcopy(calendar),observed_decision_clock=[list(x) for x in CLOCK],saved_lane_choices=choices,
        selected_risk_chains_by_decision={row['decision_date']:{sid:label['risk_chain'] for sid,label in row['saved_candidate']['selected'].items()}
            for row in choices},
        conditional_window=deepcopy(WINDOW),interval_stability_assumption=ASSUMPTION,
        enph_original_conditional_window=deepcopy(enph_identity['enph_original_conditional_window']),
        enph_original_interval_certification_extended=False,
        goog_googl_relationship='DIFFERENT_SECURITY_IDS_SAME_ISSUER_NOT_A_RENAME',
        team_old_issuer_or_class_conversion_verified=False,dated_fact_availability_backdated=False,
        reuse_basis='HARD_PINNED_DATED_FACTS_WITH_NEW_EXPLICIT_WINDOW_ASSUMPTION',**dict.fromkeys(FALSE,False))


def build():
    references={role:reference(role) for role in BOUND}
    archive.strict(LOADED);sources=dict(LOADED);documents={}
    for role,ref in references.items():
        raw=Path(ref['path']).read_bytes();require(hashlib.sha256(raw).hexdigest()==ref['sha256'],'Hard evidence bytes differ')
        archive.merge(sources,{ref['path']:ref['sha256']});documents[role]=json.loads(raw,object_pairs_hook=unique)
        for key in ('source_hashes','historical_expected_source_hashes','prepare_source_hashes'):
            if key in documents[role]:archive.merge(sources,documents[role][key])
    contract=archive.load_contract();resolution=archive.verify_expected_sources(sources,contract)
    value=assemble(documents)
    archive.strict(LOADED);require(archive.verify_expected_sources(sources,contract)==resolution,'Sources changed during assembly')
    return dict(value,parent_references=references,historical_expected_source_hashes=sources,archive_resolution=resolution)


def publish():
    require(not OUTPUT.exists(),'Fresh fixed identity namespace required')
    value=build();contract=archive.load_contract()
    def guard():
        archive.strict(LOADED)
        require(archive.verify_expected_sources(value['historical_expected_source_hashes'],contract)==value['archive_resolution'],'Publication source drift')
    guard();OUTPUT.mkdir(parents=True,exist_ok=False);path=OUTPUT/'identities.json'
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    guard();require(path.read_bytes()==raw and {p.name for p in OUTPUT.iterdir()}=={'identities.json'},'Published bytes or directory differ')
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required')
    print(json.dumps(publish()))
