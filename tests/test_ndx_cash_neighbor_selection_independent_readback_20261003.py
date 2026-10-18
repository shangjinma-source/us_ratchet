import copy
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ndx_cash_neighbor_selection_independent_readback_20261003 as m

def fixture(new_better=False):
    r=lambda name:dict(path=name,sha256='a'*64)
    contract=dict(rule='SINGLE_PAIR_PLUS_MINUS_ONE',conditional_research_buy_ids=['A'],saved_buy_limits={'A':5},old_evaluated_points=[dict(candidate_index=i,buy_shares={'A':i},saved_feasible=i==1,reference=dict(r('old'),json_pointer=f'/rows/0/evaluation/branches/0/evaluated_plans/{i}')) for i in range(2)],original_selected_candidate_index=1)
    rows=[]
    for i in range(3):
        plan=dict(buy_shares={'A':i},feasible=i>0,fees_usd='0.1',supplied_plan_index=i if i<2 else 0)
        score=None if i==0 else dict(distance=dict(numerator=1 if i==1 or new_better else 2,denominator=3 if i==1 else 6),fees_usd=dict(numerator=1,denominator=10))
        if i<2:
            identity={'old_candidate_index':i};refs={'plan':contract['old_evaluated_points'][i]['reference']}
            loc=dict(source_reference=r('old'),byte_start=0,byte_stop=1,row_sha256='b'*64,row_index=0,json_pointer_within_selected_row=f'/evaluation/branches/0/evaluated_plans/{i}')
        else:
            inner=dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1',rule=contract['rule'],scenario_contract_sha256=m.sha(m.enc(contract)),buy_shares={'A':2})
            identity=dict(task_id=m.sha(m.enc(inner)),identity=inner,scenario_candidate_ordinal=0,scenario_id='case');refs={k:r(k) for k in ('task','raw','postcheck','shard_audit')};refs['single_audit']=None
            loc=dict(task_id=identity['task_id'])
        row=dict(merged_candidate_index=i,origin='OLD' if i<2 else 'NEW',identity=identity,buy_shares=plan['buy_shares'],feasible=plan['feasible'],saved_score=score,references=refs,saved_plan=plan)
        rows.append(dict(selection_ledger_row=row,source_locator=loc))
    blob=b''.join(m.enc(x)+b'\n' for x in rows);lr=m.ref('ledger',m.sha(blob))
    path=dict(reference=dict(r('paired'),json_pointer='/rows/0/paths/candidate'),scenario_id='case',selected_candidate_index=1,buy_shares={'A':1})
    status='NEW_PATH_REQUIRED' if new_better else 'REUSE_EXISTING_PAIRED_PATH'
    s=dict(parent_policy_source_sha256='7c44c7fcedd298bb75eed2e9e94cd5587bff31cb0771947a7b540683e21a3879',schema='CASH_NEIGHBOR_STREAM_SCENARIO_SELECTION_V1',scenario_id='case',tie_policy=m.POLICY,contract_sha256=m.sha(m.enc(contract)),old_candidate_count=2,new_candidate_count=1,total_candidate_count=3,feasible_candidate_count=2,ledger_emitted_row_count=3,ledger_storage_external=True,ledger_emitter_source_authenticated=False,emitted_prefix_valid_only_after_successful_return=True,selection_performed=True,scope='BEST_IN_COMPLETE_DECLARED_UNION_NOT_GLOBAL_OPTIMUM',selected=rows[2 if new_better else 1]['selection_ledger_row'],old_selected_path=path,status=status,reused_path_reference=None if new_better else path['reference'],**{k:False for k in m.PURE_FALSE})
    selection=dict(scenario_index=0,schema='CASH_NEIGHBOR_SOURCE_BOUND_CASE_SELECTION_V1',selection=s,consumption_status='PENDING_FINAL_SOURCE_CLOSURE',requires_final_publication=True,ledger_reference=lr,ledger_bytes=len(blob),ledger_row_count=3,**m.FLAGS)
    entry=dict(scenario_index=0,scenario_id='case',ledger_reference=lr,ledger_row_count=3,status=status)
    return blob,selection,entry,contract,rows

class Tests(unittest.TestCase):
    def test_exact_fraction_tie_old_first_and_new_minimum(self):
        for new in (False,True):
            b,s,e,c,rows=fixture(new);out=m.inspect_case(io.BytesIO(b),s,e,c)
            self.assertEqual(out['selected_merged_candidate_index'],2 if new else 1)
            self.assertEqual(out['total_candidate_count'],3)
    def test_resealed_bad_winner_bool_and_missing_prefix_rejected(self):
        for change in ('winner','bool','missing','extra','grant'):
            b,s,e,c,rows=fixture()
            if change=='winner':s['selection']['selected']=rows[2]['selection_ledger_row']
            elif change=='bool':s['selection']['new_candidate_count']=True
            elif change=='missing':b=b[:b.rfind(b'\n',0,-1)+1]
            elif change=='extra':b+=m.enc(rows[0])+b'\n'
            else:s['orders_executed']=True
            with self.subTest(change=change),self.assertRaises(ValueError):m.inspect_case(io.BytesIO(b),s,e,c)
    def test_evidence_spans_preserve_original_bytes_and_reject_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'raw';b=b'{"x":0}';p.write_bytes(b);r=m.ref(p,m.sha(b));loc=dict(source_reference=r,byte_start=0,byte_stop=len(b),sha256=m.sha(b))
            ev=m.Evidence({str(p):r['sha256']})
            try:
                self.assertEqual(ev.span(loc),{'x':0})
                altered=copy.deepcopy(loc);altered['sha256']='0'*64
                with self.assertRaises(ValueError):ev.span(altered)
                altered=copy.deepcopy(loc);altered['byte_start']=False
                with self.assertRaises(ValueError):ev.span(altered)
            finally:ev.close()
    def test_incremental_rows_eof_hash_and_late_tail_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'source';doc={'before':'x'*65530,'rows':[{'a':0},{'b':'中文'*40000}],'after':False};blob=m.enc(doc);p.write_bytes(blob)
            self.assertEqual(list(m.iter_json_rows(m.ref(p,m.sha(blob)))),doc['rows'])
            p.write_bytes(blob+b' garbage');it=m.iter_json_rows(m.ref(p,m.sha(blob+b' garbage')))
            self.assertEqual(next(it),doc['rows'][0]);self.assertEqual(next(it),doc['rows'][1])
            with self.assertRaises(ValueError):next(it)
            p.write_bytes(b'{"rows":[],}')
            with self.assertRaises(ValueError):list(m.iter_json_rows(m.ref(p,m.sha(p.read_bytes()))))

    def test_pending_before_io_no_selector_import(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'never'),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'SHA'):m.readback(execute=True)
        text=Path(m.__file__).read_text(encoding='utf-8-sig')
        self.assertNotIn('import ndx_cash_neighbor_selection',text)
        self.assertNotIn('select_scenario_stream(',text)

if __name__=='__main__':unittest.main()
