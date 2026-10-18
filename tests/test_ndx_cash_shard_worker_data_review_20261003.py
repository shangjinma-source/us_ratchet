from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_cash_topup_neighbor_shard_worker_20261003 as w
from backtest import ndx_cash_topup_neighbor_journal_research as journal
from test_ndx_cash_topup_neighbor_shard_worker_20261003 import fixture


def common_fixture(root):
    tasks,prepared,_,adapter=fixture();tasks[0]['task_id']=w.FIRST_ID
    contract=root/'contract.json';contract.write_bytes(w.enc(prepared))
    shard=root/'tasks.jsonl';shard.write_bytes(b''.join(w.enc(t)+b'\n' for t in tasks))
    descriptor=dict(scenario_index=0,shard_index=0,global_shard_index=0,global_task_start=0,global_task_stop=2,
        contract_reference=w.reference(contract,w.sha(contract.read_bytes())),
        shard=dict(path=str(shard),sha256=w.sha(shard.read_bytes()),start=0,stop=2))
    calls=[]
    adapter.fresh_evaluator=lambda:lambda **kwargs:(calls.append(kwargs) or {'okay':True})
    context=dict(synthetic=True)
    common=dict(preparation={},queue=[descriptor],context=context,context_sha256=w.digest(context),sources={},
        refs={k:w.reference(p,h) for k,(p,h) in w.BOUND.items()},first_started=dict(task=tasks[0],original_contract=prepared))
    return common,adapter,calls


