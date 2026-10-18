import copy,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_cash_neighbor_selection_20261003 as m
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ndx_cash_neighbor_selection_research import fixture
from backtest import ndx_cash_neighbor_stream_selection_research as selector


def journal_fixture(stages=None):
    stages=stages or [('TASK_STARTED',{}),('RAW_RETURNED',{'result':False}),('POSTCHECK',{})]
    lines=[];entries=[];offset=0;previous='0'*64
    for i,(stage,payload) in enumerate(stages):
        body=dict(schema='CASH_NEIGHBOR_JOURNAL_RECORD_V1',sequence=i,previous_record_sha256=previous,context_sha256='c'*64,task_id='a'*64,task_position=0,stage=stage,payload=payload)
        row=dict(body,record_sha256=m.digest(body));line=m.enc(row)+b'\n';lines.append(line)
        entries.append(dict(sequence=i,byte_start=offset,byte_stop=offset+len(line),record_sha256=row['record_sha256'],task_id='a'*64,stage=stage));offset+=len(line);previous=row['record_sha256']
    blob=b''.join(lines);reference=m.ref('journal',m.sha(blob));completion=dict(record_index=entries,record_count=len(lines),terminal_record_sha256=previous)
    return blob,reference,completion


def scenario_fixture(root):
    a=fixture();prepared=a['prepared'];t=a['new_records'][0]['task'];record=a['new_records'][0]
    def put(name,obj,raw=False):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);b=obj if raw else m.enc(obj);p.write_bytes(b);return m.ref(p,m.sha(b))
    cr=put('contract.json',prepared);tr=put('tasks.jsonl',m.enc(t)+b'\n',True)
    descriptor=dict(scenario_index=0,shard_index=1,global_shard_index=1,global_task_start=1,global_task_stop=2,shard=dict(tr,start=0,stop=1),contract_reference=cr)
    sr=put('production/started.json',dict(schema='CASH_NEIGHBOR_SHARD_STARTED_V1',descriptor=descriptor,contract_sha256=prepared['contract_sha256'],context_sha256='c'*64,ordered_task_ids=[t['task_id']]))
    stages=[('TASK_STARTED',dict(task_reference=dict(tr,jsonl_line_index=0,scenario_candidate_ordinal=0),global_task_position=1,evaluation_argument_sha256='f'*64)),('RAW_RETURNED',record['raw']),('POSTCHECK',record['postcheck'])]
    blob,jr,c=journal_fixture(stages)
    # Independently rewrite synthetic task ID and chain, preserving byte locators.
    lines=[];entries=[];offset=0;previous='0'*64
    for i,line in enumerate(blob.splitlines()):
        v=json.loads(line);v['task_id']=t['task_id'];v['previous_record_sha256']=previous;v['record_sha256']=m.digest({k:x for k,x in v.items() if k!='record_sha256'});b=m.enc(v)+b'\n';lines.append(b)
        entries.append(dict(sequence=i,byte_start=offset,byte_stop=offset+len(b),record_sha256=v['record_sha256'],task_id=t['task_id'],stage=v['stage']));offset+=len(b);previous=v['record_sha256']
    jr=put('production/journal.jsonl',b''.join(lines),True)
    completion=dict(schema='CASH_NEIGHBOR_SHARD_COMPLETION_V1',status='COMPLETE_SAVED_DIAGNOSTICS_NOT_INDEPENDENTLY_AUDITED',descriptor=descriptor,started_reference=sr,journal_reference=jr,context_sha256='c'*64,task_count=1,record_count=3,record_index=entries,terminal_record_sha256=previous)
    co=put('production/completion.json',completion);fr=m.ref('future_result','d'*64)
    report=dict(schema='CASH_NEIGHBOR_FULL_AUDIT_SHARD_V1',status='PASS',global_shard_index=1,descriptor=descriptor,completion_reference=co,started_reference=sr,journal_reference=jr,result_reference=fr,detail=dict(task_count=1,journal_sha256=jr['sha256'],task_results=record['shard_audit']['document']['detail']['task_results']))
    ar=put('audit.json',report);fa=a['full_audit']['document'];fa['shard_audit_references'][1]=ar;fa['source_hashes']={x['path']:x['sha256'] for x in (co,sr,jr,tr,cr)}
    d=dict(full_audit=fa,full_result=dict(context_sha256='c'*64,completed_shard_references=[{},co]),preparation_audit=dict(source_hashes={tr['path']:tr['sha256']}))
    r=dict(full_result=fr)
    return a,d,r,descriptor,prepared,jr,completion

