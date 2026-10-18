"""Independent recovered H source/ZIP readback; no producer, SDK or economic call.

Future output anchors fail before IO. A failed original export remains failed.
Static saved bytes and graph checks do not authorize visual or Excel acceptance.
"""
import argparse,builtins,copy,hashlib,json,os,re,stat,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
STORAGE=Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
PARENT=STORAGE/'dated_workbook_extension_20261003_v1'
RECOVERY=STORAGE/'dated_h_failed_export_recovery_20261003_v1'
DATA=STORAGE/'dated_workbook_extension_data_20261003_v1'
OUTPUT=STORAGE/'dated_h_failed_export_recovery_independent_readback_20261003_v1'
BOUND={
 'manifest':(str(RECOVERY/'export_manifest.json'),'f4b5de32074a6af7206719d20095d8d5f4c07e5b5ef615132467fee024b1118f'),
 'recovery_publication':(str(RECOVERY/'publication.json'),'cbbcb63938dc10d46a63408fc01cca76f5ca6263d891a21db9e8e05c571be55d'),
 'recovery_publisher':(str(ROOT/'scripts/ndx_h_failed_export_recovery_publish_20261003.mjs'),'12edccf102bb1b7f19b063eefc9aa38c6a2bd3a5891c63ebc7e2af4c4aaf8524'),
 'source_phase':(str(ROOT/'scripts/ndx_h_failed_export_recovery_sources_20261003.py'),'96689f970ad1115047d1e0b6cde8e595c553e36dbd5a25de71b2508751057224'),
 'inspection':(str(ROOT/'backtest/ndx_h_failed_export_recovery_inspection_research.py'),'7e0adfcee03ab70c7c85ec83dc54f42041ddf9a4064842ef301f60e906be9f7a'),
 'zip_core':(str(ROOT/'backtest/ndx_h_workbook_export_inspection_research.py'),'2a7730f4cb813e5ecbc204f9850a5df21a9ff6fc18ac50667278704c4e8b85f4')}
INPUT_BOUND={
 'failure':(str(PARENT/'failure.json'),'0da4c63b4b79286c140289d63ea24fb69bc743f910b6bb6e6bf2d05b5340aa5e'),'started':(str(PARENT/'started.json'),'d4347fe8722f620689a77d20716cfb2f9e64f9a0e3dddbf4713e7d44489bb6d5'),
 'index':(str(DATA/'index.json'),'879402d5041928e36096ed24d09404bd9a4fecbdc76428225beaa01529117603'),'publication':(str(DATA/'publication.json'),'5ec8da155e9bb40f44aa3a50cf3305a72fb7f6b670660b91f4f72b86e8c96521'),
 'audit':(str(STORAGE/'dated_workbook_extension_data_independent_readback_20261003_v1/independent_readback.json'),'ef6adcb90ed6650d54d54965ff2540dfb392a34bc5c4f9982752bd88e602c1ce'),
 'tasks':(str(DATA/'tasks.jsonl'),'6ce82b33ba276ee52e5526503d2faed1f1637ab3d91bce10afd4400df7e8f72a'),'shared':(str(DATA/'shared_display.json'),'77396263d69c988d73269adc18d5dca226385b5997735879e42518a1e73bb536'),'classification':(str(DATA/'classification.json'),'976b46dab1fb2f44305156562454876cb1fab1001b6f3ab29361b719cb8e99b5')}
FLAGS=dict(formal_comparison_passed=False,point_in_time_verified=False,promotion_allowed=False,
 future_independent_oos=False,economics_recomputed=False,risk_recomputed=False,fit_performed=False,
 account_executed=False,visual_acceptance_passed=False,native_excel_open_verified=False,
 dynamic_formula_evaluation_verified=False,workbook_delivered=False,recovery_dispatch_authorized=False)
