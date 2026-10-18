"""Read-only source phase for a new H failed-export recovery, never old-run retry.

Actual anchors deliberately pending. No SDK, producer, engine or economic code is
called. The publisher owns create-only attempt evidence and output publication.
"""
import hashlib
import json
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
STORAGE = Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
PARENT = STORAGE / 'dated_workbook_extension_20261003_v1'
DATA = STORAGE / 'dated_workbook_extension_data_20261003_v1'
LOADED = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
DATA_FALSE = ('source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','account_executed','fit_performed','economic_metrics_recomputed','risk_reaggregated','workbook_delivered','charts_rendered','visual_acceptance_passed','xlsx_actual_size_limit_verified','full_transitive_source_closure_reverified')
CHART_FALSE = ('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','fit_performed','account_executed','independent_export_readback_passed','visual_acceptance_passed','workbook_delivered')
BOUND = {
    'failure': {'path': str(PARENT/'failure.json'), 'sha256': '0da4c63b4b79286c140289d63ea24fb69bc743f910b6bb6e6bf2d05b5340aa5e'},
    'started': {'path': str(PARENT/'started.json'), 'sha256': 'd4347fe8722f620689a77d20716cfb2f9e64f9a0e3dddbf4713e7d44489bb6d5'},
    'index': {'path': str(DATA/'index.json'), 'sha256': '879402d5041928e36096ed24d09404bd9a4fecbdc76428225beaa01529117603'},
    'publication': {'path': str(DATA/'publication.json'), 'sha256': '5ec8da155e9bb40f44aa3a50cf3305a72fb7f6b670660b91f4f72b86e8c96521'},
    'audit': {'path': str(STORAGE/'dated_workbook_extension_data_independent_readback_20261003_v1/independent_readback.json'), 'sha256': 'ef6adcb90ed6650d54d54965ff2540dfb392a34bc5c4f9982752bd88e602c1ce'},
    'tasks': {'path': str(DATA/'tasks.jsonl'), 'sha256': '6ce82b33ba276ee52e5526503d2faed1f1637ab3d91bce10afd4400df7e8f72a'},
    'shared': {'path': str(DATA/'shared_display.json'), 'sha256': '77396263d69c988d73269adc18d5dca226385b5997735879e42518a1e73bb536'},
    'classification': {'path': str(DATA/'classification.json'), 'sha256': '976b46dab1fb2f44305156562454876cb1fab1001b6f3ab29361b719cb8e99b5'},
}
CODE = {
    'publisher': ('scripts/ndx_dated_workbook_extension_publish_20261003.mjs', 'f3375accf43c4f765b83b6e708e3986262e5a249107724d115adfbbdf651a771'),
    'plan': ('backtest/ndx_h_failed_export_recovery_plan_research.py', '6f94e2ba3d5d3fbe72b845084410d3eaaba9767178e5537c690ffb1d9859eef4'),
    'machine': ('backtest/ndx_h_saved_machine_recovery_research.py', 'a470d579ba2e3dbf440e017fb6821b3cde2eede73afb95deb5edb19bd1da2a05'),
    'wire': ('scripts/ndx_native_navigation_utf8_transport_20261003.py', 'c74d2cca0d7e09bbab925886b096a467512abad950a26f3b54677c4207206661'),
    'preservation': ('scripts/ndx_dated_singleton_overlay_publish_20261003.mjs', '139ed56bc5874f4d6be6ff483025a29d9808e96dc6e052e7a8f92f89e6d8f7e8'),
    'repair': ('scripts/ndx_dated_singleton_path_label_repair_20261003.mjs', 'f5ef70fbc034a17a1254723b07b4cf21278d1ee11967a6a1c11489bb008fdc00'),
    'data_producer': ('scripts/ndx_dated_workbook_extension_data_20261003.py', 'c07e34d389b8d4990df31db8e70a9a70c87e2856d9abf2b5a017f64b777c8577'),
    'data_reader': ('scripts/ndx_dated_workbook_extension_data_independent_readback_20261003.py', '53357679a47679a98012cf06a58823594a9826c04f9e4ce7cf80ed1aa6d630c6'),
    'core': ('scripts/ndx_dated_workbook_extension_20261003.mjs', 'b2770383e837c136755bad29caaea8cc5b817f5b4678617a5a2ceb23d513263a'),
    'path_component': ('scripts/ndx_dated_path_chart_component_20261003.mjs', '39fcd13d7588b4c1527bcd4dbf79bf5ec626da157d337f77323910231dc8023a'),
    'risk_component': ('scripts/ndx_dated_risk_chart_component_20261003.mjs', '9a4112a2abaaaee7c5bb4bd6c0c632519f06cbe92a1c0314135d1efa194179d5'),
    'navigation_component': ('scripts/ndx_dated_extension_navigation_component_20261003.mjs', '65e0f0760d0730b65e177e8e884eeb82c21f1ebe3747a364879cc868cdbe75b6'),
    'native_helper': ('scripts/ndx_workbook_native_hyperlinks_20261003.py', '267333bd62a3399c6ab3c97104bf884a737e116a51e8c62243aa3e0fcd6a475d'),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def preflight():
    refs = {**BOUND, **{k: {'path': str(ROOT/p), 'sha256': h} for k,(p,h) in CODE.items()}}
    for r in refs.values():
        require(type(r) is dict and set(r) == {'path','sha256'} and Path(r['path']).is_absolute(), 'Exact absolute source reference')
        require(type(r['sha256']) is str and re.fullmatch('[0-9a-f]{64}', r['sha256']), 'Pending immutable source anchor')
    return refs


def physical(path):
    path = Path(path)
    for item in [path, *path.parents]:
        info = item.lstat()
        require(not item.is_symlink() and not (getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT), 'Reparse source refused')
    return path


def digest_file(path):
    h = hashlib.sha256(); count = 0
    with physical(path).open('rb') as f:
        while chunk := f.read(1024*1024):
            h.update(chunk); count += len(chunk)
    return h.hexdigest(), count


def names(root):
    result=[]
    for p in sorted(physical(root).rglob('*')):
        physical(p)
        if p.is_file(): result.append(p.relative_to(root).as_posix())
        else: require(p.is_dir(), 'Regular file or directory only')
    require(len({n.casefold() for n in result}) == len(result), 'Unique casefold physical inventory')
    return result


def read(ref):
    data = physical(ref['path']).read_bytes()
    require(hashlib.sha256(data).hexdigest() == ref['sha256'], 'Same bytes source hash')
    return data


def document(ref):
    return json.loads(read(ref).decode('utf-8'))


def private_core(ref):
    b=read(ref); namespace={'__name__':'_authenticated_recovery_core'}
    exec(compile(b, ref['path'], 'exec'), namespace)
    return namespace


def guard(context):
    require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==LOADED, 'Loaded recovery source changed')
    require(names(PARENT) == context['parent_file_names'], 'Failed parent inventory changed')
    for row in context['parent_inventory']:
        require(digest_file(PARENT/row['path']) == (row['sha256'],row['byte_count']), 'Failed parent bytes changed')
    for p,h in context['source_hashes'].items():
        require(digest_file(p)[0] == h, 'Source drift')
    for directory,expected in context['source_inventories'].items():
        require(names(Path(directory))==expected,'Original data namespace changed')


