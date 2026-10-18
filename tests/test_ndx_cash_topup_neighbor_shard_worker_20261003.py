from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile,unittest
from unittest import mock
from scripts import ndx_cash_topup_neighbor_shard_worker_20261003 as w
from backtest import ndx_cash_topup_neighbor_journal_research as journal

def fixture():
    tasks=[dict(task_id=c*64,scenario_candidate_ordinal=i,identity={'buy_shares':{'A':i}}) for i,c in enumerate('ab')]
    prepared={'contract_sha256':'e'*64};d=dict(shard=dict(path='saved.jsonl',sha256='f'*64),global_task_start=0)
    adapter=SimpleNamespace(validate_task=lambda p,t,h:None,evaluation_arguments=lambda p,t:dict(plan=t['identity']),inspect_return=lambda p,t,r:dict(outcome='FEASIBLE' if r['okay'] else 'INFEASIBLE',original_target_stock_weight_l1=None,score_absence_reason='synthetic'))
    return tasks,prepared,d,adapter
class Tests(unittest.TestCase):
    def test_external_first_and_complete_raw_journal_reuse(self):
        tasks,p,d,a=fixture();tasks[0]['task_id']=w.FIRST_ID;calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'shard'
            def evaluate(**args):calls.append(args);return dict(okay=False,complete_raw=['all',1,2,3])
            ref=w._process_shard(folder=folder,tasks=tasks,prepared=p,descriptor=d,context_hash='c'*64,adapter=a,evaluate=evaluate,journal_core=journal,verify=lambda:None,external={w.FIRST_ID:{'audit':'external'}})
            self.assertEqual(len(calls),1);saved=w.decode((folder/'completion.json').read_bytes());self.assertEqual(saved['outcome_counts']['EXTERNALLY_REFERENCED'],1);self.assertEqual(saved['outcome_counts']['INFEASIBLE'],1)
            self.assertIn(b'complete_raw',(folder/'journal.jsonl').read_bytes());self.assertEqual(w._verify_completed(folder,d,'c'*64,[t['task_id'] for t in tasks],journal,{'audit':'external'},p['contract_sha256']),ref)
            saved['outcome_counts']['FEASIBLE']=1;(folder/'completion.json').write_bytes(w.enc(saved))
            with self.assertRaises(ValueError):w._verify_completed(folder,d,'c'*64,[t['task_id'] for t in tasks],journal,{'audit':'external'},p['contract_sha256'])
    def test_exception_stops_and_retains_undispatched(self):
        tasks,p,d,a=fixture();calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'shard'
            def fail(**args):calls.append(1);raise RuntimeError('failure')
            with self.assertRaises(RuntimeError):w._process_shard(folder=folder,tasks=tasks,prepared=p,descriptor=d,context_hash='c'*64,adapter=a,evaluate=fail,journal_core=journal,verify=lambda:None,external={})
            self.assertEqual(calls,[1]);r=w.decode((folder/'failure.json').read_bytes())['recovery'];self.assertEqual(r['tasks'][0]['status'],'EVALUATION_EXCEPTION');self.assertEqual(r['undispatched_task_ids'],['b'*64]);self.assertFalse((folder/'completion.json').exists())
    def test_fsync_started_crash_never_invokes_and_source_drift_raw_kept(self):
        tasks,p,d,a=fixture();calls=[];original=w.os.fsync;counter=[0]
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'shard'
            def sync(fd):
                counter[0]+=1
                if counter[0]==2:raise OSError('after start bytes before sync')
                original(fd)
            with mock.patch.object(w.os,'fsync',side_effect=sync),self.assertRaises(OSError):w._process_shard(folder=folder,tasks=tasks,prepared=p,descriptor=d,context_hash='c'*64,adapter=a,evaluate=lambda **kw:calls.append(1),journal_core=journal,verify=lambda:None,external={})
            self.assertEqual(calls,[]);self.assertEqual(w.decode((folder/'failure.json').read_bytes())['recovery']['tasks'][0]['status'],'UNRESOLVED_DISPATCH')
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'shard'
            with self.assertRaises(ValueError):w._process_shard(folder=folder,tasks=tasks,prepared=p,descriptor=d,context_hash='c'*64,adapter=a,evaluate=lambda **kw:{'okay':True},journal_core=journal,verify=lambda:(_ for _ in ()).throw(ValueError('drift')),external={})
            self.assertTrue((folder/'journal.jsonl').exists());self.assertTrue((folder/'failure.json').exists());self.assertFalse((folder/'completion.json').exists())
    def test_batch_resource_stop_and_explicit_prior_completed_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'out';tasks,p,d,a=fixture();tasks[0]['task_id']=w.FIRST_ID
            cp=root/'contract.json';cp.write_bytes(w.enc(p));cr=w.reference(cp,w.sha(cp.read_bytes()));queue=[]
            for n in range(2):
                selected=tasks if n==0 else [dict(task_id=c*64,scenario_candidate_ordinal=i+2,identity={'buy_shares':{'A':i}}) for i,c in enumerate('de')]
                sp=root/f'shard{n}';sp.write_bytes(b''.join(w.enc(t)+b'\n' for t in selected));queue.append(dict(scenario_index=0,shard_index=n,global_shard_index=n,global_task_start=n*2,global_task_stop=n*2+2,contract_reference=cr,shard=dict(path=str(sp),sha256=w.sha(sp.read_bytes()),start=n*2,stop=n*2+2)))
            calls=[];a.fresh_evaluator=lambda:lambda **kw:(calls.append(kw) or {'okay':True})
            context={'synthetic':True};common=dict(context=context,context_sha256=w.digest(context),sources={},queue=queue,first_started=dict(task=tasks[0],original_contract=p),refs={k:{'synthetic':k} for k in ('first_started','first_raw','first_postcheck','first_audit')})
            def module(path,h):return a if path==w.ADAPTER else journal
            with mock.patch.object(w,'ROOT',root),mock.patch.object(w,'OUTPUT',out),mock.patch.object(w,'load_common',return_value=common),mock.patch.object(w,'load_module',side_effect=module),mock.patch.object(w.shutil,'disk_usage',return_value=SimpleNamespace(free=w.MIN_FREE_BYTES)),mock.patch('builtins.print'):
                first=w.run_batch(execute=True,max_shards=1);r=w.decode(Path(first['path']).read_bytes());self.assertEqual(len(calls),1);self.assertEqual(r['outcome_counts']['EXTERNALLY_REFERENCED'],1);self.assertEqual(r['outcome_counts']['UNDISPATCHED'],301655)
                with self.assertRaises(ValueError):w.run_batch(execute=True,max_shards=1)
                second=w.run_batch(execute=True,max_shards=1,prior_run_reference=first);r=w.decode(Path(second['path']).read_bytes());self.assertEqual(len(calls),3);self.assertEqual(r['outcome_counts']['EXTERNALLY_REFERENCED'],1);self.assertEqual(r['new_completed_shard_count'],1)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'out';cp=root/'contract';cp.write_bytes(w.enc(p));sp=root/'shard';sp.write_bytes(b''.join(w.enc(t)+b'\n' for t in tasks));d=dict(scenario_index=0,shard_index=0,global_shard_index=0,global_task_start=0,global_task_stop=2,contract_reference=w.reference(cp,w.sha(cp.read_bytes())),shard=dict(path=str(sp),sha256=w.sha(sp.read_bytes()),start=0,stop=2));common['queue']=[d]
            with mock.patch.object(w,'OUTPUT',out),mock.patch.object(w,'load_common',return_value=common),mock.patch.object(w,'load_module',side_effect=module),mock.patch.object(w.shutil,'disk_usage',return_value=SimpleNamespace(free=w.MIN_FREE_BYTES-1)):
                stopped=w.decode(Path(w.run_batch(execute=True)['path']).read_bytes());self.assertEqual(stopped['failure']['status'],'RESOURCE_STOP_BEFORE_DISPATCH');self.assertEqual(stopped['outcome_counts']['UNDISPATCHED'],301656);self.assertFalse((out/'scenario-00-shard-00000').exists())

    def test_public_api_explicit_and_budget_types(self):
        with mock.patch.object(w,'load_common',side_effect=AssertionError('No real inputs')):
            for options in ({},{'execute':1},{'execute':True,'max_shards':True},{'execute':True,'max_shards':0}):
                with self.assertRaises(ValueError):w.run_batch(**options)
if __name__=='__main__':unittest.main()
