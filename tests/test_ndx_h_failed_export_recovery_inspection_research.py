from copy import deepcopy
from hashlib import sha256
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import json
import unittest
from backtest import ndx_h_failed_export_recovery_inspection_research as m

def ref(name,raw=b'original'):return dict(path='D:/synthetic/'+name,sha256=sha256(raw).hexdigest())
def fixture():
 lines=[('原值'+str(i)+'\n').encode() for i in range(1632)];raw=b''.join(lines);r=ref('tasks.jsonl',raw);rows=[];offset=0
 for i,line in enumerate(lines):
  rows.append(dict(task_ordinal=i,numerical_task_id=sha256(str(i).encode()).hexdigest(),status='DISPLAY_PROJECTED',jsonl_record=dict(record_index=i,byte_start=offset,byte_stop=offset+len(line),row_sha256=sha256(line).hexdigest())));offset+=len(line)
 index=dict(schema='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1',planned_task_count=1632,task_index=rows,task_jsonl_reference=dict(r,record_count=1632,byte_count=len(raw)))
 return index,r,lines

class Tests(unittest.TestCase):
 def test_failed_parent_is_not_successful_parent(self):
  index,_,_=fixture();flags=dict.fromkeys(m.PARENT_FALSE,False)
  failure=dict(schema='DATED_H_WORKBOOK_EXTENSION_FAILURE_V1',status='FAILED_DO_NOT_CONSUME',retry_allowed=False,stream_completed=True,all_attempts_retained=True,error='Full ordered task link cells',**flags)
  started=dict(schema='DATED_H_WORKBOOK_EXTENSION_STARTED_V1',default_task_id=index['task_index'][0]['numerical_task_id'],**flags)
  refs={k:ref(v)for k,v in [('failure','failure.json'),('started','started.json'),('index_copy','sources/index.json')]}
  inventory=[dict(path=v['path'].removeprefix('D:/synthetic/'),sha256=v['sha256'],byte_count=8)for v in refs.values()]
  a=dict(failure=failure,started=started,parent_inventory=inventory,parent_root='D:/synthetic',parent_references=refs,index=index)
  self.assertFalse(m.inspect_failed_parent(**a)['prior_successful_publication_claimed'])
  for attack in ('status','permission','publication','ref'):
   b=deepcopy(a)
   if attack=='status':b['failure']['status']='PASS'
   elif attack=='permission':b['started']['visual_acceptance_passed']=0
   elif attack=='publication':b['parent_inventory'].append(dict(path='publication.json',sha256='f'*64,byte_count=1))
   else:b['parent_references']['failure']['path']='D:/elsewhere/failure.json'
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_failed_parent(**b)

 def test_277_packages_44_repairs_233_copies_and_1632_links(self):
  index,_,_=fixture();parents=[];outputs=[];start=0
  sizes=[1]*44+[7]*190+[6]*43
  for i,n in enumerate(sizes):
   p=dict(package_index=i,filename=f'package-{i+1:04d}.xlsx',start_task_ordinal=start,stop_task_ordinal=start+n,task_ids=[r['numerical_task_id']for r in index['task_index'][start:start+n]],action=m.REPAIR if n==1 else m.COPY,original_workbook_reference=ref(f'old/package-{i+1:04d}.xlsx'),pending_reference=ref(f'old/pending{i}.json'),byte_count=8)
   q=deepcopy(p);q.update(workbook_reference=ref(p['filename']),sha256=p['original_workbook_reference']['sha256'])
   if n==1:q['repair_evidence_reference']=ref(f'repair{i}.json')
   parents.append(p);outputs.append(q);start+=n
  out=m.inspect_package_partition(index=index,parent_packages=parents,packages=outputs)
  self.assertEqual((out['package_count'],out['repaired_package_count'],out['copied_package_count']),(277,44,233))
  self.assertEqual(out['native_links'][-1],dict(worksheet='全部任务',cell='H1633',target='package-0277.xlsx',location="'任务索引'!A7"))
  nav=dict(native_links=deepcopy(out['native_links']),charts=[])
  self.assertEqual(m.inspect_navigation_links(workbook=nav,expected_links=out['native_links'])['native_links_verified'],1632)
  nav['native_links'][0]['worksheet']='????'
  with self.assertRaises(ValueError):m.inspect_navigation_links(workbook=nav,expected_links=out['native_links'])
  bad=deepcopy(outputs);bad[44]['sha256']='0'*64;bad[44]['workbook_reference']['sha256']='0'*64
  with self.assertRaises(ValueError):m.inspect_package_partition(index=index,parent_packages=parents,packages=bad)
  with self.assertRaises(ValueError):m.inspect_package_partition(index=index,parent_packages=parents,packages=outputs[:-1])
  forged=deepcopy(parents);forged_new=deepcopy(outputs);forged[0]['action']=forged_new[0]['action']=m.COPY
  with self.assertRaises(ValueError):m.inspect_package_partition(index=index,parent_packages=forged,packages=forged_new)
  for status in ('FOREIGN','COMPARISON_NOT_SUPPLIED'):
   changed_index=deepcopy(index);changed_index['task_index'][45]['status']=status
   with self.assertRaises(ValueError):m.inspect_package_partition(index=changed_index,parent_packages=parents,packages=outputs)
  self.assertTrue(m.inspect_copy_bytes(original_bytes=b'original',recovered_bytes=b'original',original_reference=ref('old'),recovered_reference=ref('new'))['original_bytes_preserved'])
  with self.assertRaises(ValueError):m.inspect_copy_bytes(original_bytes=b'original',recovered_bytes=b'changed',original_reference=ref('old'),recovered_reference=ref('new',b'changed'))

 def test_singleton_only_exact_B5_delta_and_full_capture(self):
  tid='a'*64;oldf,newf=m.label_formulas()
  old=dict(worksheet='路径查看',start_row_zero_based=4,start_column_zero_based=0,row_count=1,column_count=3,values=[['unchanged','#VALUE!',0]],formulas=[[None,oldf,None]])
  new=deepcopy(old);new['values'][0][1]='ID: '+tid;new['formulas'][0][1]=newf
  self.assertEqual(m.inspect_singleton_delta(old_capture=[old],new_capture=[new],task_id=tid)['checked_cells'],3)
  for attack in ('other','formula','truncated','duplicate'):
   bad=deepcopy(new)
   if attack=='other':bad['values'][0][2]=False
   elif attack=='formula':bad['formulas'][0][1]=oldf
   elif attack=='truncated':bad['values'][0].pop()
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_singleton_delta(old_capture=[old,old]if attack=='duplicate'else[old],new_capture=[bad,bad]if attack=='duplicate'else[bad],task_id=tid)

 def test_independent_machine_offsets_hash_partial_and_types(self):
  index,r,lines=fixture();descriptors=[];locations=[];shards=[];ordinal=0
  for i,begin in enumerate(range(0,1632,17)):
   part=lines[begin:begin+17];raw=b''.join(part);name=f'machine/tasks-{i:05d}.jsonl';shards.append(dict(filename=name,raw_bytes=raw));local=0
   for line in part:
    locations.append(dict(task_ordinal=ordinal,shard_index=i,byte_start=local,byte_stop=local+len(line),row_sha256=sha256(line).hexdigest()));ordinal+=1;local+=len(line)
   descriptors.append(dict(shard_index=i,filename=name,start_task_ordinal=begin,stop_task_ordinal=ordinal,record_count=len(part),byte_count=len(raw),sha256=sha256(raw).hexdigest()))
  a=dict(index=index,shards=iter(shards),expected_tasks_reference=r,saved_descriptors=descriptors,saved_task_locations=locations)
  self.assertEqual(m.inspect_machine_stream(**a)['verified_records'],1632)
  for attack in ('offset','bool','partial','extra'):
   loc=deepcopy(locations);bs=deepcopy(shards)
   if attack=='offset':loc[17]['byte_start']=index['task_index'][17]['jsonl_record']['byte_start']
   elif attack=='bool':loc[0]['byte_start']=False
   elif attack=='partial':bs[-1]['raw_bytes']=bs[-1]['raw_bytes'][:-1]
   else:bs[-1]['raw_bytes']+=b'extra\n'
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_machine_stream(index=index,shards=iter(bs),expected_tasks_reference=r,saved_descriptors=descriptors,saved_task_locations=loc)

 def test_repaired_graph_uses_frozen_tables_and_all_other_formulas(self):
  from test_ndx_h_workbook_export_inspection_research import source_fixture
  days=[];d=date(2026,1,1)
  while len(days)<127:
   if d.weekday()<5:days.append(d.isoformat())
   d+=timedelta(days=1)
  with patch.object(Path,'read_text',return_value=json.dumps([dict(calendar=days)])):w,t=source_fixture()
  core=m.zip_core;detail=core.inspect_saved_source_tables(w,[t],[t['numerical_task_id']]);g=core.static_graph_contract(1,detail)
  w['sheets']['路径查看']={};w['sheets']['风险查看']={}
  for (sheet,a),v in g['literals'].items():w['sheets'][sheet][a]=dict(kind='n'if type(v)is int else'str',value=Decimal(v)if type(v)is int else v,formula=None)
  for (sheet,a),v in g['formulas'].items():w['sheets'][sheet][a]=dict(kind='n',value=None,formula=v)
  w['charts']=[dict(c,part=f'xl/charts/chart{i+1}.xml')for i,c in enumerate(g['charts'])]
  w['validations']={s:[dict(sqref='B4',type='whole',operator='between',formula1='1',formula2=str(n))]for s,n in [('路径查看',1),('风险查看',127)]}
  w['sheets']['路径查看']['B5'].update(kind='str',formula=m.label_formulas()[1][1:],value='ID: '+t['numerical_task_id'])
  before=deepcopy(w);self.assertEqual(m.inspect_repaired_graph(workbook=w,tasks=[t],task_ids=[t['numerical_task_id']])['only_formula_delta'],'路径查看!B5');self.assertEqual(w,before)
  w['charts'][0]['series'][0]['formula']='路径查看!Z49:Z175'
  with self.assertRaises(ValueError):m.inspect_repaired_graph(workbook=w,tasks=[t],task_ids=[t['numerical_task_id']])

if __name__=='__main__':unittest.main()