CODE={'publisher': ('scripts/ndx_dated_workbook_extension_publish_20261003.mjs', 'f3375accf43c4f765b83b6e708e3986262e5a249107724d115adfbbdf651a771'), 'plan': ('backtest/ndx_h_failed_export_recovery_plan_research.py', '6f94e2ba3d5d3fbe72b845084410d3eaaba9767178e5537c690ffb1d9859eef4'), 'machine': ('backtest/ndx_h_saved_machine_recovery_research.py', 'a470d579ba2e3dbf440e017fb6821b3cde2eede73afb95deb5edb19bd1da2a05'), 'wire': ('scripts/ndx_native_navigation_utf8_transport_20261003.py', 'c74d2cca0d7e09bbab925886b096a467512abad950a26f3b54677c4207206661'), 'preservation': ('scripts/ndx_dated_singleton_overlay_publish_20261003.mjs', '139ed56bc5874f4d6be6ff483025a29d9808e96dc6e052e7a8f92f89e6d8f7e8'), 'repair': ('scripts/ndx_dated_singleton_path_label_repair_20261003.mjs', 'f5ef70fbc034a17a1254723b07b4cf21278d1ee11967a6a1c11489bb008fdc00'), 'data_producer': ('scripts/ndx_dated_workbook_extension_data_20261003.py', 'c07e34d389b8d4990df31db8e70a9a70c87e2856d9abf2b5a017f64b777c8577'), 'data_reader': ('scripts/ndx_dated_workbook_extension_data_independent_readback_20261003.py', '53357679a47679a98012cf06a58823594a9826c04f9e4ce7cf80ed1aa6d630c6'), 'core': ('scripts/ndx_dated_workbook_extension_20261003.mjs', 'b2770383e837c136755bad29caaea8cc5b817f5b4678617a5a2ceb23d513263a'), 'path_component': ('scripts/ndx_dated_path_chart_component_20261003.mjs', '39fcd13d7588b4c1527bcd4dbf79bf5ec626da157d337f77323910231dc8023a'), 'risk_component': ('scripts/ndx_dated_risk_chart_component_20261003.mjs', '9a4112a2abaaaee7c5bb4bd6c0c632519f06cbe92a1c0314135d1efa194179d5'), 'navigation_component': ('scripts/ndx_dated_extension_navigation_component_20261003.mjs', '65e0f0760d0730b65e177e8e884eeb82c21f1ebe3747a364879cc868cdbe75b6'), 'native_helper': ('scripts/ndx_workbook_native_hyperlinks_20261003.py', '267333bd62a3399c6ab3c97104bf884a737e116a51e8c62243aa3e0fcd6a475d')}
INPUT_BOUND.update({k:(str(ROOT/p),h) for k,(p,h) in CODE.items()})

EXPORT_FALSE=('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','fit_performed','account_executed','independent_export_readback_passed','visual_acceptance_passed','workbook_delivered')

def require(ok,message):
    if not ok:raise ValueError(message)

def enc(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()

def sha(b):return hashlib.sha256(b).hexdigest()

def exact(a,b):require(enc(a)==enc(b),'Exact evidence mismatch')

def integer(v,n=None):require(type(v)is int and v>=0 and (n is None or v==n),'Exact integer count');return v

def reference(p,h):return dict(path=str(p),sha256=h)

def merge(s,r):valid(r);require(r['path']not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']

def loads(b):
    def pairs(rows):
        d={}
        for k,v in rows:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))

def false(v):
    for k in EXPORT_FALSE:require(v[k]is False,'Export authority '+k)

def save(p,v):
    b=enc(v)
    with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved bytes');return reference(p,sha(b))

DATA_FALSE=('source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','account_executed','fit_performed','economic_metrics_recomputed','risk_reaggregated','workbook_delivered','charts_rendered','visual_acceptance_passed','xlsx_actual_size_limit_verified','full_transitive_source_closure_reverified')

def validate_data_parents(index,pub,audit,inputs):
    require(index['schema']=='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1','Data index schema')
    require(pub['schema']=='DATED_WORKBOOK_EXTENSION_DATA_PUBLICATION_V1' and pub['status']=='PUBLISHED_DISPLAY_DATA_NOT_WORKBOOK_DELIVERY','Data publication status')
    require(audit['schema']=='DATED_WORKBOOK_EXTENSION_DATA_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Data audit status')
    for document in (index,pub,audit):
        for key in DATA_FALSE:require(document[key]is False,'Data authority '+key)
    exact(pub['index_reference'],inputs['index']);exact(audit['index_reference'],inputs['index']);exact(audit['publication_reference'],inputs['publication']);exact(audit['reader_sha256'],inputs['data_reader']['sha256']);exact(pub['source_hashes'],index['source_hashes'])
    integer(index['planned_task_count'],1632);present=integer(index['projected_task_count']);missing=integer(index['not_supplied_task_count']);integer(present+missing,1632)
    for key,value in [('planned_tasks',1632),('projected_tasks',present),('missing_tasks',missing),('output_rows',1632)]:integer(audit['detail'][key],value)
    integer(audit['classification_rows_verified'],101)
    for key,role in [('task_jsonl_reference','tasks'),('shared_display_reference','shared'),('classification_reference','classification')]:
        exact(pub[key],index[key]);exact(reference(index[key]['path'],index[key]['sha256']),inputs[role])
    integer(index['task_jsonl_reference']['record_count'],1632);integer(audit['verified_jsonl_bytes'],index['task_jsonl_reference']['byte_count']);exact(audit['verified_jsonl_sha256'],inputs['tasks']['sha256'])
    for role in ('index','publication','tasks','shared','classification','data_producer'):
        r=inputs[role];require(audit['source_hashes'].get(r['path'])==r['sha256'],'Audit fixed parent source '+role)
    r=inputs['data_producer'];require(index['source_hashes'].get(r['path'])==r['sha256'],'Data producer source')
    require(audit['producer_called']is False and audit['pure_projection_called']is False,'Independent saved audit scope')

