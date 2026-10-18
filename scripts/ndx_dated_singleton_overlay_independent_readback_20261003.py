"""Source-bound static H XLSX readback. Never imports a publisher or runs Excel.

Future external anchors fail before reads. Workbook visuals, dynamic evaluation,
Excel opening and delivery acceptance remain explicitly outside this report.
"""
import argparse,copy,hashlib,json,os,re,types
from pathlib import Path
STORAGE=Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
EXPORT=STORAGE/'dated_workbook_extension_20261003_v1'
OVERLAY=STORAGE/'dated_singleton_repair_overlay_20261003_v1'
OUTPUT=STORAGE/'dated_singleton_overlay_independent_readback_20261003_v1'
DATA=STORAGE/'dated_workbook_extension_data_20261003_v1'
BOUND={
 'manifest':(str(OVERLAY/'export_manifest.json'),None),'export_publication':(str(OVERLAY/'publication.json'),None),
 'parent_manifest':(str(EXPORT/'export_manifest.json'),None),'parent_publication':(str(EXPORT/'publication.json'),None),
 'publisher':(str(ROOT/'scripts/ndx_dated_singleton_overlay_publish_20261003.mjs'),'139ed56bc5874f4d6be6ff483025a29d9808e96dc6e052e7a8f92f89e6d8f7e8'),
 'parent_publisher':(str(ROOT/'scripts/ndx_dated_workbook_extension_publish_20261003.mjs'),'f3375accf43c4f765b83b6e708e3986262e5a249107724d115adfbbdf651a771'),
 'overlay_plan':(str(ROOT/'scripts/ndx_dated_singleton_overlay_plan_20261003.mjs'),'ef7c9c8704fc211a7bbd0e0932d2de2451c275354f8f6f5e8dcb9dbfe028567d'),
 'repair':(str(ROOT/'scripts/ndx_dated_singleton_path_label_repair_20261003.mjs'),'f5ef70fbc034a17a1254723b07b4cf21278d1ee11967a6a1c11489bb008fdc00'),
 'native_overlay':(str(ROOT/'scripts/ndx_dated_overlay_native_links_20261003.py'),'7126d0ade019db5a8ab1540b94de64fd18f49413f3160729379aea672468af99'),
 'pure':(str(ROOT/'backtest/ndx_h_workbook_export_inspection_research.py'),'2a7730f4cb813e5ecbc204f9850a5df21a9ff6fc18ac50667278704c4e8b85f4')}
INPUT_BOUND={
 'index':(str(DATA/'index.json'),'879402d5041928e36096ed24d09404bd9a4fecbdc76428225beaa01529117603'),'publication':(str(DATA/'publication.json'),'5ec8da155e9bb40f44aa3a50cf3305a72fb7f6b670660b91f4f72b86e8c96521'),
 'audit':(str(STORAGE/'dated_workbook_extension_data_independent_readback_20261003_v1/independent_readback.json'),'ef6adcb90ed6650d54d54965ff2540dfb392a34bc5c4f9982752bd88e602c1ce'),
 'tasks':(str(DATA/'tasks.jsonl'),'6ce82b33ba276ee52e5526503d2faed1f1637ab3d91bce10afd4400df7e8f72a'),'shared':(str(DATA/'shared_display.json'),'77396263d69c988d73269adc18d5dca226385b5997735879e42518a1e73bb536'),'classification':(str(DATA/'classification.json'),'976b46dab1fb2f44305156562454876cb1fab1001b6f3ab29361b719cb8e99b5'),
 'data_producer':(str(ROOT/'scripts/ndx_dated_workbook_extension_data_20261003.py'),'c07e34d389b8d4990df31db8e70a9a70c87e2856d9abf2b5a017f64b777c8577'),
 'data_reader':(str(ROOT/'scripts/ndx_dated_workbook_extension_data_independent_readback_20261003.py'),'53357679a47679a98012cf06a58823594a9826c04f9e4ce7cf80ed1aa6d630c6'),
 'core':(str(ROOT/'scripts/ndx_dated_workbook_extension_20261003.mjs'),'b2770383e837c136755bad29caaea8cc5b817f5b4678617a5a2ceb23d513263a'),
 'path_component':(str(ROOT/'scripts/ndx_dated_path_chart_component_20261003.mjs'),'39fcd13d7588b4c1527bcd4dbf79bf5ec626da157d337f77323910231dc8023a'),
 'risk_component':(str(ROOT/'scripts/ndx_dated_risk_chart_component_20261003.mjs'),'9a4112a2abaaaee7c5bb4bd6c0c632519f06cbe92a1c0314135d1efa194179d5'),
 'navigation_component':(str(ROOT/'scripts/ndx_dated_extension_navigation_component_20261003.mjs'),'65e0f0760d0730b65e177e8e884eeb82c21f1ebe3747a364879cc868cdbe75b6'),
 'native_helper':(str(ROOT/'scripts/ndx_workbook_native_hyperlinks_20261003.py'),'267333bd62a3399c6ab3c97104bf884a737e116a51e8c62243aa3e0fcd6a475d')}