class Tests(unittest.TestCase):
    def test_pending_pins_before_io_and_namespace(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'anchor'):m.prepare()
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)),patch.object(m,'prepare',side_effect=AssertionError('prepare')):
            with self.assertRaisesRegex(ValueError,'namespace'):m.run(execute=True)

    def test_exact_journal_bytes_order_tail_and_bool(self):
        blob,r,c=journal_fixture();j=m.Journal(io.BytesIO(blob),r,c,'c'*64,['a'*64])
        for stage in ('TASK_STARTED','RAW_RETURNED','POSTCHECK'):j.take(0,stage)
        j.finish()
        for change in ('tail','index','order','boolean'):
            b=blob;v=copy.deepcopy(c)
            if change=='tail':b+=b'junk'
            if change=='index':v['record_index'][0]['byte_stop']+=1
            if change=='boolean':v['record_count']=True
            j=m.Journal(io.BytesIO(b),r,v,'c'*64,['a'*64])
            with self.subTest(change=change),self.assertRaises(ValueError):
                for stage in (('POSTCHECK','RAW_RETURNED','TASK_STARTED') if change=='order' else ('TASK_STARTED','RAW_RETURNED','POSTCHECK')):j.take(0,stage)
                j.finish()

    def test_source_bound_saved_shard_to_stream_selector(self):
        with tempfile.TemporaryDirectory() as temp:
            a,d,r,descriptor,p,jr,c=scenario_fixture(Path(temp));sources={};streamed=set();locator={};emitted=[]
            def emit(row):
                if row['origin']=='NEW':
                    self.assertEqual(locator['task_id'],row['identity']['task_id']);self.assertEqual(locator['raw_record']['source_reference'],jr)
                    self.assertNotIn('json_pointer',row['references']['raw'])
                emitted.append(row)
            args=dict(a,new_records=m.new_records(d,r,[descriptor],p,sources,streamed,locator),emit_ledger_row=emit)
            out=selector.select_scenario_stream(**args)
            self.assertEqual(out['total_candidate_count'],3);self.assertEqual(out['status'],'NEW_PATH_REQUIRED');self.assertEqual(len(emitted),3);self.assertEqual(streamed,{jr['path']})
            Path(jr['path']).write_bytes(Path(jr['path']).read_bytes()+b'garbage')
            with self.assertRaises(ValueError):list(m.new_records(d,r,[descriptor],p,{},set(),{}))

    def test_first_shard_external_report_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            a,d,r,desc,p,jr,c=scenario_fixture(Path(temp));tid=a['new_records'][0]['task']['task_id'];desc.update(global_shard_index=0,global_task_start=0,global_task_stop=1)
            def replace(reference,value):
                blob=m.enc(value);Path(reference['path']).write_bytes(blob);return m.ref(reference['path'],m.sha(blob))
            oldaudit=d['full_audit']['shard_audit_references'][1];report=json.loads(Path(oldaudit['path']).read_bytes());start=json.loads(Path(c['started_reference']['path']).read_bytes());start['descriptor']=desc;c['started_reference']=replace(c['started_reference'],start)
            r.update({k:m.ref(k,'e'*64) for k in ('first_started','first_raw','first_postcheck','first_audit')})
            body=dict(schema='CASH_NEIGHBOR_JOURNAL_RECORD_V1',sequence=0,previous_record_sha256='0'*64,context_sha256='c'*64,task_id=tid,task_position=0,stage='EXTERNAL_REFERENCE',payload={k:r[k] for k in ('first_started','first_raw','first_postcheck','first_audit')})
            rec=dict(body,record_sha256=m.digest(body));blob=m.enc(rec)+b'\n';Path(jr['path']).write_bytes(blob);jr=m.ref(jr['path'],m.sha(blob))
            c.update(descriptor=desc,journal_reference=jr,record_count=1,record_index=[dict(sequence=0,byte_start=0,byte_stop=len(blob),record_sha256=rec['record_sha256'],task_id=tid,stage='EXTERNAL_REFERENCE')],terminal_record_sha256=rec['record_sha256'])
            cr=replace(d['full_result']['completed_shard_references'][1],c);detail=report.pop('detail');detail.update(journal_sha256=jr['sha256']);report.update(detail)
            report.update(schema='CASH_NEIGHBOR_SHARD_INDEPENDENT_READBACK_V1',global_shard_index=0,descriptor=desc,completion_reference=cr,journal_reference=jr,started_reference=c['started_reference'])
            report['source_hashes']={x['path']:x['sha256'] for x in (jr,c['started_reference'],desc['contract_reference'],m.ref(desc['shard']['path'],desc['shard']['sha256']))}
            ar=replace(oldaudit,report);d['full_audit'].update(existing_first_shard_audit_reference=ar,source_hashes={cr['path']:cr['sha256']});d['full_audit']['shard_audit_references'][0]=ar;d['full_result']['completed_shard_references']=[cr];d.update(first_raw={'original':True},first_postcheck={},first_audit={})
            with patch.object(m,'FIRST_ID',tid):
                got=list(m.new_records(d,r,[desc],p,{},set(),{}));self.assertEqual(got[0]['raw'],{'original':True});self.assertEqual(got[0]['references']['raw'],r['first_raw'])

    def test_old_path_reuse_only_original_plan_and_pointer(self):
        a=fixture();old=a['previous_row'];r={k:m.ref(k,'b'*64) for k in ('previous','paired')}
        paired=dict(scenario_id=old['scenario_id'],input_row=copy.deepcopy(old['input_row']),input_reference=old['input_reference'],topup_context={k:v for k,v in old.items() if k not in ('evaluation','closure_records','feasible_scores')},topup_context_reference=m.pointer(r['previous'],'/rows/0'),selected_plan=copy.deepcopy(old['evaluation']['branches'][0]['evaluated_plans'][0]),selected_plan_reference=m.pointer(r['previous'],'/rows/0/evaluation/branches/0/evaluated_plans/0'),paths={'candidate':{}})
        self.assertEqual(m.old_path(old,paired,0,r)['buy_shares'],{'A':1})
        paired['selected_plan']['buy_shares']['A']=99
        with self.assertRaises(ValueError):m.old_path(old,paired,0,r)

    def test_task_canonical_locator_and_streamed_eof_gate(self):
        t=dict(x=False,text='中文');b=m.enc(t)+b'\n';rows=m.tasks_with_locators(b,m.ref('tasks',m.sha(b)));self.assertEqual(rows[0][1]['byte_stop'],len(b));self.assertEqual(rows[0][1]['sha256'],m.sha(b))
        with self.assertRaises(ValueError):m.tasks_with_locators(b[:-1],m.ref('tasks',m.sha(b)))
        r={'previous':m.ref('old','a'*64)};d={'previous_publication':{'source_hashes':{}}};s=dict(complete_document_consumed=True,row_count=40,sha256='a'*64,metadata=dict(schema='OLD_HOLDING_TOPUP_CONDITIONAL_RESEARCH_V1',source_hashes={},point_in_time_verified=False,promotion_allowed=False,orders_executed=False))
        m.streamed_parent_summary(s,'previous',r,d);s['sha256']='b'*64
        with self.assertRaises(ValueError):m.streamed_parent_summary(s,'previous',r,d)

    def test_pending_case_durable_output_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);start=m.save(root/'started.json',{})
            ledger=root/'ledger.jsonl';ledger.write_bytes(b'{}\n');lr=m.ref(ledger,m.sha(b'{}\n'))
            sr=m.save(root/'selection.json',dict(ledger_reference=lr,started_reference=start,consumption_status='PENDING_FINAL_SOURCE_CLOSURE',requires_final_publication=True,ledger_bytes=3,ledger_row_count=1))
            pr=m.save(root/'publication.json',dict(selection_reference=sr,ledger_reference=lr,started_reference=start,status='PENDING_FINAL_SOURCE_CLOSURE',requires_final_publication=True))
            entries=[dict(selection_reference=sr,publication_reference=pr,ledger_reference=lr,ledger_row_count=1)]
            m.verify_case_outputs(entries);ledger.write_bytes(b'[]\n')
            with self.assertRaisesRegex(ValueError,'ledger bytes'):m.verify_case_outputs(entries)

    def test_failure_prefix_retained_no_retry(self):
        class Empty:
            def __init__(self,f):pass
            def __iter__(self):return self
            def __next__(self):raise StopIteration
            @property
            def summary(self):raise ValueError('EOF hash rejected')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);old=root/'old';old.write_bytes(b'{}');out=root/'out';refs={'previous':m.ref(old,m.sha(b'{}')),'paired':m.ref(old,m.sha(b'{}'))}
            with patch.object(m,'OUTPUT',out),patch.object(m,'prepare',return_value=({},refs,[],{}, {'json_stream':type('Module',(),{'JsonRowsStream':Empty})})):
                with self.assertRaisesRegex(ValueError,'EOF hash'):m.run(execute=True)
                self.assertEqual({x.name for x in out.iterdir()},{'started.json','failure.json'})
                with self.assertRaisesRegex(ValueError,'namespace'):m.run(execute=True)

if __name__=='__main__':unittest.main()