def check_data_namespaces(inputs):
    parent=Path(inputs['index']['path']).parent
    require({p.name for p in parent.iterdir()}=={'started.json','tasks.jsonl','shared_display.json','classification.json','index.json','publication.json'},'Exact saved data namespace')
    audit_parent=Path(inputs['audit']['path']).parent
    require({p.name for p in audit_parent.iterdir()}=={'independent_readback.json'},'Exact saved data audit namespace')
    require(all(not p.is_symlink() and p.is_file() for folder in (parent,audit_parent) for p in folder.iterdir()),'Saved parent regular files')

def restore(row,shared):
    t=copy.deepcopy(row)
    if t['schema']=='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1':return t
    for role in ('incumbent_integer','incumbent_continuous','STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'):
        exact(sorted(t['series'][role]),['shared_series_id']);key=t['series'][role]['shared_series_id'];v=shared['series'][key]
        exact(v['identity'],dict(role=role,source_reference=t['source_index'][role]));exact(v['series']['source_reference'],v['identity']['source_reference']);t['series'][role]=copy.deepcopy(v['series'])
        if role.startswith('incumbent'):
            exact(t['risk_tracks'][role],dict(shared_risk_id=key));risk=shared['risk'][key];exact(risk['identity'],v['identity']);exact(risk['risk']['source_reference'],v['identity']['source_reference']);t['risk_tracks'][role]=copy.deepcopy(risk['risk'])
    return t

def cell_records(r):
    h=hashlib.sha256();count=size=0
    with Path(r['path']).open('rb')as f:
        for line in f:
            require(line.endswith(b'\n') and len(line)<=64*1024**2,'Bounded complete cell snapshot line');h.update(line);count+=1;size+=len(line);yield loads(line)
    exact(h.hexdigest(),r['sha256']);integer(r['record_count'],count);integer(r['byte_count'],size)

def inspect_navigation(core,wb,index,classification,packages,ids):
    links=core.expected_navigation_links(packages,ids);exact(wb['native_links'],links);require(not wb['charts'],'No invented navigation charts')
    core.inspect_classification_table(wb,classification);rows=[]
    for p in packages:
        for t in p['tasks']:
            entry=index['task_index'][t['task_ordinal']]
            rows.append([t['task_ordinal']+1,'ID: '+t['numerical_task_id'],entry['k'],entry['weight_spec'],entry['status'],t['integer_status'],t['continuous_status'],p['filename'],t['local_task_number'],'分类/来源与风险时点待认证；非独立OOS',entry['jsonl_record'],t['numerical_task_id']])
    core.source_table(wb,'全部任务',rows,(4,11));return links

def verify_chart_sidecars(chart,tasks):
    if tasks[0]['schema']=='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1':
        exact(chart['risk_source_index'],[]);exact(chart['task_evidence'],[]);exact(chart['engine_evidence'],[]);require(chart['task_selector']is None and chart['date_selector']is None,'Missing selectors absent');return
    exact(chart['task_selector'],'路径查看!B4');exact(chart['date_selector'],'风险查看!B4');integer(chart['default_local_task'],1);integer(chart['default_date_index'],1)
    expected=[]
    for ti,t in enumerate(tasks):
        order=[('candidate_target',None),('incumbent_target',None)]+[(role,day)for day in range(127)for role in ('candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous')if ti==0 or not role.startswith('incumbent')]
        for role,day in order:
            target=day is None;who=role.split('_')[0];holder=t['original_target_chain_evidence'][who]if target else t['risk_tracks'][role]
            expected.append(dict(source_id=len(expected),numerical_task_id=t['numerical_task_id'],role=role,session=None if target else t['calendar'][day],task_pointer='/original_target_chain_evidence/'+who if target else f'/risk_tracks/{role}/rows/{day}',task_pointer_scope='RESOLVED_DISPLAY_TASK_NOT_RAW_JSONL_POINTER',source_reference=holder['source_evidence']['source_reference']if target else holder.get('source_reference'),saved_missing_evidence=holder.get('missing_evidence')))
    exact(chart['risk_source_index'],expected)
    fields=['numerical_task_id','source_index','input_references','original_provenance_and_missing','preserved_evidence_sidecars']
    exact(chart['task_evidence'],[{k:t[k]for k in fields+(['source_jsonl_records']if 'source_jsonl_records'in t else [])}for t in tasks])
    exact(chart['engine_evidence'],[{k:t[k]for k in ('numerical_task_id','engine_normalization_evidence','original_target_evidence')}for t in tasks])