EXPORT_FALSE=('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','fit_performed','account_executed','independent_export_readback_passed','visual_acceptance_passed','workbook_delivered')
FLAGS=dict(formal_comparison_passed=False,point_in_time_verified=False,promotion_allowed=False,future_independent_oos=False,economics_recomputed=False,risk_recomputed=False,fit_performed=False,account_executed=False,visual_acceptance_passed=False,native_excel_open_verified=False,dynamic_formula_evaluation_verified=False,workbook_delivered=False,full_transitive_source_closure_reverified=False)

def require(ok,message):
    if not ok:raise ValueError(message)
def enc(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b):require(enc(a)==enc(b),'Exact evidence mismatch')
def integer(v,n=None):require(type(v)is int and v>=0 and (n is None or v==n),'Exact integer count');return v
def reference(p,h):return dict(path=str(p),sha256=h)
def valid(r):require(type(r)is dict and type(r.get('path'))is str and r['path'].strip()==r['path'] and type(r.get('sha256'))is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Pending or invalid external SHA');return r
def merge(s,r):valid(r);require(r['path']not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def hash_file(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()
def loads(b):
    def pairs(rows):
        d={}
        for k,v in rows:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def read_bound_bytes(r):
    valid(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed workbook bytes');return b
def read(r):valid(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Source bytes');return loads(b)
def false(v):
    for k in EXPORT_FALSE:require(v[k]is False,'Export authority '+k)
def guard(s):
    require(hash_file(SOURCE)==LOADED,'Reader drift')
    for p,h in s.items():require(hash_file(p)==h,'Source drift '+p)
def save(p,v):
    b=enc(v)
    with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved bytes');return reference(p,sha(b))
def within(p):
    result=Path(p).resolve();require(result.is_relative_to(EXPORT.resolve()) and not Path(p).is_symlink(),'Fixed export descendant');return result

def validate_manifest(m,p,index,audit,refs,inputs):
    require(m['schema']=='DATED_H_WORKBOOK_EXTENSION_EXPORT_V1' and m['status']=='EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE','Pending independent export')
    require(p['schema']=='DATED_H_WORKBOOK_EXTENSION_PUBLICATION_V1' and p['status']=='PUBLISHED_EXPORT_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE','Export publication')
    false(m);false(p);exact(p['manifest_reference'],refs['manifest']);exact(m['source_hashes'],p['source_hashes']);exact(m['input_references'],inputs)
    require(index['schema']=='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1','Saved H data')
    require(audit['schema']=='DATED_WORKBOOK_EXTENSION_DATA_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Saved independent H data audit')
    exact(audit['index_reference'],inputs['index']);exact(audit['publication_reference'],inputs['publication']);exact(audit['reader_sha256'],inputs['data_reader']['sha256'])
    integer(index['planned_task_count'],1632);ids=[v['numerical_task_id'] for v in index['task_index']];require(len(ids)==len(set(ids))==1632,'All original IDs')
    for i,row in enumerate(index['task_index']):integer(row['task_ordinal'],i)
    for k,v in [('planned_task_count',1632),('packaged_task_count',1632),('unprocessed_task_count',0),('classification_count',101),('shared_series_count',4),('shared_risk_track_count',2)]:integer(m[k],v)
    exact(m['default_task_id'],ids[0]);require(m['actual_package_bytes_within_50_mib']is True and m['source_eof_verified']is True and m['original_order_preserved']is True,'Complete engineering publication')
    require(m['rendered_previews_are_not_visual_acceptance']is True and m['expected_cells_are_author_snapshots_not_independent_proof']is True,'No visual/independent claims')
    require(p['all_package_callbacks_were_pending_until_complete_eof']is True,'EOF publication')
    return ids

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

def validate_machine_location(loc,descriptor,position,expected_start,raw):
    integer(loc['task_ordinal'],position);integer(loc['shard_index']);integer(descriptor['shard_index'],loc['shard_index']);integer(descriptor['start_task_ordinal']);integer(descriptor['stop_task_ordinal'])
    require(descriptor['start_task_ordinal']<=position<descriptor['stop_task_ordinal'],'Machine task shard order');integer(loc['byte_start'],expected_start);integer(loc['byte_stop'],expected_start+len(raw));exact(loc['row_sha256'],sha(raw))


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

def output_closure(manifest):
    exact(manifest['output_inventory_excludes'],['export_manifest.json','publication.json']);out={}
    for row in manifest['output_inventory']:
        name=row['path'];require(type(name)is str and not name.startswith('/') and '..'not in name.split('/') and '\\'not in name,'Relative output inventory');p=within(EXPORT/name);require(str(p)not in out,'Unique output inventory');integer(row['byte_count']);require(p.stat().st_size==row['byte_count'],'Output size');merge(out,reference(p,row['sha256']))
    files=[]
    for p in EXPORT.rglob('*'):
        require(not p.is_symlink(),'No output symlinks')
        if p.is_file():files.append(str(p.resolve()))
    exact(sorted(files),sorted(list(out)+[str((EXPORT/x).resolve()) for x in manifest['output_inventory_excludes']]))
    return out

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


def namespace_files(root,manifest):
    exact(manifest['output_inventory_excludes'],['export_manifest.json','publication.json']);expected={}
    for row in manifest['output_inventory']:
        p=(root/row['path']).resolve();require(not Path(row['path']).is_absolute() and p.is_relative_to(root.resolve()) and not p.is_symlink(),'Fixed inventory namespace');integer(row['byte_count']);require(p.stat().st_size==row['byte_count'],'Declared artifact bytes');require(str(p) not in expected,'Unique artifact inventory');expected[str(p)]=row['sha256']
    files=[]
    for p in root.rglob('*'):
        require(not p.is_symlink(),'No artifact symlink')
        if p.is_file():files.append(str(p.resolve()))
    exact(sorted(files),sorted(list(expected)+[str((root/n).resolve()) for n in manifest['output_inventory_excludes']]))
    require(not (root/'failure.json').exists(),'Failed export cannot be accepted');return expected


def validate_overlay(m,p,parent,refs):
    require(m['schema']=='DATED_H_SINGLETON_REPAIR_OVERLAY_EXPORT_V1' and m['status']=='EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE','New explicit overlay schema')
    require(p['schema']=='DATED_H_SINGLETON_OVERLAY_PUBLICATION_V1' and p['status']=='PUBLISHED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE','Overlay publication role')
    false(m);false(p)
    for obj in (m,p):
        for key in ('source_bytes_authenticated','native_excel_open_verified'):require(obj[key] is False,'No overlay authority '+key)
    exact(p['manifest_reference'],refs['manifest']);exact(p['source_hashes'],m['source_hashes'])
    exact(m['parent_manifest_reference'],refs['parent_manifest']);exact(m['parent_publication_reference'],refs['parent_publication'])
    exact(m['parent_input_references_preserved'],parent['input_references']);exact(m['parent_source_hashes_preserved'],parent['source_hashes']);exact(m['parent_output_inventory_preserved'],parent['output_inventory']);exact(m['machine_index_reference'],parent['machine_index_reference'])
    for k,n in (('planned_task_count',1632),('packaged_task_count',1632),('unprocessed_task_count',0)):integer(m[k],n)
    require(len(m['packages'])==len(parent['packages']),'No package regrouping');changed=[]
    allowed={'workbook_reference','expected_cells_reference','chart_source_index_reference','previews','byte_count','sha256','repair_evidence_reference'}
    for i,(old,new) in enumerate(zip(parent['packages'],m['packages'])):
        integer(old['package_index'],i);integer(new['package_index'],i);replace=len(old['tasks'])==1 and old['tasks'][0]['comparison_status']!='COMPARISON_NOT_SUPPLIED'
        if not replace:exact(old,new);continue
        changed.append(i);exact({k:v for k,v in old.items() if k not in allowed},{k:v for k,v in new.items() if k not in allowed})
        exact(new['workbook_reference'],reference(OVERLAY/old['filename'],new['sha256']));integer(new['byte_count']);require(0<new['byte_count']<=50*1024**2,'New actual export limit')
        require(len(new['previews'])==len(old['previews']),'All original preview roles')
        for a,b in zip(old['previews'],new['previews']):exact({k:v for k,v in a.items() if k not in ('path','sha256')},{k:v for k,v in b.items() if k not in ('path','sha256')})
        for r in [new[k] for k in ('workbook_reference','expected_cells_reference','chart_source_index_reference','repair_evidence_reference')]+new['previews']:require(Path(r['path']).resolve().is_relative_to(OVERLAY.resolve()),'Repaired evidence only new namespace')
    integer(m['replacement_package_count'],len(changed));integer(m['reused_package_count'],len(m['packages'])-len(changed));require([r['package_index'] for r in m['replacement_map']]==changed,'Exact repair denominator')
    for r,i in zip(m['replacement_map'],changed):
        old=parent['packages'][i];exact(r['task_id'],old['tasks'][0]['numerical_task_id']);exact(r['original_workbook_reference'],old['workbook_reference']);exact(r['replacement_path'],str(OVERLAY/old['filename']));exact(r['allowed_formula_delta'],dict(worksheet='路径查看',cell='B5',repair_reference=refs['repair']))
    return set(changed)


def label_formulas():
    def wrap(x):return '=IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<=1),'+x+',NA()),NA())'
    return wrap("INDEX('任务索引'!$B$2:$B$2,$B$4)"),wrap("'任务索引'!$B$2")


def inspect_repaired_graph(core,wb,tasks,ids):
    require(len(tasks)==len(ids)==1,'Repair contract only one present task')
    source=core.inspect_saved_source_tables(wb,tasks,ids);contract=core.static_graph_contract(1,source,100000);old,new=(v[1:] for v in label_formulas());exact(contract['formulas'][('路径查看','B5')],old);contract['formulas'][('路径查看','B5')]=new
    label=wb['sheets']['路径查看'].get('B5');require(type(label)is dict and label['kind']!='e','Cached repaired label is not error');exact(label['value'],'ID: '+ids[0])
    for (sheet,a),v in contract['literals'].items():core.cell_equal(wb['sheets'][sheet].get(a),v)
    for (sheet,a),v in contract['formulas'].items():require(wb['sheets'][sheet].get(a,{}).get('formula')==v,'Exact source graph formula '+sheet+'!'+a)
    for sheet,n in [('路径查看',1),('风险查看',127)]:exact(wb['validations'].get(sheet,[]),[dict(sqref='B4',type='whole',operator='between',formula1='1',formula2=str(n))])
    require(len(wb['charts'])==8,'All original eight charts');mapping={(c['worksheet'],c['chart_ordinal']):c for c in wb['charts']};require(len(mapping)==8,'Chart ownership')
    for expected in contract['charts']:
        actual=mapping.get((expected['worksheet'],expected['chart_ordinal']));require(actual and actual['chart_type']==expected['chart_type'] and actual['title']==expected['title'],'Chart exact role/title/type');require(len(actual['series'])==len(expected['series']),'All original chart series')
        for a,b in zip(actual['series'],expected['series']):
            for k in ('category_formula','formula'):exact(core.reference_range(a[k]),core.reference_range(b[k]))
    return dict(source_tables=source,static_chart_source_graph_verified=True,only_formula_delta='路径查看!B5',**FLAGS)


def inspect_capture_delta(old_rows,new_rows,tid):
    count=changed=0;old_formula,new_formula=label_formulas()
    from itertools import zip_longest
    for a,b in zip_longest(old_rows,new_rows):
        require(a is not None and b is not None,'Full capture rows');exact({k:v for k,v in a.items() if k not in ('values','formulas')},{k:v for k,v in b.items() if k not in ('values','formulas')})
        for i in range(a['row_count']):
            for j in range(a['column_count']):
                count+=1;target=a['worksheet']=='路径查看' and a['start_row_zero_based']+i==4 and a['start_column_zero_based']+j==1
                if target:
                    exact(a['values'][i][j],'#VALUE!');exact(a['formulas'][i][j],old_formula);exact(b['values'][i][j],'ID: '+tid);exact(b['formulas'][i][j],new_formula);changed+=1
                else:
                    exact(a['values'][i][j],b['values'][i][j]);exact(a['formulas'][i][j],b['formulas'][i][j])
    integer(changed,1);return dict(checked_cells=count,changed_cells=1)


def inspect_navigation_relocation(oldbytes,newbytes,expected_links):
    import io,zipfile,xml.etree.ElementTree as ET
    ns='http://schemas.openxmlformats.org/package/2006/relationships';hyper='http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink'
    with zipfile.ZipFile(io.BytesIO(oldbytes)) as old,zipfile.ZipFile(io.BytesIO(newbytes)) as new:
        exact(old.namelist(),new.namelist());changed=[n for n in old.namelist() if old.read(n)!=new.read(n)];require(len(changed)==1 and re.fullmatch(r'xl/worksheets/_rels/sheet\d+\.xml.rels',changed[0]),'Only navigation relationships changed')
        a=ET.fromstring(old.read(changed[0]));b=ET.fromstring(new.read(changed[0]));require(a.tag==b.tag=='{'+ns+'}Relationships','Relationship root role');exact(a.attrib,b.attrib);exact(a.text,b.text);exact(a.tail,b.tail);require(len(a)==len(b),'No relationship addition/removal');targets=[]
        for x,y in zip(a,b):
            require(x.tag==y.tag=='{'+ns+'}Relationship' and x.text==y.text and x.tail==y.tail and len(x)==len(y)==0,'Same leaf relationship nodes')
            if x.get('Type')==hyper:
                exact({k:v for k,v in x.attrib.items() if k!='Target'},{k:v for k,v in y.attrib.items() if k!='Target'});require(re.fullmatch(r'package-\d{4}\.xlsx',x.get('Target','')),'Original package basename');targets.append(y.get('Target'))
            else:exact(x.attrib,y.attrib)
        exact(targets,[l['target'] for l in expected_links])


def readback(*,execute=False):
    require(execute is True,'Explicit readback');refs={k:valid(reference(p,h)) for k,(p,h) in BOUND.items()};inputs={k:valid(reference(p,h)) for k,(p,h) in INPUT_BOUND.items()};require(not OUTPUT.exists(),'Create only no retry')
    sources={str(SOURCE):LOADED}
    for r in list(refs.values())+list(inputs.values()):merge(sources,r)
    guard(sources);check_data_namespaces(inputs);parent=read(refs['parent_manifest']);parentpub=read(refs['parent_publication']);m=read(refs['manifest']);pub=read(refs['export_publication']);index=read(inputs['index']);audit=read(inputs['audit'])
    ids=validate_manifest(parent,parentpub,index,audit,dict(manifest=refs['parent_manifest']),inputs);validate_data_parents(index,read(inputs['publication']),audit,inputs);changed=validate_overlay(m,pub,parent,refs)
    expected={refs['parent_publisher']['path']:refs['parent_publisher']['sha256']}
    for r in inputs.values():merge(expected,r)
    for claims in (index['source_hashes'],audit['source_hashes']):
        for p,h in claims.items():merge(expected,reference(p,h))
    exact(expected,parent['source_hashes']);newrefs=[refs[k] for k in ('parent_manifest','parent_publication','parent_publisher','overlay_plan','repair','native_overlay')];exact(m['new_source_references'],newrefs)
    overlay_sources=dict(expected);merge(overlay_sources,refs['publisher'])
    for r in newrefs:merge(overlay_sources,r)
    exact(m['source_hashes'],overlay_sources)
    for p,h in overlay_sources.items():merge(sources,reference(p,h))
    oldfiles=namespace_files(EXPORT,parent);newfiles=namespace_files(OVERLAY,m);files={**oldfiles,**newfiles};guard(files);guard(sources)
    def artifact_ref(r):
        valid(r);p=str(Path(r['path']).resolve());require(files.get(p)==r['sha256'],'Artifact in exactly two bound namespaces');return r
    def artifact(r):return read(artifact_ref(r))
    for document in (parent,m):
        for package in document['packages']:
            for r in [package[k] for k in ('workbook_reference','expected_cells_reference','chart_source_index_reference')]+package['previews']:artifact_ref(r)
        nav=document['navigation']
        for r in [nav[k] for k in ('workbook_reference','expected_cells_reference','native_links_reference')]+nav['previews']:artifact_ref(r)
    corebytes=read_bound_bytes(refs['pure']);core=types.ModuleType('_overlay_independent_core');exec(compile(corebytes,refs['pure']['path'],'exec'),core.__dict__)
    shared=read(inputs['shared']);classification=read(inputs['classification']);machine=artifact(m['machine_index_reference']);integer(machine['record_count'],1632);exact(machine['full_tasks_reference'],reference(EXPORT/'tasks.jsonl',inputs['tasks']['sha256']));integer(len(machine['task_locations']),1632)
    exact(machine['shared_reference'],reference(EXPORT/'shared_display.json',inputs['shared']['sha256']));exact(machine['classification_reference'],reference(EXPORT/'classification.json',inputs['classification']['sha256']))
    for key in ('full_tasks_reference','shared_reference','classification_reference'):artifact_ref(machine[key])
    require(machine['schema']=='DATED_H_MACHINE_DATA_INDEX_V1','Machine schema');false(machine);integer(machine['byte_count'],index['task_jsonl_reference']['byte_count'])
    start=0
    for j,s in enumerate(machine['shards']):
        integer(s['shard_index'],j);integer(s['start_task_ordinal'],start);integer(s['stop_task_ordinal']);require(s['filename']==f'machine/tasks-{j:05d}.jsonl','Machine fixed shard path');integer(s['record_count'],s['stop_task_ordinal']-start);integer(s['byte_count'],(EXPORT/s['filename']).stat().st_size);require(0<s['record_count']<=100000 and s['byte_count']<=32*1024**2,'Machine caps');require(files[str(within(EXPORT/s['filename']))]==s['sha256'],'Machine shard bytes');start=s['stop_task_ordinal']
    integer(start,1632)
    accepted=[];oversize=0
    for i,a in enumerate(parent['attempts']):
        integer(a['attempt_index'],i);r=a['reference'];exact(r['path'],str(EXPORT/'attempts'/f'attempt-{i:05d}'/'artifact.xlsx'));require(files[str(within(r['path']))]==r['sha256']==a['sha256'],'Saved attempt bytes');integer(a['bytes'],Path(r['path']).stat().st_size)
        if a['status']=='OVERSIZE_ATTEMPT_NOT_ACCEPTED':require(a['bytes']>50*1024**2,'Actual oversize retained');oversize+=1
        else:require(a['status']=='PENDING_COMPLETE_STREAM_AND_SOURCE_PUBLICATION' and a['bytes']<=50*1024**2,'Accepted bounded attempt');accepted.append(a)
    integer(parent['oversize_attempt_count'],oversize);integer(len(accepted),len(parent['packages']))
    for a,p in zip(accepted,parent['packages']):
        exact(a['reference'],p['attempt_reference']);integer(a['start_task_ordinal'],p['start_task_ordinal']);integer(a['stop_task_ordinal'],p['stop_task_ordinal']);exact(a['task_ids'],[t['numerical_task_id']for t in p['tasks']]);exact(a['sha256'],p['sha256'])
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        started_reference=save(OUTPUT/'started.json',dict(input_references=refs,original_data_references=inputs,source_hashes=sources,original_b9_pass_required=False,**FLAGS));reports=[];ordinal=offset=0;h=hashlib.sha256();shard_offsets={i:0 for i in range(len(machine['shards']))}
        with (EXPORT/'tasks.jsonl').open('rb') as stream:
            for pi,package in enumerate(m['packages']):
                old=parent['packages'][pi];integer(package['package_index'],pi);integer(package['start_task_ordinal'],ordinal);stop=integer(package['stop_task_ordinal']);require(ordinal<stop<=1632,'Full contiguous package');tasks=[]
                for position in range(ordinal,stop):
                    raw=stream.readline(64*1024**2+1);require(raw.endswith(b'\n') and len(raw)<=64*1024**2,'Whole source record');entry=index['task_index'][position];exact(entry['jsonl_record'],dict(record_index=position,byte_start=offset,byte_stop=offset+len(raw),row_sha256=sha(raw)));row=loads(raw);exact(row['numerical_task_id'],ids[position]);integer(row['task_ordinal'],position);tasks.append(restore(row,shared));h.update(raw);offset+=len(raw)
                    loc=machine['task_locations'][position];integer(loc['shard_index']);require(loc['shard_index']<len(machine['shards']),'Shard index bounded');s=machine['shards'][loc['shard_index']];validate_machine_location(loc,s,position,shard_offsets[loc['shard_index']],raw);shard_offsets[loc['shard_index']]=loc['byte_stop']
                    with (EXPORT/s['filename']).open('rb') as part:part.seek(loc['byte_start']);require(part.read(len(raw))==raw,'Original machine bytes')
                for local,t in enumerate(tasks):
                    absent=t['schema']=='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1';position=ordinal+local
                    exact(package['tasks'][local],dict(numerical_task_id=ids[position],task_ordinal=position,local_task_number=local+1,navigation_row=local+2,comparison_status=index['task_index'][position]['status'],integer_status='COMPARISON_NOT_SUPPLIED' if absent else t['series']['candidate_integer']['status'],continuous_status='COMPARISON_NOT_SUPPLIED' if absent else t['series']['candidate_continuous']['status']))
                require(package['filename']==f'package-{pi+1:04d}.xlsx','Stable package filename')
                exact([t['numerical_task_id'] for t in package['tasks']],ids[ordinal:stop]);wr=package['workbook_reference'];artifact_guard=files.get(str(Path(wr['path']).resolve()));require(artifact_guard==wr['sha256']==package['sha256'],'Chosen package byte anchor');integer(package['byte_count'],Path(wr['path']).stat().st_size);require(package['byte_count']<=50*1024**2,'Export size')
                wb=core.read_workbook(read_bound_bytes(wr));chart=artifact(package['chart_source_index_reference']);false(chart);integer(chart['start_task_ordinal'],ordinal);integer(chart['stop_task_ordinal'],stop);verify_chart_sidecars(chart,tasks);exact(chart['task_ids'],ids[ordinal:stop]);exact(chart['source_jsonl_records'],[dict(numerical_task_id=ids[i],task_ordinal=i,source_record=index['task_index'][i]['jsonl_record']) for i in range(ordinal,stop)])
                require(files.get(str(Path(package['expected_cells_reference']['path']).resolve()))==package['expected_cells_reference']['sha256'],'Capture bytes anchor')
                core.inspect_capture_records(wb,cell_records(package['expected_cells_reference']),chart)
                if pi in changed:
                    replacement=next(r for r in m['replacement_map'] if r['package_index']==pi);exact(replacement['source_records'],[dict(numerical_task_id=ids[ordinal],task_ordinal=ordinal,jsonl_record=index['task_index'][ordinal]['jsonl_record'])])
                    detail=inspect_repaired_graph(core,wb,tasks,ids[ordinal:stop]);preservation=inspect_capture_delta(cell_records(old['expected_cells_reference']),cell_records(package['expected_cells_reference']),ids[ordinal]);evidence=artifact(package['repair_evidence_reference']);require(evidence['schema']=='DATED_SINGLETON_PATH_LABEL_REPAIR_V1' and evidence['task_id']==ids[ordinal] and evidence['parent_attempt_is_not_new_export_evidence'] is True,'Repair evidence role');exact(evidence['new_workbook_reference'],wr);exact(evidence['source_record'],index['task_index'][ordinal]['jsonl_record']);exact(evidence['source_jsonl_reference'],inputs['tasks']);exact(evidence['shared_reference'],inputs['shared']);detail['preservation']=preservation
                elif tasks[0]['schema']=='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1':
                    require(all(t['schema']==tasks[0]['schema'] for t in tasks) and not wb['charts'],'Missing stays missing');core.source_table(wb,'任务索引',[[i+1,'ID: '+t['numerical_task_id'],'COMPARISON_NOT_SUPPLIED'] for i,t in enumerate(tasks)]);detail=dict(missing_task_count=len(tasks))
                else:detail=core.inspect_static_chart_graph(wb,tasks,ids[ordinal:stop])
                if tasks[0]['schema']=='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1':integer(package['actual_data_rows'],len(tasks)+1)
                else:
                    sr=detail['source_tables'];count=sr['risk_detail_rows']+254*len(tasks)+len(chart['risk_source_index'])+127+len(tasks)+1+len(sr['risk_detail_page_lengths'])+len(sr['risk_coordinate_page_lengths']);integer(package['actual_data_rows'],count)
                reports.append(dict(package_index=pi,replaced=pi in changed,workbook_reference=wr,detail=detail));ordinal=stop
            require(stream.read(1)==b'','Complete original source EOF')
        integer(ordinal,1632);integer(offset,machine['byte_count']);exact(h.hexdigest(),inputs['tasks']['sha256'])
        for j,s in enumerate(machine['shards']):integer(shard_offsets[j],s['byte_count'])
        nav=m['navigation'];newnav=read_bound_bytes(nav['workbook_reference']);oldnav=read_bound_bytes(parent['navigation']['workbook_reference']);wb=core.read_workbook(newnav);expected_links=[];rows=[]
        for p in m['packages']:
            target=os.path.relpath(p['workbook_reference']['path'],OVERLAY).replace('\\','/')
            for t in p['tasks']:
                i=t['task_ordinal'];entry=index['task_index'][i];expected_links.append(dict(worksheet='全部任务',cell=f'H{i+2}',target=target,location=f"'任务索引'!A{t['navigation_row']}"));rows.append([i+1,'ID: '+t['numerical_task_id'],entry['k'],entry['weight_spec'],entry['status'],t['integer_status'],t['continuous_status'],p['filename'],t['local_task_number'],'分类/来源与风险时点待认证；非独立OOS',entry['jsonl_record'],t['numerical_task_id']])
        exact(wb['native_links'],expected_links);inspect_navigation_relocation(oldnav,newnav,expected_links);core.inspect_classification_table(wb,classification);core.source_table(wb,'全部任务',rows,(4,11));core.inspect_capture_records(wb,cell_records(nav['expected_cells_reference']),{'charts':[]},expected_links)
        intents=artifact(nav['native_links_reference']);exact(intents['links'],m['native_links']);require(len(m['native_links'])==1632,'Full navigation graph')
        for i,(got,want) in enumerate(zip(m['native_links'],expected_links)):
            owner=next(p for p in m['packages'] if p['start_task_ordinal']<=i<p['stop_task_ordinal']);exact(got,dict(**want,numerical_task_id=ids[i],package_index=owner['package_index'],expected_workbook_reference=owner['workbook_reference']))
        check_data_namespaces(inputs);exact(namespace_files(EXPORT,parent),oldfiles);exact(namespace_files(OVERLAY,m),newfiles);guard(sources);guard(files)
        result=save(OUTPUT/'independent_readback.json',dict(schema='DATED_H_SINGLETON_OVERLAY_INDEPENDENT_READBACK_V1',status='PASS_STATIC_SAVED_BYTES_AND_SOURCE_GRAPH',manifest_reference=refs['manifest'],publication_reference=refs['export_publication'],parent_manifest_reference=refs['parent_manifest'],reader_sha256=LOADED,source_hashes=sources,started_reference=started_reference,verified_task_count=1632,replaced_package_count=len(changed),packages=reports,navigation_links_verified=1632,classification_rows_verified=101,original_b9_pass_required=False,original_error_evidence_preserved=True,scope='FULL_CHOSEN_PACKAGE_BYTES_AND_SOURCE_GRAPH_WITH_ONLY_REGISTERED_B5_AND_NATIVE_TARGET_DELTAS;NOT_VISUAL_OR_EXCEL_ACCEPTANCE',**FLAGS))
        exact(namespace_files(EXPORT,parent),oldfiles);exact(namespace_files(OVERLAY,m),newfiles);guard(sources);guard(files);require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Reader exact output');require(hash_file(result['path'])==result['sha256'],'Report durable bytes');require(hash_file(started_reference['path'])==started_reference['sha256'],'Started durable bytes');return result
    except BaseException as e:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_RETRY',error_type=type(e).__name__,error=str(e),**FLAGS));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
