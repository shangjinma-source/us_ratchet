"""Independent V2 envelope/source reconstruction and new-account Decimal audit only."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_historical_cross_k_accounts_independent_audit_20260923 as independent

SOURCE=Path(__file__).resolve()
BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'historical_cross_k_candidate_accounts_delta_20260923_v2'
SEED=dict(path=str(BASE/'historical_cross_k_candidate_accounts_20260923_v1/completed_121_incremental_independent_audit.json'),
          sha256='e209229ccca4cd8e55f02ba02fee4fa69d13a9c98c4e9964cc0c5ec31cd96296')
FIT=dict(path=str(BASE/'historical_fourteen_cross_k_20260923_v1/completed_5001_independent_audit.json'),
         sha256='41f9be6511c1f21ddc8267f92f25db0a5c051620b48847c18bb97ca9aeb0fbfa')
PRODUCER=dict(path=str(ROOT/'scripts/ndx_historical_cross_k_candidate_accounts_delta_20260923.py'),
              sha256='e4f0a45476bcd83da95d9fe9ac820d73e37cd8d9051c9f3e42ca465b87875995')
SEED_READER=dict(path=str(ROOT/'scripts/ndx_historical_cross_k_accounts_incremental_audit_20260923.py'),
                sha256='5c7ffe3cec84838af2c8b3cd83bda9396871abdc8a09817b9aed6532691f2b7e')
READER_SHA='52bf9f7934605d9768bb71e0de18080bd9edcbff225f61f333f366f52e64a39d'
INDEX=dict(path=str(OUTPUT/'index_9460b37dd3661d221800626befaa51766adfcd8f5c70dc63b6c91175db98e617.json'),
           sha256='c6b160835faab4888c2b289875c1a18e41f1e839843394c980823c4754b8f85f')
LOADED=dict(independent.LOADED)
independent.archive.merge(LOADED,{str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest()})


def require(condition,message):
    if not condition:raise ValueError(message)


def validate_authority(seed,index,fit,fit_index):
    require(seed['schema']=='HISTORICAL_CROSS_K_ACCOUNT_PREFIX_INCREMENTAL_INDEPENDENT_AUDIT_V1'
        and type(seed['completed_account_task_count']) is int and seed['completed_account_task_count']==121
        and len(seed['details'])==121 and seed['reused_independent_account_count']==111
        and seed['newly_independently_audited_account_count']==10 and seed['raw_marker_result_chain_verified'] is True,
        'Hard independently reviewed 121-account seed required')
    require(index['completed_account_task_count']==121 and len(index['entries'])==121
        and index['finalized_after_full_source_verification'] is True,'Finalized seed account denominator differs')
    require(fit['schema']=='HISTORICAL_CROSS_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1'
        and fit['completed_new_count']==5001 and len(fit['details'])==5001
        and fit['complete_marker_raw_checkpoint_chain_verified'] is True
        and fit_index['completed_new_count']==5001 and len(fit_index['entries'])==5001
        and fit_index['finalized_after_full_source_verification'] is True,'Hard reviewed 5001-fit authority required')
    require(all(document['plan_reference']==independent.PLAN for document in (seed,index,fit,fit_index)), 'Historical plan differs')
    require(seed['fit_prefix_audit_reference']==index['fit_prefix_audit_reference']==FIT,'Fit authority differs')
    identifiers=[row['task_id'] for row in fit['details']]
    require(len(set(identifiers))==5001 and identifiers==[row['task_id'] for row in fit_index['entries']]
        and identifiers[:121]==[row['task_id'] for row in index['entries']]==[row['task_id'] for row in seed['details']],
        'Ordered seed/fit task linkage differs')
    for entry,detail in zip(index['entries'],seed['details'],strict=True):
        require(all(entry[key]==detail[key] for key in ('raw_reference','result_reference')),'Sealed old artifact reference differs')


def unwrap(document,kind,ordinal):
    expected=dict(schema='HISTORICAL_CROSS_K_DELTA_'+kind+'_V2',producer_reference=PRODUCER,
        seed_account_audit_reference=SEED,global_task_ordinal_zero_based=ordinal,
        reused_payload_schema_is_not_producer_identity=True,
        payload_sha256=independent.digest(document['payload']),payload=document['payload'])
    require(type(document.get('global_task_ordinal_zero_based')) is int and independent.exact(document,expected),
        'Exact V2 producer/seed/ordinal/payload envelope required')
    return document['payload']


def entry_sources(entry,ordinal,row,folder):
    require(set(entry)=={'task_id','global_task_ordinal_zero_based','started_reference','raw_reference','result_reference'}
        and type(entry['global_task_ordinal_zero_based']) is int and entry['global_task_ordinal_zero_based']==ordinal
        and entry['task_id']==row['task_id'],'Exact new ordered delta entry required')
    sources={}
    for key,name in (('started_reference','started.json'),('raw_reference','raw.json'),('result_reference','result.json')):
        reference=entry[key]
        if key=='raw_reference' and reference is None:continue
        require(type(reference) is dict and set(reference)=={'path','sha256'}
            and reference['path']==str(folder/row['task_id']/name),'Exact V2 artifact path required')
        independent.archive.merge(sources,{reference['path']:reference['sha256']})
    return sources


def expected_index(index,auth_sources,seed,queue,details):
    sources=dict(auth_sources)
    entries=index['entries'];count=len(entries)
    require(1<=count<=10,'Bounded nonempty delta prefix required')
    for ordinal,(entry,row) in enumerate(zip(entries,queue[121:121+count],strict=True),121):
        independent.archive.merge(sources,entry_sources(entry,ordinal,row,OUTPUT))
    executed=sum(row['status']!='SKIPPED_RISK' for row in details)
    expected=dict(schema='HISTORICAL_CROSS_K_FINALIZED_DELTA_INDEX_V2',producer_reference=PRODUCER,
        seed_account_audit_reference=SEED,seed_index_reference=seed['index_reference'],fit_prefix_audit_reference=FIT,
        plan_reference=independent.PLAN,folder=str(OUTPUT),seed_account_count=121,newly_completed_account_count=count,
        combined_account_count=121+count,new_execution_count=executed,new_skipped_risk_count=count-executed,
        real_execution_performed=executed>0,audited_fit_task_count=5001,pending_account_count=5001-121-count,
        entries=entries,old_accounts_copied=False,old_account_numerical_audit_repeated=False,
        old_fit_numerical_audit_repeated=False,independent_delta_audit_completed=False,
        finalized_after_full_source_verification=True,historical_expected_source_hashes=sources,
        archive_resolution=index['archive_resolution'],fit_performed=False,control_executed=False,promotion_allowed=False,
        point_in_time_verified=False,formal_dual_benchmark_admission=False)
    require(independent.exact(index,expected),'Exact finalized V2 index/closure/count/scope required')
    return sources


def build(index_path,index_sha256):
    reference=dict(path=str(Path(index_path).resolve()),sha256=index_sha256)
    require(reference==INDEX,'Hard externally completed first V2 delta index required')
    require(LOADED[str(Path(independent.__file__).resolve())]==READER_SHA,'Frozen independent inspector source differs')
    archive=independent.archive
    # This mirrors source declarations only, not producer execution or old
    # numerical verification. No delta producer module is imported.
    auth_sources=independent.runner_loaded_sources()
    archive.merge(auth_sources,{PRODUCER['path']:PRODUCER['sha256'],SEED_READER['path']:SEED_READER['sha256']})
    seed=independent.read(SEED,auth_sources)
    seed_index=independent.read(seed['index_reference'],auth_sources)
    fit=independent.read(FIT,auth_sources)
    fit_index=independent.read(fit['index_reference'],auth_sources)
    validate_authority(seed,seed_index,fit,fit_index)
    for document in (seed,fit):archive.merge(auth_sources,document['historical_expected_source_hashes'])
    inputs=independent.read(independent.INPUT,auth_sources)
    plan=independent.read(independent.PLAN,auth_sources)
    first_marker=independent.read(seed_index['entries'][0]['started_reference'],auth_sources)
    require(first_marker['runtime']==independent.prefix.runtime(),'Sealed account runtime differs')
    contract=archive.load_contract()
    archive.verify_expected_sources(auth_sources,contract)
    for document in (seed,seed_index,fit,fit_index):
        require(independent.exact(document['archive_resolution'],independent.prefix.partition_subset(
            document['historical_expected_source_hashes'],contract)),'Authority source partition differs')
    sources=dict(LOADED);archive.merge(sources,auth_sources)
    index=independent.read(reference,sources)
    require(Path(reference['path']).parent==OUTPUT and Path(reference['path']).name=='index_'+independent.digest(index)+'.json',
        'Exact digest-addressed new namespace required')
    entries=index['entries'];count=len(entries)
    require(1<=count<=10,'Only bounded new delta may be independently audited')
    tasks={row['task_id']:dict(row['task'],task_id=row['task_id']) for row in plan['tasks']}
    queue=[dict(task_id=entry['task_id'],fit_checkpoint_reference=entry['result_reference'],detail=detail)
           for entry,detail in zip(fit_index['entries'],fit['details'],strict=True)]
    require({path.name for path in OUTPUT.iterdir()}=={entry['task_id'] for entry in entries}|{Path(reference['path']).name},
        'Unindexed delta artifacts prohibit successful prefix audit')
    comparison=independent.read(independent.COMPARISON,sources)
    control=independent.read(independent.CONTROL,sources)
    require(comparison['account_references']['incumbent']==independent.CONTROL
        and comparison['account_references']['candidate']==independent.EXTERNAL,'Shared control comparison differs')
    nav=comparison['nav_reference'];nav_bytes=Path(nav['path']).read_bytes()
    require(hashlib.sha256(nav_bytes).hexdigest()==nav['sha256'],'Shared NAV bytes differ')
    archive.merge(sources,{nav['path']:nav['sha256']})
    details=[]
    for ordinal,(entry,row) in enumerate(zip(entries,queue[121:121+count],strict=True),121):
        required=entry_sources(entry,ordinal,row,OUTPUT)
        archive.merge(sources,required)
        directory=OUTPUT/row['task_id']
        names={'started.json','result.json'}|({'raw.json'} if entry['raw_reference'] else set())
        require({path.name for path in directory.iterdir()}==names,'Orphan or failed delta task cannot pass')
        documents={}
        for kind,envelope_kind in (('started','ATTEMPT'),('raw','RAW_ACCOUNT'),('result','ACCOUNT_RESULT')):
            ref=entry[kind+'_reference']
            documents[kind]=None if ref is None else unwrap(independent.read(ref,sources),envelope_kind,ordinal)
        saved=documents['result']
        require(saved['fit_prefix_audit_reference']==FIT and saved['fit_checkpoint_reference']==row['fit_checkpoint_reference'],
            'New task completed fit authority differs')
        checkpoint=independent.read(row['fit_checkpoint_reference'],sources)
        require(independent.exact(checkpoint['task'],tasks[row['task_id']]) and checkpoint['fit_performed'] is True,
            'Historical fit/task declaration differs')
        require(row['task_id']!=independent.prefix.plan_reader.target_reader.JOB,'External account may not execute again')
        plain={key:value for key,value in entry.items() if key!='global_task_ordinal_zero_based'}
        detail=independent.inspect_entry(plain,documents,tasks[row['task_id']],checkpoint['result'],row['detail'],FIT,
            auth_sources,inputs,plan['numerical_source_hashes'],control['execution'],nav_bytes.decode('utf-8-sig'))
        details.append(dict(detail,global_task_ordinal_zero_based=ordinal))
    required=expected_index(index,auth_sources,seed,queue,details)
    require(independent.exact(index['archive_resolution'],archive.verify_expected_sources(required,contract)),
        'V2 index source partition differs')
    archive.merge(sources,required)
    return dict(schema='HISTORICAL_CROSS_K_V2_DELTA_INDEPENDENT_AUDIT_V1',index_reference=reference,
        seed_audit_reference=SEED,fit_prefix_audit_reference=FIT,producer_reference=PRODUCER,plan_reference=independent.PLAN,
        reused_independent_account_count=121,newly_independently_audited_account_count=count,
        combined_account_count=121+count,audited_fit_task_count=5001,details=details,
        old_account_numerical_audit_repeated=False,old_fit_numerical_audit_repeated=False,
        producer_called=False,runner_called=False,engine_called=False,raw_marker_result_chain_verified=True,
        write_order_independently_attested=False,automatic_next_seed_authorization=False,
        independent_delta_audit_completed=True,formal_dual_benchmark_admission=False,
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,contract),
        **dict.fromkeys(independent.FALSE,False))


def build_and_publish(path,index_path,index_sha256):
    require(OUTPUT not in Path(path).resolve().parents,'Publish audit outside immutable raw delta namespace')
    value=build(index_path,index_sha256)
    archive=independent.archive;contract=archive.load_contract()
    require(independent.exact(value['archive_resolution'],archive.verify_expected_sources(value['historical_expected_source_hashes'],contract)),
        'Sources changed before publication')
    reference=independent.publish(path,value)
    require(independent.exact(value,independent.read(reference,{})),'Published independent audit bytes differ')
    require(independent.exact(value['archive_resolution'],archive.verify_expected_sources(value['historical_expected_source_hashes'],contract)),
        'Sources changed after publication')
    return reference


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',required=True);parser.add_argument('--index-sha256',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(json.dumps(build_and_publish(args.output,args.index,args.index_sha256)))
