"""Independent metadata/byte gates for future H reader; synthetic only."""
import copy,importlib.util,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_dated_workbook_extension_independent_readback_20261003 as m
s=importlib.util.spec_from_file_location('h_reader_owner',ROOT/'tests/test_ndx_dated_workbook_extension_independent_readback_20261003.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)

class Review(unittest.TestCase):
    def test_complete_ordinal_and_publication_cannot_gain_authority(self):
        self.assertEqual(len(m.validate_manifest(*f.fixture())),1632)
        for attack in ('initial_bool','ordinal_bool','omit','swap_audit','numeric_authority'):
            args=list(copy.deepcopy(f.fixture()));a,p,i,d,r,refs=args
            if attack=='initial_bool':a['unprocessed_task_count']=False
            elif attack=='ordinal_bool':i['task_index'][0]['task_ordinal']=False
            elif attack=='omit':i['task_index'].pop()
            elif attack=='swap_audit':d['index_reference']={**d['index_reference'],'sha256':'b'*64}
            else:p['formal_comparison_passed']=0
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.validate_manifest(*args)
    def test_machine_snapshot_bytes_have_eof_not_just_self_reported_hash(self):
        with tempfile.TemporaryDirectory()as t:
            p=Path(t)/'cells';raw=b'{"worksheet":"x"}\n';p.write_bytes(raw)
            r=dict(path=str(p),sha256=m.sha(raw),byte_count=len(raw),record_count=1)
            self.assertEqual(list(m.cell_records(r)),[{'worksheet':'x'}])
            for attack in ('truncated','wrong_count','wrong_hash','duplicate'):
                q=copy.deepcopy(r);p.write_bytes(raw)
                if attack=='truncated':p.write_bytes(raw[:-1]);q['sha256']=m.sha(raw[:-1]);q['byte_count']-=1
                elif attack=='wrong_count':q['record_count']=True
                elif attack=='wrong_hash':q['sha256']='f'*64
                else:
                    b=b'{"x":1,"x":2}\n';p.write_bytes(b);q.update(sha256=m.sha(b),byte_count=len(b))
                with self.subTest(attack=attack),self.assertRaises(ValueError):list(m.cell_records(q))
    def test_no_inventory_path_escape_or_late_sidecar(self):
        with tempfile.TemporaryDirectory()as t,patch.object(m,'EXPORT',Path(t)):
            root=Path(t);(root/'export_manifest.json').write_bytes(b'{}');(root/'publication.json').write_bytes(b'{}');(root/'ok').write_bytes(b'x')
            a=dict(output_inventory_excludes=['export_manifest.json','publication.json'],output_inventory=[dict(path='ok',sha256=m.sha(b'x'),byte_count=1)])
            self.assertEqual(len(m.output_closure(a)),1)
            (root/'failure.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):m.output_closure(a)
            (root/'failure.json').unlink();a['output_inventory'][0]['path']='../outside'
            with self.assertRaises(ValueError):m.output_closure(a)

    def test_parent_publication_machine_coordinates_and_failure_namespace(self):
        refs={k:m.reference(k,'a'*64) for k in ('index','publication','tasks','shared','classification','data_producer','data_reader')}
        flags=dict.fromkeys(m.DATA_FALSE,False)
        index=dict(schema='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1',planned_task_count=1632,projected_task_count=3,not_supplied_task_count=1629,source_hashes={'data_producer':'a'*64},**flags)
        for field,key in [('task_jsonl_reference','tasks'),('shared_display_reference','shared'),('classification_reference','classification')]:index[field]=dict(refs[key])
        index['task_jsonl_reference'].update(record_count=1632,byte_count=98)
        pub=dict(schema='DATED_WORKBOOK_EXTENSION_DATA_PUBLICATION_V1',status='PUBLISHED_DISPLAY_DATA_NOT_WORKBOOK_DELIVERY',index_reference=refs['index'],source_hashes=index['source_hashes'],**flags)
        for field in ('task_jsonl_reference','shared_display_reference','classification_reference'):pub[field]=copy.deepcopy(index[field])
        audit=dict(schema='DATED_WORKBOOK_EXTENSION_DATA_INDEPENDENT_READBACK_V1',status='PASS',index_reference=refs['index'],publication_reference=refs['publication'],reader_sha256='a'*64,source_hashes={v['path']:v['sha256'] for v in refs.values()},detail=dict(planned_tasks=1632,projected_tasks=3,missing_tasks=1629,output_rows=1632),classification_rows_verified=101,verified_jsonl_sha256='a'*64,verified_jsonl_bytes=98,producer_called=False,pure_projection_called=False,**flags)
        m.validate_data_parents(index,pub,audit,refs)
        for attack in ('pubref','partial','permission','receipt'):
            i,p,a=copy.deepcopy((index,pub,audit))
            if attack=='pubref':p['index_reference']=m.reference('other','a'*64)
            elif attack=='partial':a['detail']['missing_tasks']=0
            elif attack=='permission':i['point_in_time_verified']=0
            else:p['status']='FAILED'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.validate_data_parents(i,p,a,refs)
        raw=b'{}\n';loc=dict(task_ordinal=1,shard_index=0,byte_start=3,byte_stop=6,row_sha256=m.sha(raw));desc=dict(shard_index=0,start_task_ordinal=0,stop_task_ordinal=2)
        m.validate_machine_location(loc,desc,1,3,raw)
        for field,value in [('shard_index',False),('byte_start',0),('task_ordinal',True),('row_sha256','f'*64)]:
            b={**loc,field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):m.validate_machine_location(b,desc,1,3,raw)
        with tempfile.TemporaryDirectory() as t:
            d=Path(t)/'data';a=Path(t)/'audit';d.mkdir();a.mkdir()
            for name in ('started.json','tasks.jsonl','shared_display.json','classification.json','index.json','publication.json'):(d/name).write_bytes(b'{}')
            (a/'independent_readback.json').write_bytes(b'{}')
            r={'index':{'path':str(d/'index.json')},'audit':{'path':str(a/'independent_readback.json')}}
            m.check_data_namespaces(r);(a/'failure.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):m.check_data_namespaces(r)

if __name__=='__main__':unittest.main()
