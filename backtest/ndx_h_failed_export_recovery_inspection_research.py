"""Independent saved recovery-byte checks, not publication or visual acceptance.

The source reader must authenticate all input/output refs and filesystem inventory.
Only the frozen ZIP/source-table inspector is shared; no recovery producer/plan,
machine producer, workbook builder, SDK or economic engine is called.
"""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from itertools import zip_longest
from pathlib import PureWindowsPath
import json
import re
from backtest import ndx_h_workbook_export_inspection_research as zip_core

TASKS=1632
LIMIT=32*1024**2
FLAGS=dict(source_origin_authenticated=False,physical_inventory_verified=False,
 numerical_replay_performed=False,visual_acceptance_passed=False,
 native_excel_open_verified=False,workbook_delivery_accepted=False,
 recovery_dispatch_authorized=False,point_in_time_verified=False,promotion_allowed=False)
PARENT_FALSE=('formal_comparison_passed','point_in_time_verified','promotion_allowed',
 'future_independent_oos','economics_recomputed','risk_recomputed','fit_performed',
 'account_executed','independent_export_readback_passed','visual_acceptance_passed','workbook_delivered')
COPY='COPY_ORIGINAL_BYTES_NO_SDK_EXPORT'
REPAIR='REBUILD_SINGLETON_WITH_REGISTERED_B5_ONLY_DELTA'

def require(v,msg):
 if not v:raise ValueError(msg)
def integer(v):require(type(v)is int and v>=0,'Exact integer');return v
def digest(v):require(type(v)is str and re.fullmatch('[0-9a-f]{64}',v),'SHA256');return v
def exact(a,b):require(json.dumps(a,sort_keys=True,ensure_ascii=False,allow_nan=False)==json.dumps(b,sort_keys=True,ensure_ascii=False,allow_nan=False),'Exact evidence')
def reference(r):
 require(type(r)is dict and set(r)=={'path','sha256'},'Exact reference');digest(r['sha256'])
 require(type(r['path'])is str and PureWindowsPath(r['path']).is_absolute(),'Absolute reference')
def ids(index):
 require(index['schema']=='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1' and integer(index['planned_task_count'])==TASKS,'Original full index')
 rows=index['task_index'];require(type(rows)is list and len(rows)==TASKS,'Complete index')
 result=[]
 for i,r in enumerate(rows):require(integer(r['task_ordinal'])==i,'Task ordinal');result.append(digest(r['numerical_task_id']))
 require(len(set(result))==TASKS,'Unique original task IDs');return result

def inspect_failed_parent(*,failure,started,parent_inventory,parent_root,parent_references,index):
 original_ids=ids(index);root=PureWindowsPath(parent_root);require(root.is_absolute(),'Absolute parent root')
 inventory={}
 for v in parent_inventory:
  require(type(v)is dict and set(v)=={'path','sha256','byte_count'},'Inventory fields');integer(v['byte_count']);digest(v['sha256'])
  n=v['path'];require(type(n)is str and n and '\\'not in n and ':'not in n and all(x and x not in ('.','..')and x==x.rstrip(' .') for x in n.split('/')),'Relative inventory path')
  require(n.casefold()not in inventory,'Casefold inventory uniqueness');inventory[n.casefold()]=v
 require(not {'publication.json','export_manifest.json','machine_index.json','navigation_links.json'}&set(inventory),'Failed parent cannot pretend prior successful publication')
 require(type(parent_references)is dict and set(parent_references)=={'failure','started','index_copy'},'Exact failed parent roles')
 for key,name in [('failure','failure.json'),('started','started.json'),('index_copy','sources/index.json')]:
  r=parent_references[key];reference(r);require(PureWindowsPath(r['path'])==root/name,'Parent role path');require(inventory[name]['sha256']==r['sha256'],'Parent role hash inventory')
 require(failure['schema']=='DATED_H_WORKBOOK_EXTENSION_FAILURE_V1'and failure['status']=='FAILED_DO_NOT_CONSUME','Actual failed lineage')
 require(failure['retry_allowed']is False and failure['stream_completed']is True and failure['all_attempts_retained']is True and 'Full ordered task link cells'in failure['error'],'Known terminal phase, not retry')
 require(started['schema']=='DATED_H_WORKBOOK_EXTENSION_STARTED_V1'and started['default_task_id']==original_ids[0],'Original start identity')
 for d in (failure,started):
  for k in PARENT_FALSE:require(d[k]is False,'Parent permissions')
 return dict(parent_failure_preserved=True,prior_successful_publication_claimed=False,parent_references=deepcopy(parent_references),**FLAGS)

