import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_h_failed_export_recovery_independent_readback_v2_20261008 as r


def package_fixture(root):
 inventory={};documents={};ids=[f'{i:064x}'for i in range(1632)];flags=dict.fromkeys(r.EXPORT_FALSE,False)
 def put(name,value=None,size=10):
  inventory[name]=dict(path=name,sha256='a'*64,byte_count=size)
  if value is not None:documents[name]=value
  return r.reference(root/name,'a'*64)
 index=dict(schema='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1',planned_task_count=1632,task_index=[dict(task_ordinal=i,numerical_task_id=t,status='DISPLAY_PROJECTED')for i,t in enumerate(ids)])
 cursor=0
 for i,n in enumerate([1]*44+[7]*190+[6]*43):
  base=f'attempts/attempt-{i:05d}';identity=dict(attempt_index=i,start_task_ordinal=cursor,stop_task_ordinal=cursor+n,task_ids=ids[cursor:cursor+n]);cursor+=n
  p=dict(schema='DATED_H_EXPORT_ATTEMPT_V1',status='PENDING_COMPLETE_STREAM_AND_SOURCE_PUBLICATION',**identity,bytes=10,sha256='a'*64,reference=put(base+'/artifact.xlsx'),expected_cells_reference=put(base+'/expected_cells.jsonl'),chart_source_index_reference=put(base+'/chart_source_index.json'),previews=[dict(**put(base+f'/preview-{j}.png'),worksheet=w,range=a)for j,(w,a)in enumerate([('路径查看','A1:G46'),('风险查看','A1:N43')])],costs=dict(missing=False,taskCount=n,taskIds=identity['task_ids'],dataRows=100),**flags)
  put(base+'/pending.json',p);put(base+'/started.json',dict(status='PENDING_EXPORT_ATTEMPT',**identity,**flags));put(f'package-{i+1:04d}.xlsx')
 return index,inventory,documents

class Tests(unittest.TestCase):
 def test_pending_before_io_and_private_authenticated_inspector_injection(self):
  pending=copy.deepcopy(r.BOUND);pending['manifest']=(pending['manifest'][0],None)
  with patch.object(r,'BOUND',pending),patch.object(r,'guard',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):r.readback(execute=True)
  refs={k:r.reference(*r.BOUND[k])for k in ('inspection','zip_core')}
  core,z=r.compile_inspectors(refs)
  self.assertIs(core.zip_core,z)
  self.assertEqual(core.label_formulas()[1],"=IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<=1),'任务索引'!$B$2,NA()),NA())")
  bad=copy.deepcopy(refs);bad['zip_core']['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'Consumed same bytes'):r.compile_inspectors(bad)

 def test_original_277_pending_mapping_44_repair_not_self_reported_plan(self):
  root=Path('D:/synthetic/failed');index,inventory,docs=package_fixture(root)
  with patch.object(r,'PARENT',root):
   packages,oversize=r.reconstruct_packages(index,inventory,docs.__getitem__)
   self.assertEqual((len(packages),sum(p['action'].startswith('REBUILD')for p in packages),len(oversize)),(277,44,0))
   self.assertEqual(packages[-1]['stop_task_ordinal'],1632)
   for change in ('flag','slice','size','preview','missing'):
    d=copy.deepcopy(docs);inv=copy.deepcopy(inventory);p=d['attempts/attempt-00000/pending.json']
    if change=='flag':p['point_in_time_verified']=0
    elif change=='slice':p['stop_task_ordinal']=2
    elif change=='size':inv['package-0001.xlsx']['byte_count']=11
    elif change=='preview':p['previews'][0]['worksheet']='错误'
    else:p['costs']['missing']=True
    with self.subTest(change=change),self.assertRaises(ValueError):r.reconstruct_packages(index,inv,d.__getitem__)

 def test_physical_inventory_same_bytes_and_undeclared_output(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);p=root/'文件.json';raw=b'{"x":6222659648236112670}';p.write_bytes(raw)
   rows=[dict(path=p.name,sha256=r.sha(raw),byte_count=len(raw))]
   sources=r.inventory_map(root,rows);r.guard(sources)
   self.assertEqual(r.read(r.reference(p,r.sha(raw)))['x'],6222659648236112670)
   (root/'failure.json').write_text('{}')
   with self.assertRaises(ValueError):r.inventory_map(root,rows)
   for name in ('../x','/x','A//x','x:stream','x.','x '):
    with self.subTest(name=name),self.assertRaises(ValueError):r.relative(name)

 def test_failed_parent_publication_scope_typed_counts_and_source_closure(self):
  ref=lambda n:r.reference(Path('D:/synthetic')/n,'a'*64)
  refs={'manifest':ref('manifest')};inputs={'failure':ref('failure'),'started':ref('start')};sources={'D:/x':'a'*64}
  flags=dict.fromkeys(r.EXPORT_FALSE,False);flags.update(source_bytes_authenticated=False,native_excel_open_verified=False)
  m=dict(schema='DATED_H_FAILED_EXPORT_RECOVERY_V1',status='RECOVERED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',source_hashes=sources,input_references=inputs,parent_failure_reference=inputs['failure'],parent_started_reference=inputs['started'],parent_status='FAILED_DO_NOT_CONSUME',old_publication_existed=False,recovery_is_new_attempt=True,planned_task_count=1632,packaged_task_count=1632,unprocessed_task_count=0,output_inventory_excludes=['export_manifest.json','publication.json'],**flags)
  p=dict(schema='DATED_H_FAILED_EXPORT_RECOVERY_PUBLICATION_V1',status='PUBLISHED_RECOVERY_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',manifest_reference=refs['manifest'],source_hashes=sources,**flags)
  r.validate_publication(m,p,refs,inputs,sources)
  for key,value in [('parent_status','PASS'),('old_publication_existed',0),('unprocessed_task_count',False),('visual_acceptance_passed',0),('source_hashes',{})]:
   bad=copy.deepcopy(m);bad[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):r.validate_publication(bad,p,refs,inputs,sources)

if __name__=='__main__':unittest.main()