def validate_documents(d, refs):
    index,p,a=d['index'],d['publication'],d['audit']
    require(index['schema']=='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1','B6 schema')
    require(p['schema']=='DATED_WORKBOOK_EXTENSION_DATA_PUBLICATION_V1' and p['status']=='PUBLISHED_DISPLAY_DATA_NOT_WORKBOOK_DELIVERY','B6 publication')
    require(a['schema']=='DATED_WORKBOOK_EXTENSION_DATA_INDEPENDENT_READBACK_V1' and a['status']=='PASS','B7 schema/status')
    require(p['index_reference']==refs['index']==a['index_reference'] and a['publication_reference']==refs['publication'],'B6 B7 role links')
    require(a['reader_sha256']==refs['data_reader']['sha256'] and a['producer_called'] is False and a['pure_projection_called'] is False,'Independent reader binding')
    for obj in (index,p,a):
        require(all(obj[k] is False for k in DATA_FALSE),'Data authority False')
    require(p['source_hashes']==index['source_hashes'],'Publication source closure')
    for field in ('planned_task_count','projected_task_count','not_supplied_task_count'):
        require(type(index[field]) is int and index[field]>=0,'Exact data counts')
    require(index['planned_task_count']==1632==index['projected_task_count']+index['not_supplied_task_count'],'Full data partition')
    for key,expected in (('planned_tasks',1632),('projected_tasks',index['projected_task_count']),('missing_tasks',index['not_supplied_task_count'])):
        require(type(a['detail'][key]) is int and a['detail'][key]==expected,'Independent full counts')
    require(type(a['classification_rows_verified']) is int and a['classification_rows_verified']==101,'Classification count')
    require(type(index['full_new_cutoff_task_denominator']) in (int,str) and str(index['full_new_cutoff_task_denominator'])=='6222659648236112670','Original full domain')
    require(index['delivery_status']=='DISPLAY_DATA_ONLY_NOT_H_WORKBOOK_DELIVERY','Data only scope')
    for key,role in (('task_jsonl_reference','tasks'),('shared_display_reference','shared'),('classification_reference','classification')):
        require(p[key]==index[key] and all(index[key][k]==refs[role][k] for k in ('path','sha256')),'Data child role')
        require(a['source_hashes'][refs[role]['path']]==refs[role]['sha256'],'Independent child source')
    require(a['verified_jsonl_sha256']==refs['tasks']['sha256'] and type(a['verified_jsonl_bytes']) is int and a['verified_jsonl_bytes']==index['task_jsonl_reference']['byte_count'],'Verified full bytes')
    require(type(index['task_jsonl_reference']['record_count']) is int and index['task_jsonl_reference']['record_count']==1632,'Full source row count')
    require(index['source_hashes'][refs['data_producer']['path']]==refs['data_producer']['sha256'],'Data producer source')
    for role in ('index','publication','data_producer','data_reader'):
        require(a['source_hashes'][refs[role]['path']]==refs[role]['sha256'],'Independent fixed source')
    require(d['shared']['schema']=='DATED_WORKBOOK_EXTENSION_SHARED_DATA_V1' and d['classification']['schema']=='DATED_WORKBOOK_CLASSIFICATION_TABLE_V1' and len(d['classification']['rows'])==101,'Shared/classification schemas')


