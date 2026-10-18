import itertools,unittest
from pathlib import Path
from copy import deepcopy
from unittest import mock
from scripts import ndx_cash_topup_neighbor_preparation_independent_readback_20261003 as m
from test_ndx_cash_topup_neighbor_preparation_research import fixture

def prepared():
    a=fixture();return m.reconstruct_contract(a['input_row'],a['previous_row'],a['input_reference'],a['previous_reference'])
def shard_fixture():
    p=prepared();stats={};tasks=list(m.expected_tasks(p,stats));raw=b''.join(m.enc(t)+b'\n' for t in tasks);folder=Path('synthetic')
    row=dict(scenario_id='test',contract_sha256=p['contract_sha256'],statistics=stats,shards=[dict(path=str(folder/'tasks-00000.jsonl'),sha256=m.sha(raw),start=0,stop=len(tasks))],old_selected_candidate_index=0,old_feasible_seed_count=2,old_evaluated_point_count=3,**dict.fromkeys(m.OUT_FALSE,False))
    return p,row,raw,folder
class Tests(unittest.TestCase):
    def test_independent_grid_complete_and_source_preserved(self):
        p=prepared();before=deepcopy(p);stats={};tasks=list(m.expected_tasks(p,stats))
        expected=set()
        for seed in ((1,1),(2,1)):
            for x in itertools.product(range(4),repeat=2):
                d=[abs(a-b) for a,b in zip(x,seed)]
                if max(d)==1 and 1<=sum(v>0 for v in d)<=2:expected.add(x)
        expected-={(1,1),(2,1),(0,0)}
        self.assertEqual({tuple(t['identity']['buy_shares'][s] for s in ('A','B')) for t in tasks},expected);self.assertEqual(stats['raw_move_attempt_count'],16);self.assertEqual(stats['unprocessed_move_count'],0);self.assertEqual(p,before)
        self.assertEqual(tasks[0]['first_origin']['moves'],[dict(security_id='A',delta=-1)])
    def test_exact_shard_order_counts_ids_and_permissions(self):
        p,row,raw,folder=shard_fixture();m.verify_shards(p,row,lambda ref:raw,folder)
        for mode in ('order','id','bool','truncated','extra'):
            lines=raw.splitlines();bad=deepcopy(row)
            if mode=='order':lines.reverse()
            elif mode=='id':x=m.decode(lines[0]);x['task_id']='0'*64;lines[0]=m.enc(x)
            elif mode=='bool':bad['shards'][0]['start']=False
            elif mode=='truncated':lines=lines[:-1]
            else:lines.append(lines[0])
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.verify_shards(p,bad,lambda ref:b'\n'.join(lines)+b'\n',folder)
    def test_contract_all_seeds_no_selected_only_and_types(self):
        a=fixture();p=prepared();self.assertEqual(p['contract']['all_feasible_seed_indexes'],[0,1])
        for field in ('feasible','shares'):
            b=deepcopy(a)
            if field=='feasible':b['previous_row']['evaluation']['branches'][0]['evaluated_plans'][0]['feasible']=1
            else:b['previous_row']['domain']['buy_limits']['A']=True
            with self.assertRaises(ValueError):m.reconstruct_contract(b['input_row'],b['previous_row'],b['input_reference'],b['previous_reference'])
    def test_pending_blocks_reads_and_does_not_call_producer(self):
        with mock.patch.object(m,'PREPARATION_SHA',None),mock.patch.object(Path,'read_bytes',side_effect=AssertionError('No live reads')):
            with self.assertRaises(ValueError):m.readback(execute=True)

if __name__=='__main__':unittest.main()
