"""Future H reader metadata gates only; never execute an export or actual readback."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ndx_dated_workbook_extension_independent_readback_20261003 as m


def fixture():
    r=lambda n:m.reference(n,'a'*64)
    refs={'manifest':r('manifest')};inputs={k:r(k)for k in ('index','publication','data_reader')}
    ids=[f'{i:064x}'for i in range(1632)];index={'schema':'SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1','planned_task_count':1632,'task_index':[dict(numerical_task_id=tid,task_ordinal=i)for i,tid in enumerate(ids)]}
    audit=dict(schema='DATED_WORKBOOK_EXTENSION_DATA_INDEPENDENT_READBACK_V1',status='PASS',index_reference=inputs['index'],publication_reference=inputs['publication'],reader_sha256='a'*64)
    false={k:False for k in m.EXPORT_FALSE}
    manifest=dict(schema='DATED_H_WORKBOOK_EXTENSION_EXPORT_V1',status='EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',input_references=inputs,source_hashes={'x':'a'*64},planned_task_count=1632,packaged_task_count=1632,unprocessed_task_count=0,classification_count=101,shared_series_count=4,shared_risk_track_count=2,default_task_id=ids[0],actual_package_bytes_within_50_mib=True,source_eof_verified=True,original_order_preserved=True,rendered_previews_are_not_visual_acceptance=True,expected_cells_are_author_snapshots_not_independent_proof=True,**false)
    pub=dict(schema='DATED_H_WORKBOOK_EXTENSION_PUBLICATION_V1',status='PUBLISHED_EXPORT_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',manifest_reference=refs['manifest'],source_hashes=manifest['source_hashes'],all_package_callbacks_were_pending_until_complete_eof=True,**false)
    return manifest,pub,index,audit,refs,inputs

class Tests(unittest.TestCase):
    def test_future_anchors_reject_before_source_reads(self):
        with tempfile.TemporaryDirectory()as tmp,patch.object(m,'OUTPUT',Path(tmp)/'new'),patch.object(Path,'read_bytes',side_effect=AssertionError('Unexpected source IO')):
            with self.assertRaisesRegex(ValueError,'Pending'):m.readback(execute=True)
            self.assertFalse((Path(tmp)/'new').exists())

    def test_complete_original_domain_and_no_false_final_acceptance(self):
        self.assertEqual(len(m.validate_manifest(*fixture())),1632)
        for change in ('bool','reorder','granted','audit','source'):
            args=list(copy.deepcopy(fixture()));a,p,i,d,r,refs=args
            if change=='bool':a['packaged_task_count']=True
            elif change=='reorder':i['task_index'][0]['task_ordinal']=2
            elif change=='granted':a['visual_acceptance_passed']=True
            elif change=='audit':d['reader_sha256']='b'*64
            else:a['input_references']=copy.deepcopy(a['input_references']);a['input_references']['index']['path']='other'
            with self.subTest(change=change),self.assertRaises(ValueError):m.validate_manifest(*args)

    def test_inventory_exact_scope_and_extra_failure_residue(self):
        with tempfile.TemporaryDirectory()as tmp,patch.object(m,'EXPORT',Path(tmp)):
            root=Path(tmp);(root/'export_manifest.json').write_bytes(b'{}');(root/'publication.json').write_bytes(b'{}');(root/'tasks.jsonl').write_bytes(b'{}\n')
            v={'output_inventory_excludes':['export_manifest.json','publication.json'],'output_inventory':[{'path':'tasks.jsonl','sha256':m.sha(b'{}\n'),'byte_count':3}]}
            self.assertEqual(len(m.output_closure(v)),1)
            (root/'failure.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):m.output_closure(v)
            v['output_inventory'][0]['path']='../foreign'
            with self.assertRaises(ValueError):m.output_closure(v)

    def test_data_receipt_and_machine_exact_types(self):
        refs={k:m.reference(k,'a'*64)for k in ('index','publication','tasks','shared','classification','data_producer','data_reader')}
        i=dict(schema='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1',planned_task_count=1632,projected_task_count=1600,not_supplied_task_count=32,source_hashes={'data_producer':'a'*64},**dict.fromkeys(m.DATA_FALSE,False))
        for key,role in [('task_jsonl_reference','tasks'),('shared_display_reference','shared'),('classification_reference','classification')]:i[key]=copy.deepcopy(refs[role])
        i['task_jsonl_reference'].update(record_count=1632,byte_count=99)
        pub=dict(schema='DATED_WORKBOOK_EXTENSION_DATA_PUBLICATION_V1',status='PUBLISHED_DISPLAY_DATA_NOT_WORKBOOK_DELIVERY',index_reference=refs['index'],source_hashes=copy.deepcopy(i['source_hashes']),**dict.fromkeys(m.DATA_FALSE,False))
        for k in ('task_jsonl_reference','shared_display_reference','classification_reference'):pub[k]=copy.deepcopy(i[k])
        a=dict(schema='DATED_WORKBOOK_EXTENSION_DATA_INDEPENDENT_READBACK_V1',status='PASS',index_reference=refs['index'],publication_reference=refs['publication'],reader_sha256='a'*64,source_hashes={v['path']:v['sha256']for v in refs.values()},detail=dict(planned_tasks=1632,projected_tasks=1600,missing_tasks=32,output_rows=1632),classification_rows_verified=101,verified_jsonl_sha256='a'*64,verified_jsonl_bytes=99,producer_called=False,pure_projection_called=False,**dict.fromkeys(m.DATA_FALSE,False))
        m.validate_data_parents(i,pub,a,refs)
        for key in ('status','source_hashes','task_jsonl_reference','formal_comparison_passed'):
            bad=copy.deepcopy(pub);bad[key]='bad'
            with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):m.validate_data_parents(i,bad,a,refs)
        raw=b'{}\n';loc=dict(task_ordinal=0,shard_index=0,byte_start=0,byte_stop=3,row_sha256=m.sha(raw));desc=dict(shard_index=0,start_task_ordinal=0,stop_task_ordinal=1)
        m.validate_machine_location(loc,desc,0,0,raw)
        for obj,key in ((loc,'shard_index'),(desc,'stop_task_ordinal')):
            old=obj[key];obj[key]=False
            with self.assertRaises(ValueError):m.validate_machine_location(loc,desc,0,0,raw)
            obj[key]=old

    def test_restore_shared_role_cannot_swap_and_missing_sidecars_remain_empty(self):
        roles=('incumbent_integer','incumbent_continuous','STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX');row={'schema':'DATED_WORKBOOK_TASK_EXTENSION_TABLES_V1','series':{},'risk_tracks':{},'source_index':{}};shared={'series':{},'risk':{}}
        for i,role in enumerate(roles):
            sid=str(i)*64;r=m.reference(role,'a'*64);row['source_index'][role]=r;row['series'][role]={'shared_series_id':sid};v={'identity':{'role':role,'source_reference':r},'series':{'source_reference':r,'slots':[]}};shared['series'][sid]=v
            if role.startswith('incumbent'):row['risk_tracks'][role]={'shared_risk_id':sid};shared['risk'][sid]={'identity':v['identity'],'risk':{'source_reference':r,'rows':[]}}
        self.assertEqual(m.restore(row,shared)['series']['incumbent_integer']['slots'],[])
        shared['series']['0'*64]['identity']['role']='wrong'
        with self.assertRaises(ValueError):m.restore(row,shared)
        absent={'schema':'DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1'};chart={'risk_source_index':[],'task_evidence':[],'engine_evidence':[],'task_selector':None,'date_selector':None}
        m.verify_chart_sidecars(chart,[absent]);chart['task_selector']='路径查看!B4'
        with self.assertRaises(ValueError):m.verify_chart_sidecars(chart,[absent])

if __name__=='__main__':unittest.main()
