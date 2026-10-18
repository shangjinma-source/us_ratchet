import copy,hashlib,importlib.util,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_dated_workbook_extension_tables_research import fixture,classification,classification_fixture,m as core
spec=importlib.util.spec_from_file_location('extension_publisher',Path(__file__).resolve().parents[1]/'scripts/ndx_dated_workbook_extension_data_20261003.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def streams():
    p,c,shared,aggregates=fixture();entries=[]
    for k in range(4,21):
        for kind in ('equal','fixed','anchor'):
            for j in range(32):
                i=len(entries);tid=p['numerical_task_id'] if i==0 else ('%064x'%i)
                entries.append(dict(numerical_task_id=tid,task_ordinal=i,k=k,weight_spec={'kind':kind},status='COMPARISON_NOT_SUPPLIED',jsonl_record=None))
    p['original_task_summary_row']={k:entries[0][k] for k in ('numerical_task_id','k','weight_spec')};c['original_task_summary_row']=copy.deepcopy(p['original_task_summary_row'])
    pb=m.enc(p)+b'\n';cb=m.enc(c)+b'\n';ce=copy.deepcopy(entries)
    for rows,b,status in ((entries,pb,'AUDITED_SAVED_PATHS_PROJECTED'),(ce,cb,'SAVED_CHAIN_DISPLAY_ADDED')):
        rows[0].update(status=status,jsonl_record=dict(record_index=0,byte_start=0,byte_stop=len(b),row_sha256=m.sha(b)))
    def index(rows,b):return dict(planned_task_count=1632,task_index=rows,task_jsonl_reference=dict(path='unused',sha256=m.sha(b),record_count=1,byte_count=len(b)),calendar=p['calendar'],projected_task_count=1,not_supplied_task_count=1631,full_new_cutoff_task_denominator=6222659648236112670)
    return pb,cb,index(entries,pb),index(ce,cb),shared,aggregates

class Tests(unittest.TestCase):
    def test_sparse_full_queue_shared_once_last_retained(self):
        pb,cb,p,c,s,a=streams();emitted=[]
        out=m.stream_display(io.BytesIO(pb),io.BytesIO(cb),p,c,s,a,core,lambda b:emitted.append(b) or {'index':len(emitted)-1})
        self.assertEqual(len(emitted),1632);self.assertEqual(out['not_supplied_task_count'],1631);self.assertEqual(len(out['shared_series']),4);self.assertEqual(len(out['shared_risk']),2)
        row=json.loads(emitted[0]);self.assertNotIn('slots',row['series']['incumbent_integer']);self.assertEqual(len(row['series']['candidate_integer']['slots']),127)
        self.assertEqual(out['task_index'][-1]['task_ordinal'],1631);self.assertEqual(out['package_plan']['task_count'],1632)
    def test_corrupt_offsets_hashes_order_and_pending(self):
        for fault in ('offset','hash','task','tail'):
            pb,cb,p,c,s,a=streams()
            if fault=='offset':c['task_index'][0]['jsonl_record']['byte_stop']+=1
            elif fault=='hash':p['task_jsonl_reference']['sha256']='f'*64
            elif fault=='task':c['task_index'][0]['numerical_task_id']='f'*64
            else:pb+=b'{}\n'
            with self.subTest(fault=fault),self.assertRaises(ValueError):m.stream_display(io.BytesIO(pb),io.BytesIO(cb),p,c,s,a,core,lambda b:{})
        with patch.dict(m.BOUND,{'path_index':('missing',None)}),self.assertRaises(ValueError):m.load()
    def test_publisher_failed_final_guard_keeps_evidence(self):
        pb,cb,p,c,s,a=streams()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pp=root/'p';cp=root/'c';pp.write_bytes(pb);cp.write_bytes(cb);p['task_jsonl_reference']['path']=str(pp);c['task_jsonl_reference']['path']=str(cp)
            docs=dict(path_index=p,chain_index=c,path_shared={'shared_paths':s},chain_shared={'aggregates':a},classification={'coverage':classification.summarize_saved_classification(**classification_fixture()),'source_hashes':{}})
            p['source_hashes']={};c['source_hashes']={};out=root/'out'
            with patch.object(m,'OUTPUT',out),patch.object(m,'load',return_value=(docs,{}, {},core)),patch.object(m,'guard',side_effect=ValueError('source drift')):
                with self.assertRaises(ValueError):m.run(execute=True)
                self.assertTrue((out/'tasks.jsonl').exists());self.assertTrue((out/'failure.json').exists())
                with self.assertRaises(ValueError):m.run(execute=True)
if __name__=='__main__':unittest.main()