def inspect_package_partition(*,index,parent_packages,packages):
 original_ids=ids(index);require(type(packages)is list and len(packages)==len(parent_packages)>0,'Full package count')
 cursor=changed=copied=0;links=[]
 for pi,(old,new)in enumerate(zip(parent_packages,packages)):
  for field in ('package_index','start_task_ordinal','stop_task_ordinal'):integer(old[field]);integer(new[field])
  require(old['package_index']==new['package_index']==pi and old['start_task_ordinal']==cursor,'Package ordinal and complete partition')
  stop=old['stop_task_ordinal'];require(cursor<stop<=TASKS,'Nonempty bounded package')
  statuses=[r['status']for r in index['task_index'][cursor:stop]]
  require(all(s in ('DISPLAY_PROJECTED','COMPARISON_NOT_SUPPLIED')for s in statuses)and len(set(statuses))==1,'Known homogeneous original package statuses')
  expected_action=REPAIR if stop-cursor==1 and statuses[0]=='DISPLAY_PROJECTED'else COPY
  require(old['action']==expected_action,'Repair action independently derived from original index')
  for k in ('package_index','filename','start_task_ordinal','stop_task_ordinal','task_ids','action','original_workbook_reference','pending_reference'):exact(new[k],old[k])
  require(old['filename']==f'package-{pi+1:04d}.xlsx','Stable output basename');exact(old['task_ids'],original_ids[cursor:stop])
  reference(old['original_workbook_reference']);reference(new['workbook_reference']);require(integer(new['byte_count'])<=50*1024**2 and new['byte_count']>0,'XLSX cap')
  require(new['sha256']==new['workbook_reference']['sha256'],'Output hash association');digest(new['sha256'])
  if old['action']==COPY:
   require(new['sha256']==old['original_workbook_reference']['sha256'] and new['byte_count']==old['byte_count'],'Copy hash and size exact');copied+=1
  else:
   require(old['action']==REPAIR and stop-cursor==1,'Only singleton may repair');reference(new['repair_evidence_reference']);changed+=1
  for i in range(cursor,stop):links.append(dict(worksheet='全部任务',cell=f'H{i+2}',target=old['filename'],location=f"'任务索引'!A{i-cursor+2}"))
  cursor=stop
 require(cursor==TASKS and len(links)==TASKS,'All task links covered')
 return dict(package_count=len(packages),copied_package_count=copied,repaired_package_count=changed,native_links=links,**FLAGS)

def inspect_copy_bytes(*,original_bytes,recovered_bytes,original_reference,recovered_reference):
 for b,r in ((original_bytes,original_reference),(recovered_bytes,recovered_reference)):
  require(type(b)is bytes and 0<len(b)<=50*1024**2,'Bounded workbook bytes');reference(r);require(sha256(b).hexdigest()==r['sha256'],'Same inspected workbook bytes')
 require(original_bytes==recovered_bytes,'Copied package original bytes exact')
 return dict(original_bytes_preserved=True,byte_count=len(original_bytes),**FLAGS)

def label_formulas():
 def wrap(x):return '=IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<=1),'+x+',NA()),NA())'
 return wrap("INDEX('任务索引'!$B$2:$B$2,$B$4)"),wrap("'任务索引'!$B$2")

def inspect_singleton_delta(*,old_capture,new_capture,task_id):
 digest(task_id);old_formula,new_formula=label_formulas();changed=total=0;seen=set()
 for a,b in zip_longest(old_capture,new_capture):
  require(type(a)is dict and type(b)is dict,'Complete capture streams')
  exact({k:v for k,v in a.items()if k not in ('values','formulas')},{k:v for k,v in b.items()if k not in ('values','formulas')})
  nr=integer(a['row_count']);nc=integer(a['column_count']);require(0<nr*nc<=2000000,'Bounded capture dimensions')
  sr=integer(a['start_row_zero_based']);sc=integer(a['start_column_zero_based'])
  for item in (a,b):
   for field in ('values','formulas'):require(type(item[field])is list and len(item[field])==nr and all(type(r)is list and len(r)==nc for r in item[field]),'Exact capture matrix shape')
  for i in range(nr):
   for j in range(nc):
    key=(a['worksheet'],sr+i,sc+j);require(key not in seen,'Unique captured cell');seen.add(key);total+=1
    if key==('路径查看',4,1):
     exact((a['values'][i][j],a['formulas'][i][j]),('#VALUE!',old_formula));exact((b['values'][i][j],b['formulas'][i][j]),('ID: '+task_id,new_formula));changed+=1
    else:exact((a['values'][i][j],a['formulas'][i][j]),(b['values'][i][j],b['formulas'][i][j]))
 require(changed==1,'Exactly one B5 delta')
 return dict(checked_cells=total,changed_cells=1,allowed_cell='路径查看!B5',**FLAGS)