def load_sources():
    refs = preflight()  # all pending anchors rejected before filesystem IO
    require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==LOADED, 'Loaded recovery source changed')
    sources = {str(Path(__file__).resolve()): LOADED}
    for r in refs.values():
        require(digest_file(r['path'])[0] == r['sha256'], 'Bound source bytes')
        sources[r['path']] = r['sha256']
    d = {k:document(refs[k]) for k in ('failure','started','index','publication','audit','shared','classification')}
    validate_documents(d,refs)
    source_inventories={str(Path(refs['index']['path']).parent):sorted(['started.json','tasks.jsonl','shared_display.json','classification.json','index.json','publication.json']),str(Path(refs['audit']['path']).parent):['independent_readback.json']}
    for directory,expected_names in source_inventories.items():
        require(names(Path(directory))==expected_names,'Exact original source namespace')
    original_roles = ('index','publication','audit','tasks','shared','classification','data_producer','data_reader','core','path_component','risk_component','navigation_component','native_helper')
    require(d['started']['input_references'] == {k:refs[k] for k in original_roles}, 'Original publisher exact fixed roles')
    expected = {refs[k]['path']:refs[k]['sha256'] for k in (*original_roles,'publisher')}
    for obj in (d['index'],d['audit']):
        for p,h in obj['source_hashes'].items():
            require(p not in expected or expected[p] == h, 'Original source claim conflict')
            require(type(h) is str and re.fullmatch('[0-9a-f]{64}',h), 'Original source claim hash')
            expected[p]=h
    require(d['started']['source_hashes'] == expected, 'Exact original source closure')
    for p,h in expected.items():
        if p not in sources:
            require(digest_file(p)[0] == h, 'Original declared source bytes')
        sources[p]=h
    inventory=[]; filenames=names(PARENT); chart_identities={}
    shard_names=[n for n in filenames if re.fullmatch(r'machine/tasks-\d{5}\.jsonl',n)]
    # Machine core owns the single initial read of every shard. Other originals
    # including the full tasks copy are hashed independently once here.
    for name in filenames:
        if name in shard_names: continue
        if re.fullmatch(r'attempts/attempt-\d{5}/chart_source_index.json',name):
            p=physical(PARENT/name)
            require(p.stat().st_size<=128*1024*1024,'Bounded single chart metadata; no truncation')
            raw=p.read_bytes();h,size=hashlib.sha256(raw).hexdigest(),len(raw)
            chart=json.loads(raw.decode('utf-8'))
            fields=('schema','attempt_index','start_task_ordinal','stop_task_ordinal','task_ids','source_jsonl_records',*CHART_FALSE)
            chart_identities[name]={k:chart[k] for k in fields}
            del raw,chart
        else:
            h,size=digest_file(PARENT/name)
        inventory.append({'path':name,'sha256':h,'byte_count':size})
    byname={r['path']:r for r in inventory}
    def local(name):
        return {'path':str(PARENT/name),'sha256':byname[name]['sha256']}
    for role in ('index','publication','audit','shared','classification'):
        require(byname[f'sources/{role}.json']['sha256'] == refs[role]['sha256'], 'Original source copy exact')
    for name,role in (('tasks.jsonl','tasks'),('shared_display.json','shared'),('classification.json','classification')):
        require(byname[name]['sha256'] == refs[role]['sha256'], 'Original complete data copy exact')
    attempts=[]
    for name in filenames:
        if re.fullmatch(r'attempts/attempt-\d{5}/pending.json',name):
            start=name.replace('/pending.json','/started.json')
            attempts.append({'pending':document(local(name)),'pending_reference':local(name),'started':document(local(start)),'started_reference':local(start)})
    for entry in attempts:
        p=entry['pending'];name=f"attempts/attempt-{p['attempt_index']:05d}/chart_source_index.json";chart=chart_identities[name]
        require(chart['schema']=='DATED_H_PACKAGE_CHART_SOURCE_INDEX_V1','Original chart schema')
        require(all(chart[k] is False for k in CHART_FALSE),'Original chart authority False')
        for key in ('attempt_index','start_task_ordinal','stop_task_ordinal'):
            require(type(chart[key]) is int and type(p[key]) is int and chart[key]==p[key],'Chart draft coordinates')
        require(chart['task_ids']==p['task_ids'],'Chart task identity')
        expected_records=[dict(numerical_task_id=r['numerical_task_id'],task_ordinal=r['task_ordinal'],source_record=r['jsonl_record']) for r in d['index']['task_index'][p['start_task_ordinal']:p['stop_task_ordinal']]]
        require(json.dumps(chart['source_jsonl_records'],sort_keys=True)==json.dumps(expected_records,sort_keys=True),'Chart original source row locations')
    machine_core=private_core(refs['machine'])
    task_metadata=[]
    def chunks(name):
        with physical(PARENT/name).open('rb') as f:
            while b:=f.readline(32*1024*1024+1):
                require(len(b)<=32*1024*1024 and b.endswith(b'\n'), 'Bounded full original line')
                row=json.loads(b.decode('utf-8')); ordinal=len(task_metadata)
                require(ordinal<1632 and type(row['task_ordinal']) is int and row['task_ordinal']==ordinal and row['numerical_task_id']==d['index']['task_index'][ordinal]['numerical_task_id'], 'Original compact row identity')
                missing=row['schema']=='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1'
                statuses=['COMPARISON_NOT_SUPPLIED']*2 if missing else [row['series'][r]['status'] for r in ('candidate_integer','candidate_continuous')]
                require(all(type(s) is str and s for s in statuses), 'Original saved series statuses')
                comparison='COMPARISON_NOT_SUPPLIED' if missing else 'DISPLAY_PROJECTED'
                require(d['index']['task_index'][ordinal]['status']==comparison, 'Compact/index status')
                task_metadata.append(dict(task_ordinal=ordinal,numerical_task_id=row['numerical_task_id'],comparison_status=comparison,integer_status=statuses[0],continuous_status=statuses[1]))
                del row
                yield b
    machine=machine_core['inspect_machine_stream'](index=d['index'],shards=({'filename':n,'chunks':chunks(n)} for n in shard_names),expected_tasks_reference=refs['tasks'])
    for entry in attempts:
        p=entry['pending']; selected=task_metadata[p['start_task_ordinal']:p['stop_task_ordinal']]
        require(all((r['comparison_status']=='COMPARISON_NOT_SUPPLIED') is p['costs']['missing'] for r in selected), 'Pending missing classification equals original rows')
    # Exact machine result field integration is checked by the source-phase tests.
    for row in machine['shards']:
        inventory.append({'path':row['filename'],'sha256':row['sha256'],'byte_count':row['byte_count']})
    inventory.sort(key=lambda r:r['path'])
    plan=private_core(refs['plan'])['plan_failed_export_recovery'](parent_root=str(PARENT),parent_inventory=inventory,
        failure=d['failure'],failure_reference=refs['failure'],started=d['started'],started_reference=refs['started'],
        index=d['index'],index_reference=local('sources/index.json'),attempts=attempts)
    require(names(PARENT) == filenames, 'Source read inventory drift')
    result={'schema':'DATED_H_FAILED_RECOVERY_SOURCE_CONTEXT_V1','input_references':refs,
            'source_hashes':sources,'parent_inventory':inventory,'parent_file_names':filenames,
            'plan':plan,'machine':machine,'task_metadata':task_metadata,'attempts':attempts,'documents':d,
            'source_inventories':source_inventories,
            'parent_status':'FAILED_DO_NOT_CONSUME','recovery_dispatch_authorized':False}
    guard(result)
    return result


if __name__=='__main__':
    require(sys.argv[1:] == ['--read-only-prepare'], 'Explicit source preparation only')
    sys.stdout.buffer.write(json.dumps(load_sources(),ensure_ascii=False,allow_nan=False).encode('utf-8'))