def valid(r):
 require(type(r)is dict and type(r.get('path'))is str and Path(r['path']).is_absolute() and r['path']==r['path'].strip(),'Absolute reference')
 require(type(r.get('sha256'))is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Pending immutable anchor');return r

def physical(p):
 p=Path(p)
 for q in (p,*p.parents):
  s=q.lstat();require(not q.is_symlink() and not(getattr(s,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT),'No reparse paths')
 return p

def hash_file(p):
 h=hashlib.sha256()
 with physical(p).open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()

def read_bytes(r):
 valid(r);b=physical(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed same bytes');return b

def read(r):return loads(read_bytes(r))

def guard(s):
 require(hash_file(SOURCE)==LOADED,'Loaded reader changed')
 for p,h in s.items():require(hash_file(p)==h,'Source drift '+p)

def relative(name):
 require(type(name)is str and name and '\\'not in name and ':'not in name and all(x and x not in ('.','..') and x==x.rstrip(' .')for x in name.split('/')),'Strict relative artifact path');return name

def names(root):
 physical(root);out=[]
 for p in root.rglob('*'):
  physical(p)
  if p.is_file():out.append(p.relative_to(root).as_posix())
  else:require(p.is_dir(),'Regular namespace')
 require(len(set(x.casefold()for x in out))==len(out),'Casefold unique files');return sorted(out)

def inventory_map(root,rows,extra=()):
 out={};rel=[]
 for row in rows:
  exact(sorted(row),['byte_count','path','sha256']);n=relative(row['path']);integer(row['byte_count']);p=physical(root/n)
  require(p.is_file()and p.stat().st_size==row['byte_count'],'Inventory actual size');merge(out,reference(p,row['sha256']));rel.append(n)
 require(len(rel)==len(set(n.casefold()for n in rel)),'Unique inventory')
 exact(names(root),sorted(rel+list(extra)));return out

def compile_inspectors(refs):
 z=types.ModuleType('_fixed_zip_inspection');exec(compile(read_bytes(refs['zip_core']),refs['zip_core']['path'],'exec'),z.__dict__)
 package=types.SimpleNamespace(ndx_h_workbook_export_inspection_research=z)
 def private_import(name,globals=None,locals=None,fromlist=(),level=0):
  if name=='backtest':
   exact(tuple(fromlist),('ndx_h_workbook_export_inspection_research',));require(level==0,'Absolute injected ZIP import');return package
  require(not name.startswith(('backtest','scripts')),'No business dependency execution')
  return builtins.__import__(name,globals,locals,fromlist,level)
 core=types.ModuleType('_fixed_recovery_inspection');core.__dict__['__builtins__']={**vars(builtins),'__import__':private_import}
 exec(compile(read_bytes(refs['inspection']),refs['inspection']['path'],'exec'),core.__dict__)
 require(core.zip_core is z,'Authenticated isolated ZIP module');return core,z

def validate_publication(m,p,refs,inputs,source_map):
 require(m['schema']=='DATED_H_FAILED_EXPORT_RECOVERY_V1'and m['status']=='RECOVERED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE','Recovery manifest')
 require(p['schema']=='DATED_H_FAILED_EXPORT_RECOVERY_PUBLICATION_V1'and p['status']=='PUBLISHED_RECOVERY_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE','Recovery publication')
 for doc in (m,p):
  false(doc)
  for k in ('source_bytes_authenticated','native_excel_open_verified'):require(doc[k]is False,'No delegated acceptance')
 exact(p['manifest_reference'],refs['manifest']);exact(m['source_hashes'],source_map);exact(p['source_hashes'],source_map);exact(m['input_references'],inputs)
 exact(m['parent_failure_reference'],inputs['failure']);exact(m['parent_started_reference'],inputs['started'])
 require(m['parent_status']=='FAILED_DO_NOT_CONSUME'and m['old_publication_existed']is False and m['recovery_is_new_attempt']is True,'Failed parent retained')
 for k,n in [('planned_task_count',1632),('packaged_task_count',1632),('unprocessed_task_count',0)]:integer(m[k],n)
 exact(m['output_inventory_excludes'],['export_manifest.json','publication.json'])

def reconstruct_packages(index,inventory,artifact):
 ids=[r['numerical_task_id']for r in index['task_index']];out=[];oversize=[]
 pending_names=sorted(n for n in inventory if re.fullmatch(r'attempts/attempt-\d{5}/pending.json',n))
 cursor=0
 for i,name in enumerate(pending_names):
  require(name==f'attempts/attempt-{i:05d}/pending.json','Contiguous original attempts')
  base=f'attempts/attempt-{i:05d}';p=artifact(name);start=artifact(base+'/started.json');false(p);false(start)
  require(p['schema']=='DATED_H_EXPORT_ATTEMPT_V1'and start['status']=='PENDING_EXPORT_ATTEMPT','Original pending roles')
  for k in ('attempt_index','start_task_ordinal','stop_task_ordinal'):integer(p[k]);exact(p[k],start[k])
  integer(p['attempt_index'],i);a=p['start_task_ordinal'];b=p['stop_task_ordinal'];require(0<=a<b<=1632,'Attempt bounds');exact(p['task_ids'],ids[a:b]);exact(start['task_ids'],ids[a:b])
  ar=p['reference'];exact(ar,reference(PARENT/(base+'/artifact.xlsx'),inventory[base+'/artifact.xlsx']['sha256']))
  integer(p['bytes'],inventory[base+'/artifact.xlsx']['byte_count']);exact(p['sha256'],ar['sha256'])
  costs=p['costs'];require(type(costs['missing'])is bool,'Typed missing');integer(costs['taskCount'],b-a);exact(costs['taskIds'],ids[a:b]);require(0<integer(costs['dataRows'])<=250000,'Data row cap')
  require(all((r['status']=='COMPARISON_NOT_SUPPLIED')is costs['missing']for r in index['task_index'][a:b]),'Original missing scope')
  for key,filename in [('expected_cells_reference','expected_cells.jsonl'),('chart_source_index_reference','chart_source_index.json')]:
   r=p[key];exact(r['path'],str(PARENT/base/filename));exact(r['sha256'],inventory[base+'/'+filename]['sha256'])
  views=[('任务索引','A1:C20')]if costs['missing']else[('路径查看','A1:G46'),('风险查看','A1:N43')]
  integer(len(p['previews']),len(views))
  for j,(v,(sheet,area))in enumerate(zip(p['previews'],views)):
   exact(v,dict(path=str(PARENT/base/f'preview-{j}.png'),sha256=inventory[base+f'/preview-{j}.png']['sha256'],worksheet=sheet,range=area))
  if p['status']=='OVERSIZE_ATTEMPT_NOT_ACCEPTED':require(p['bytes']>50*1024**2,'Actual oversize');oversize.append(name);continue
  require(p['status']=='PENDING_COMPLETE_STREAM_AND_SOURCE_PUBLICATION'and 0<p['bytes']<=50*1024**2 and a==cursor,'Original accepted partition')
  pi=len(out);filename=f'package-{pi+1:04d}.xlsx';exact(inventory[filename]['sha256'],ar['sha256']);integer(inventory[filename]['byte_count'],p['bytes'])
  out.append(dict(package_index=pi,filename=filename,start_task_ordinal=a,stop_task_ordinal=b,task_ids=ids[a:b],attempt_index=i,original_workbook_reference=reference(PARENT/filename,ar['sha256']),byte_count=p['bytes'],pending_reference=reference(PARENT/name,inventory[name]['sha256']),action='REBUILD_SINGLETON_WITH_REGISTERED_B5_ONLY_DELTA'if b-a==1 and not costs['missing']else'COPY_ORIGINAL_BYTES_NO_SDK_EXPORT'))
  cursor=b
 integer(cursor,1632);integer(len(out),277)
 exact(sorted(n for n in inventory if re.fullmatch(r'package-\d{4}.xlsx',n)),[p['filename']for p in out]);return out,oversize


def readback(*,execute=False):
 require(execute is True,'Explicit independent readback')
 refs={k:valid(reference(p,h))for k,(p,h)in BOUND.items()};inputs={k:valid(reference(p,h))for k,(p,h)in INPUT_BOUND.items()}
 require(not OUTPUT.exists(),'Create only no retry')
 sources={str(SOURCE):LOADED}
 for r in list(refs.values())+list(inputs.values()):merge(sources,r)
 # No raw/SDK/producer is executed. All fixed bytes are locked before private code.
 guard(sources);check_data_namespaces(inputs)
 d={k:read(inputs[k])for k in ('failure','started','index','publication','audit','shared','classification')}
 validate_data_parents(d['index'],d['publication'],d['audit'],inputs)
 original_roles=('index','publication','audit','tasks','shared','classification','data_producer','data_reader','core','path_component','risk_component','navigation_component','native_helper')
 exact(d['started']['input_references'],{k:inputs[k]for k in original_roles})
 old_sources={}
 for k in (*original_roles,'publisher'):merge(old_sources,inputs[k])
 for doc in (d['index'],d['audit']):
  for p,h in doc['source_hashes'].items():merge(old_sources,reference(p,h))
 exact(d['started']['source_hashes'],old_sources)
 expected=dict(old_sources)
 for r in inputs.values():merge(expected,r)
 for k in ('source_phase','recovery_publisher'):merge(expected,refs[k])
 for p,h in expected.items():merge(sources,reference(p,h))
 m=read(refs['manifest']);pub=read(refs['recovery_publication']);validate_publication(m,pub,refs,inputs,expected)
 newfiles=inventory_map(RECOVERY,m['output_inventory'],('export_manifest.json','publication.json'))
 def newref(r):
  valid(r);require(newfiles.get(str(Path(r['path'])))==r['sha256'],'New artifact inventory bound');return r
 def newdoc(r):return read(newref(r))
 for key,filename in [('parent_inventory_reference','parent_inventory.json'),('recovery_plan_reference','recovery_plan.json'),('machine_index_reference','machine_index.json')]:exact(m[key]['path'],str(RECOVERY/filename));newref(m[key])
 invdoc=newdoc(m['parent_inventory_reference']);exact(invdoc['parent_root'],str(PARENT));exact(invdoc['parent_failure_reference'],inputs['failure']);false(invdoc)
 oldfiles=inventory_map(PARENT,invdoc['files']);byname={r['path']:r for r in invdoc['files']}
 def oldref(name):return reference(PARENT/name,byname[name]['sha256'])
 def olddoc(name):return read(oldref(name))
 def artifact_ref(r):
  valid(r);require(({**oldfiles,**newfiles}).get(str(Path(r['path'])))==r['sha256'],'Artifact restricted to exact old/new inventory');return r
 def artifact(r):return read(artifact_ref(r))
 for k in ('index','publication','audit','shared','classification'):exact(oldref('sources/'+k+'.json')['sha256'],inputs[k]['sha256'])
 for name,role in [('tasks.jsonl','tasks'),('shared_display.json','shared'),('classification.json','classification')]:exact(oldref(name)['sha256'],inputs[role]['sha256'])
 guard(sources);guard(oldfiles);guard(newfiles)
 core,z=compile_inspectors(refs);parent_roles=dict(failure=inputs['failure'],started=inputs['started'],index_copy=oldref('sources/index.json'))
 parent_report=core.inspect_failed_parent(failure=d['failure'],started=d['started'],parent_inventory=invdoc['files'],parent_root=str(PARENT),parent_references=parent_roles,index=d['index'])
 originals,oversize=reconstruct_packages(d['index'],byname,olddoc)
 partition=core.inspect_package_partition(index=d['index'],parent_packages=originals,packages=m['packages'])
 plan=newdoc(m['recovery_plan_reference']);require(plan['schema']=='DATED_H_FAILED_EXPORT_RECOVERY_PLAN_V1' and plan['status']=='STRUCTURAL_PLAN_PENDING_INDEPENDENT_BYTES_AND_FULL_EOF_VALIDATION','Saved structural plan');false(plan);require(plan['old_publication_existed']is False and plan['recovery_is_new_attempt']is True,'New plan failed lineage');integer(plan['package_count'],277);integer(plan['planned_task_count'],1632);exact(plan['packages'],originals);exact(plan['parent_inventory_preserved'],invdoc['files']);exact(plan['parent_references'],parent_roles);exact(plan['navigation_links'],partition['native_links'])
 exact(plan['parent_status'],'FAILED_DO_NOT_CONSUME');integer(plan['singleton_rebuild_count'],partition['repaired_package_count'])
 exact(plan['machine_shards'],sorted(n for n in byname if re.fullmatch(r'machine/tasks-\d{5}\.jsonl',n)))
 exact(plan['preserved_oversize_attempts'],[dict(pending=olddoc(n),pending_reference=oldref(n),started=olddoc(n.replace('/pending.json','/started.json')),started_reference=oldref(n.replace('/pending.json','/started.json')))for n in oversize])
 for k in ('machine_eof_verified','source_bytes_authenticated','recovery_dispatch_authorized','chart_and_cell_data_verified','path_containment_physical_verified'):require(plan[k]is False,'Plan cannot certify completed bytes')
 started_ref=reference(RECOVERY/'started.json',newfiles[str(RECOVERY/'started.json')]);started=read(started_ref)
 require(started['schema']=='DATED_H_FAILED_EXPORT_RECOVERY_STARTED_V1'and started['parent_status']=='FAILED_DO_NOT_CONSUME','Recovery start role');false(started);exact(started['input_references'],inputs);exact(started['source_hashes'],expected)
 machine=newdoc(m['machine_index_reference']);require(machine['schema']=='DATED_H_RECOVERED_MACHINE_DATA_INDEX_V1'and machine['original_bytes_not_reencoded']is True,'Recovered machine role');false(machine)
 for key,name in [('full_tasks_reference','tasks.jsonl'),('shared_reference','shared_display.json'),('classification_reference','classification.json')]:exact(machine[key],oldref(name))
 integer(machine['record_count'],1632);integer(machine['byte_count'],d['index']['task_jsonl_reference']['byte_count']);exact(machine['sha256'],inputs['tasks']['sha256'])
 shards=[]
 for i,s in enumerate(machine['shards']):
  exact(s['filename'],f'machine/tasks-{i:05d}.jsonl');exact(s['reference'],oldref(s['filename']));shards.append({k:v for k,v in s.items()if k!='reference'})
 reports=[];OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  ownstart=save(OUTPUT/'started.json',dict(schema='DATED_H_RECOVERY_READBACK_STARTED_V1',input_references=refs,parent_input_references=inputs,source_hashes=sources,**FLAGS))
  machine_report=core.inspect_machine_stream(index=d['index'],shards=({'filename':s['filename'],'raw_bytes':read_bytes(oldref(s['filename']))}for s in shards),expected_tasks_reference=inputs['tasks'],saved_descriptors=shards,saved_task_locations=machine['task_locations'])
  ids=core.ids(d['index']);offset=0;whole=hashlib.sha256()
  with physical(PARENT/'tasks.jsonl').open('rb')as stream:
   for old,p in zip(originals,m['packages']):
    a=p['start_task_ordinal'];b=p['stop_task_ordinal'];tasks=[];pending=read(old['pending_reference'])
    for position in range(a,b):
     raw=stream.readline(32*1024**2+1);require(raw.endswith(b'\n')and len(raw)<=32*1024**2,'Full bounded task line')
     exact(d['index']['task_index'][position]['jsonl_record'],dict(record_index=position,byte_start=offset,byte_stop=offset+len(raw),row_sha256=sha(raw)))
     row=loads(raw);integer(row['task_ordinal'],position);exact(row['numerical_task_id'],ids[position]);tasks.append(restore(row,d['shared']));offset+=len(raw);whole.update(raw)
    for j,t in enumerate(tasks):
     missing=t['schema']=='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1';position=a+j
     exact(p['tasks'][j],dict(task_ordinal=position,numerical_task_id=ids[position],comparison_status=d['index']['task_index'][position]['status'],integer_status='COMPARISON_NOT_SUPPLIED'if missing else t['series']['candidate_integer']['status'],continuous_status='COMPARISON_NOT_SUPPLIED'if missing else t['series']['candidate_continuous']['status'],local_task_number=j+1,navigation_row=j+2))
    integer(len(p['tasks']),b-a);exact(p['workbook_reference']['path'],str(RECOVERY/p['filename']));wr=artifact_ref(p['workbook_reference']);wbbytes=read_bytes(wr);integer(len(wbbytes),p['byte_count'])
    wb=z.read_workbook(wbbytes);chart=artifact(p['chart_source_index_reference']);false(chart);integer(chart['attempt_index'],old['attempt_index']);integer(chart['start_task_ordinal'],a);integer(chart['stop_task_ordinal'],b);exact(chart['task_ids'],ids[a:b]);verify_chart_sidecars(chart,tasks)
    exact(chart['source_jsonl_records'],[dict(numerical_task_id=ids[i],task_ordinal=i,source_record=d['index']['task_index'][i]['jsonl_record'])for i in range(a,b)])
    exact(p['chart_source_index_reference']['sha256'],pending['chart_source_index_reference']['sha256']);artifact_ref(p['expected_cells_reference']);z.inspect_capture_records(wb,cell_records(p['expected_cells_reference']),chart)
    if p['action']==core.REPAIR:
     repair_dir=RECOVERY/f"repair-{p['package_index']:04d}"
     for key,filename in [('expected_cells_reference','expected_cells.jsonl'),('chart_source_index_reference','chart_source_index.json'),('repair_evidence_reference','repair_evidence.json')]:exact(p[key]['path'],str(repair_dir/filename));newref(p[key])
     for j,preview in enumerate(p['previews']):exact(preview['path'],str(repair_dir/f'preview-{j}.png'));newref(preview)
     delta=core.inspect_singleton_delta(old_capture=cell_records(pending['expected_cells_reference']),new_capture=cell_records(p['expected_cells_reference']),task_id=ids[a]);detail=core.inspect_repaired_graph(workbook=wb,tasks=tasks,task_ids=ids[a:b])
     e=artifact(p['repair_evidence_reference']);require(e['schema']=='DATED_H_FAILED_PARENT_SINGLETON_REPAIR_V1'and e['original_attempt_is_not_new_export']is True,'Repair evidence');false(e)
     for key,value in [('original_pending_reference',old['pending_reference']),('original_workbook_reference',old['original_workbook_reference']),('new_workbook_reference',wr),('source_record',d['index']['task_index'][a]['jsonl_record'])]:exact(e[key],value)
     integer(e['new_byte_count'],len(wbbytes));integer(e['cell_preservation']['checked_cells'],delta['checked_cells']);integer(e['cell_preservation']['changed_cells'],1)
    else:
     core.inspect_copy_bytes(original_bytes=read_bytes(old['original_workbook_reference']),recovered_bytes=wbbytes,original_reference=old['original_workbook_reference'],recovered_reference=wr)
     exact(p['expected_cells_reference'],pending['expected_cells_reference']);exact(p['chart_source_index_reference'],pending['chart_source_index_reference']);exact(p['previews'],pending['previews']);require(p['repair_evidence_reference']is None,'No invented copy repair')
     if tasks[0]['schema']=='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1':
      require(all(t['schema']==tasks[0]['schema']for t in tasks)and not wb['charts'],'Missing not cash');z.source_table(wb,'任务索引',[[i+1,'ID: '+t['numerical_task_id'],'COMPARISON_NOT_SUPPLIED']for i,t in enumerate(tasks)]);detail={'missing_task_count':len(tasks)}
     else:detail=z.inspect_static_chart_graph(wb,tasks,ids[a:b])
    integer(p['actual_data_rows'],pending['costs']['dataRows'])
    if tasks[0]['schema']=='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1':integer(p['actual_data_rows'],len(tasks)+1)
    else:
     source_detail=z.inspect_saved_source_tables(wb,tasks,ids[a:b]);expected_rows=source_detail['risk_detail_rows']+254*len(tasks)+len(chart['risk_source_index'])+127+len(tasks)+1+len(source_detail['risk_detail_page_lengths'])+len(source_detail['risk_coordinate_page_lengths']);integer(p['actual_data_rows'],expected_rows)
    require(len(p['previews'])==len(pending['previews']),'All preview roles')
    for new,previous in zip(p['previews'],pending['previews']):artifact_ref(new);exact({k:v for k,v in new.items()if k not in ('path','sha256')},{k:v for k,v in previous.items()if k not in ('path','sha256')})
    reports.append(dict(package_index=p['package_index'],task_count=len(tasks),workbook_reference=wr,action=p['action']))
   require(stream.read(1)==b'','Complete source EOF')
  integer(offset,machine['byte_count']);exact(whole.hexdigest(),inputs['tasks']['sha256'])
  nav=m['navigation'];integer(nav['link_count'],1632)
  for r in [nav[k]for k in ('workbook_reference','expected_cells_reference','native_links_reference')]+nav['previews']:newref(r)
  wb=z.read_workbook(read_bytes(nav['workbook_reference']));core.inspect_navigation_links(workbook=wb,expected_links=partition['native_links']);inspect_navigation(z,wb,d['index'],d['classification'],m['packages'],ids)
  z.inspect_capture_records(wb,cell_records(nav['expected_cells_reference']),{'charts':[]},partition['native_links'])
  from itertools import zip_longest
  for x,y in zip_longest(cell_records(nav['expected_cells_reference']),cell_records(oldref_with_capture(oldref('navigation_expected_cells.jsonl')))):exact(x,y)
  intents=artifact(nav['native_links_reference']);require(intents['schema']=='DATED_H_RECOVERED_NATIVE_LINKS_V1','Navigation links role');false(intents);exact(intents['links'],partition['native_links']);exact(intents['helper_reference'],inputs['native_helper']);exact(intents['utf8_transport_reference'],inputs['wire'])
  def final_guard():
   check_data_namespaces(inputs);exact(inventory_map(PARENT,invdoc['files']),oldfiles);exact(inventory_map(RECOVERY,m['output_inventory'],('export_manifest.json','publication.json')),newfiles);guard(sources);guard(oldfiles);guard(newfiles)
  final_guard()
  report=save(OUTPUT/'independent_readback.json',dict(schema='DATED_H_FAILED_EXPORT_RECOVERY_INDEPENDENT_READBACK_V1',status='PASS_STATIC_SAVED_BYTES_AND_SOURCE_GRAPH',manifest_reference=refs['manifest'],publication_reference=refs['recovery_publication'],parent_failure_reference=inputs['failure'],parent_remains_failed=True,original_b9_pass_required=False,reader_sha256=LOADED,source_hashes=sources,started_reference=ownstart,verified_task_count=1632,verified_package_count=len(reports),packages=reports,machine=machine_report,navigation_links_verified=1632,classification_rows_verified=101,scope='SAVED_BYTES_AND_SOURCE_GRAPH_NOT_VISUAL_NATIVE_EXCEL_OR_ECONOMIC_REPLAY',**FLAGS))
  final_guard();exact(names(OUTPUT),['independent_readback.json','started.json']);require(hash_file(ownstart['path'])==ownstart['sha256']and hash_file(report['path'])==report['sha256'],'Own durable output');return report
 except BaseException as error:
  save(OUTPUT/'failure.json',dict(status='FAILED_NO_RETRY',error_type=type(error).__name__,error=str(error),completed_package_count=len(reports),packages=reports,input_references=refs,**FLAGS));raise


def oldref_with_capture(r):
 # Old navigation capture is saved as a bare reference. Derive only stream
 # envelope counters; its original bytes remain hash-bound and read separately.
 count=size=0;h=hashlib.sha256()
 with physical(r['path']).open('rb')as f:
  for line in f:require(line.endswith(b'\n')and len(line)<=64*1024**2,'Bounded capture');count+=1;size+=len(line);h.update(line)
 exact(h.hexdigest(),r['sha256']);return dict(**r,record_count=count,byte_count=size)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