def inspect_repaired_graph(*,workbook,tasks,task_ids):
 require(len(tasks)==len(task_ids)==1,'Singleton graph')
 source=zip_core.inspect_saved_source_tables(workbook,tasks,task_ids)
 graph=zip_core.static_graph_contract(1,source,100000);old,new=label_formulas()
 require(graph['formulas'][('路径查看','B5')]==old[1:],'Frozen original graph')
 cell=workbook['sheets']['路径查看']['B5'];require(cell['formula']==new[1:] and cell['kind']!='e' and cell['value']=='ID: '+task_ids[0],'Repaired label formula/cache')
 # Restore only the reviewed formula on an independent inspection copy, then
 # use the unchanged frozen graph checker for every source table and eight charts.
 restored=deepcopy(workbook);restored['sheets']['路径查看']['B5']['formula']=old[1:]
 detail=zip_core.inspect_static_chart_graph(restored,tasks,task_ids)
 return dict(detail=detail,only_formula_delta='路径查看!B5',**FLAGS)

def inspect_navigation_links(*,workbook,expected_links):
 """Actual OOXML links must match independently reconstructed package locations.

 This checks the decoded Chinese names too; a claimed UTF-8 transport marker is
 not sufficient. Full navigation cells/classification are checked separately by
 the frozen source-table inspector in the final source reader.
 """
 require(type(expected_links)is list and len(expected_links)==TASKS,'All navigation links')
 for i,link in enumerate(expected_links):
  require(set(link)=={'worksheet','cell','target','location'}and link['worksheet']=='全部任务'and link['cell']==f'H{i+2}','Exact navigation cell')
  require(re.fullmatch('package-[0-9]{4}\\.xlsx',link['target'])and re.fullmatch("'任务索引'!A[1-9][0-9]*",link['location']),'Native local package and Chinese target')
 exact(workbook['native_links'],expected_links);require(workbook['charts']==[],'No navigation charts invented')
 return dict(native_links_verified=TASKS,unicode_worksheet_targets_verified=True,**FLAGS)

def inspect_machine_stream(*,index,shards,expected_tasks_reference,saved_descriptors,saved_task_locations):
 """Independent record-at-a-time check; supplied shard blobs <=32MiB, no JSON."""
 ids(index);reference(expected_tasks_reference)
 source=index['task_jsonl_reference'];exact({k:source[k]for k in ('path','sha256')},expected_tasks_reference)
 require(integer(source['record_count'])==TASKS,'Original machine count');integer(source['byte_count'])
 whole=sha256();ordinal=global_offset=0;descriptors=[];locations=[]
 for si,item in enumerate(shards):
  require(si<TASKS and type(item)is dict and set(item)=={'filename','raw_bytes'},'Bounded complete shard bytes')
  raw=item['raw_bytes'];name=f'machine/tasks-{si:05d}.jsonl'
  require(item['filename']==name and type(raw)is bytes and 0<len(raw)<=LIMIT,'Original shard size/name')
  reader=BytesIO(raw);begin=ordinal
  while reader.tell()<len(raw):
   local=reader.tell();line=reader.readline(LIMIT+1)
   require(line.endswith(b'\n') and ordinal<TASKS,'No partial or extra record')
   entry=index['task_index'][ordinal]['jsonl_record']
   for k in ('record_index','byte_start','byte_stop'):integer(entry[k])
   exact(entry,dict(record_index=ordinal,byte_start=global_offset,byte_stop=global_offset+len(line),row_sha256=sha256(line).hexdigest()))
   locations.append(dict(task_ordinal=ordinal,shard_index=si,byte_start=local,byte_stop=reader.tell(),row_sha256=sha256(line).hexdigest()))
   global_offset+=len(line);ordinal+=1
  whole.update(raw);descriptors.append(dict(shard_index=si,filename=name,start_task_ordinal=begin,stop_task_ordinal=ordinal,record_count=ordinal-begin,byte_count=len(raw),sha256=sha256(raw).hexdigest()))
 require(ordinal==TASKS and global_offset==source['byte_count'] and whole.hexdigest()==expected_tasks_reference['sha256'],'Full original stream EOF/hash/extent')
 exact(saved_descriptors,descriptors);exact(saved_task_locations,locations)
 return dict(verified_records=ordinal,verified_bytes=global_offset,verified_sha256=whole.hexdigest(),independent_machine_offsets_and_eof_checked=True,**FLAGS)