class Tests(unittest.TestCase):
    def test_every_dispatch_has_durable_started_before_call_and_full_raw(self):
        tasks,p,d,a=fixture();sync_count=[0];before_calls=[];oldsync=w.os.fsync
        def sync(fd):sync_count[0]+=1;return oldsync(fd)
        def evaluate(**kwargs):before_calls.append(sync_count[0]);return {'okay':True,'full_payload':[1,0,{'not_removed':False}]}
        with tempfile.TemporaryDirectory() as tmp,patch.object(w.os,'fsync',side_effect=sync):
            folder=Path(tmp)/'shard'
            w._process_shard(folder=folder,tasks=tasks,prepared=p,descriptor=d,context_hash='c'*64,adapter=a,evaluate=evaluate,journal_core=journal,verify=lambda:None,external={})
            self.assertEqual(before_calls,[2,5]);self.assertEqual(sync_count[0],8)
            rows=[w.decode(x) for x in (folder/'journal.jsonl').read_bytes().splitlines()]
            self.assertEqual([r['stage'] for r in rows],['TASK_STARTED','RAW_RETURNED','POSTCHECK']*2)
            self.assertEqual(rows[1]['payload']['result']['full_payload'],[1,0,{'not_removed':False}])

    def test_raw_only_and_torn_next_start_never_become_completed(self):
        ids=['a'*64,'b'*64];records=[];previous=journal.ZERO
        for stage,payload in [('TASK_STARTED',{}),('RAW_RETURNED',{'result':{'saved':True},'error':None,'explicit_evaluator_call_attempt_count':1,'returned_evaluation_count':1})]:
            row=journal.make_record(sequence=len(records),previous_hash=previous,context_sha256='c'*64,task_id=ids[0],task_position=0,stage=stage,payload=payload)
            records.append(w.enc(row)+b'\n');previous=row['record_sha256']
        raw=b''.join(records)+b'{"partial":"never overwritten'
        result=journal.inspect_journal(raw,context_sha256='c'*64,ordered_task_ids=ids)
        self.assertFalse(result['complete']);self.assertEqual(result['tasks'][0]['status'],'RAW_SAVED_POSTCHECK_MISSING')
        self.assertEqual(result['tail']['sha256'],w.sha(raw[result['valid_prefix_byte_count']:]))
        self.assertFalse(result['recovery_calls_evaluator']);self.assertFalse(result['tail_truncated_or_overwritten'])

    def test_resource_stop_does_not_relabel_saved_first_as_undispatched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);common,adapter,calls=common_fixture(root)
            with patch.object(w,'OUTPUT',root/'out'),patch.object(w,'load_common',return_value=common),patch.object(w,'guard'),patch.object(w,'load_module',side_effect=lambda p,h:adapter if p==w.ADAPTER else journal),patch.object(w.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                ref=w.run_batch(execute=True,max_shards=1);result=w.decode(Path(ref['path']).read_bytes())
            self.assertEqual(calls,[]);self.assertEqual(result['failure']['status'],'RESOURCE_STOP_BEFORE_DISPATCH')
            self.assertEqual(result['outcome_counts']['EXTERNALLY_REFERENCED'],1)
            self.assertEqual(result['outcome_counts']['UNDISPATCHED'],301656)
            self.assertEqual(sum(result['outcome_counts'].values()),301657)

    def test_resume_requires_external_result_anchor_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);common,adapter,calls=common_fixture(root);out=root/'out';out.mkdir()
            with patch.object(w,'OUTPUT',out),patch.object(w,'load_common',return_value=common),patch.object(w,'guard'),patch.object(w,'load_module') as module:
                with self.assertRaisesRegex(ValueError,'external anchor'):w.run_batch(execute=True,max_shards=1)
                module.assert_not_called()
            self.assertEqual(calls,[])

    def test_result_publication_drift_keeps_failure_and_blocks_continuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);common,adapter,calls=common_fixture(root);out=root/'out'
            def guard(_):
                if out.exists() and list(out.glob('request-*/result.json')):raise ValueError('postwrite drift')
            with patch.object(w,'OUTPUT',out),patch.object(w,'load_common',return_value=common),patch.object(w,'guard',side_effect=guard),patch.object(w,'load_module',side_effect=lambda p,h:adapter if p==w.ADAPTER else journal),patch.object(w.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(ValueError,'postwrite drift'):w.run_batch(execute=True,max_shards=1)
            result_path=next(out.glob('request-*/result.json'));self.assertTrue((result_path.parent/'failure.json').exists())
            ref=w.reference(result_path,w.sha(result_path.read_bytes()))
            with patch.object(w,'OUTPUT',out),patch.object(w,'load_common',return_value=common),patch.object(w,'guard'),patch.object(w,'load_module') as module:
                with self.assertRaisesRegex(ValueError,'residue'):w.run_batch(execute=True,max_shards=1,prior_run_reference=ref)
                module.assert_not_called()
            self.assertEqual(calls,[])

    def test_completed_shard_binds_contract_and_cannot_relabel_first_as_new(self):
        tasks,p,d,a=fixture();tasks[0]['task_id']=w.FIRST_ID
        external={k:w.reference(path,h) for k,(path,h) in w.BOUND.items() if k.startswith('first_')}
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'good'
            w._process_shard(folder=folder,tasks=tasks,prepared=p,descriptor=d,context_hash='c'*64,adapter=a,evaluate=lambda **kw:{'okay':True},journal_core=journal,verify=lambda:None,external={w.FIRST_ID:external})
            args=(folder,d,'c'*64,[t['task_id'] for t in tasks],journal,external,p['contract_sha256'])
            w._verify_completed(*args)
            started=w.decode((folder/'started.json').read_bytes());started['contract_sha256']='f'*64
            (folder/'started.json').write_bytes(w.enc(started));completion=w.decode((folder/'completion.json').read_bytes())
            completion['started_reference']['sha256']=w.sha((folder/'started.json').read_bytes());(folder/'completion.json').write_bytes(w.enc(completion))
            with self.assertRaises(ValueError):w._verify_completed(*args)
            bad=Path(tmp)/'bad'
            with patch.object(w,'ROOT',Path(tmp)):
                w._process_shard(folder=bad,tasks=tasks,prepared=p,descriptor=d,context_hash='c'*64,adapter=a,evaluate=lambda **kw:{'okay':True},journal_core=journal,verify=lambda:None,external={})
            with self.assertRaises(ValueError):w._verify_completed(bad,d,'c'*64,[t['task_id'] for t in tasks],journal,external,p['contract_sha256'])


if __name__=='__main__':unittest.main()
