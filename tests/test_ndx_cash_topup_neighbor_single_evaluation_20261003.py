from copy import deepcopy
from decimal import Inexact, localcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_cash_topup_neighbor_single_evaluation_20261003 as w
from backtest import ndx_cash_topup_neighbor_preparation_research as prep


def fixture():
    row = dict(scenario_id='synthetic', branch_role='MAIN_LANE', target_l1_applicable=True, zero_buy_only=False,
        cash_event=dict(decision_date='2023-04-28', execution_date='2023-05-01', amount_usd='100'),
        starting_cash_usd='100', holdings={s:10 for s in 'ABCD'}, execution_prices={s:'10' for s in 'ABCD'},
        securities={s:dict(issuer_id=s, risk_chain=s, ticker=s) for s in 'ABCD'},
        risk_parameters=dict(zip(('max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap'),('.45','.05','.8','.7','.55'))),
        transaction_cost_bps='10', minimum_cash_buffer_usd='100', target_weights={s:'0.20' for s in 'ABCD'},
        allowed_buy_security_ids=list('ABCD'), gaps=['ORIGINAL_IDENTITY_GAP'],
        **dict.fromkeys(('point_in_time_verified','promotion_allowed','fork_executable','orders_executed'),False))
    ref=dict(path='input.json',sha256='a'*64,json_pointer='/rows/8')
    oldref=dict(path='old.json',sha256='b'*64,json_pointer='/rows/0')
    old=dict(input_reference=ref,input_row=deepcopy(row),scenario_id=row['scenario_id'],domain=dict(conditional_research_buy_ids=list('ABCD'),buy_limits={s:3 for s in 'ABCD'}),
        evaluation=dict(branches=[dict(branch_id=row['scenario_id'],evaluated_count=1,evaluated_plans=[dict(buy_shares={s:1 for s in 'ABCD'},feasible=True)])]),
        original_allowed_buy_security_ids=list('ABCD'),selected_candidate_index=0,assumption='CONDITIONAL',new_buy_domain_is_research_assumption=True,
        target_weights_changed=False,cash_must_be_fully_invested=False,**dict.fromkeys(('point_in_time_verified','promotion_allowed','fork_executable','orders_executed'),False))
    p=prep.prepare_scenario(input_row=row,previous_row=old,input_reference=ref,previous_reference=oldref)
    task=next(prep.iter_neighbors(p,{}))
    return p,task


def reseal(p,t):
    p['contract_sha256']=w.digest(p['contract'])
    t['identity']['scenario_contract_sha256']=p['contract_sha256'];t['task_id']=w.digest(t['identity'])


class Tests(unittest.TestCase):
    def test_exact_old_explicit_kernel_once_zero_cartesian_and_l1(self):
        p,t=fixture();before=deepcopy((p,t));evaluate=w.fresh_evaluator();kernel=evaluate.__globals__['kernel']
        with patch.object(kernel,'evaluate_branches',wraps=kernel.evaluate_branches) as called,localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True
            result=evaluate(**w.evaluation_arguments(p,t));detail=w.inspect_return(p,t,result)
        self.assertEqual(called.call_count,1);self.assertEqual(called.call_args.kwargs['max_evaluations'],0)
        self.assertEqual(detail['outcome'],'FEASIBLE');self.assertEqual(detail['original_target_stock_weight_l1']['distance'],{'numerator':3,'denominator':86})
        self.assertEqual(result['branches'][0]['evaluated_plans'][0]['fees_usd'],'0.03')
        self.assertEqual((p,t),before);self.assertEqual(p['contract']['original_input_row']['target_weights']['A'],'0.20')

    def test_cash_failure_keeps_diagnostic_not_score_or_new_cash(self):
        p,t=fixture();p['contract']['original_input_row']['starting_cash_usd']='0';p['contract']['original_input_row']['cash_event']['amount_usd']='0';reseal(p,t)
        result=w.fresh_evaluator()(**w.evaluation_arguments(p,t));detail=w.inspect_return(p,t,result)
        self.assertEqual(detail['outcome'],'INFEASIBLE');self.assertIsNone(detail['original_target_stock_weight_l1'])
        self.assertFalse(result['branches'][0]['evaluated_plans'][0]['financial_checks']['CASH_BUFFER'])

    def test_identity_seed_caps_original_point_and_bool_attacks(self):
        for attack in ('cash','old','bool','origin','cap'):
            p,t=fixture()
            if attack=='cash':p['contract']['original_input_row']['starting_cash_usd']='200'
            elif attack=='old':t['identity']['buy_shares']={s:1 for s in 'ABCD'};t['task_id']=w.digest(t['identity'])
            elif attack=='bool':t['first_origin']['moves'][0]['delta']=True
            elif attack=='origin':t['first_origin']['seed_reference']['json_pointer']='/rows/99'
            else:t['identity']['buy_shares']['A']=4;t['task_id']=w.digest(t['identity'])
            with self.subTest(attack=attack),self.assertRaises(ValueError):w.evaluation_arguments(p,t)

    def test_pending_anchor_before_any_file_read(self):
        pending=dict(w.BOUND,audit=(w.BOUND['audit'][0],None))
        with patch.object(w,'BOUND',pending),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):w.load_common()
            read.assert_not_called()

    def test_attempt_durable_exception_and_no_retry(self):
        p,t=fixture();state=dict(prepared=p,task=t,contract_reference={'path':'c','sha256':'c'*64},task_reference={'path':'s','sha256':'d'*64},source_hashes={})
        def failing(**kwargs):raise ArithmeticError('synthetic only')
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'OUTPUT',Path(tmp)),patch.object(w,'load_task',return_value=state),patch.object(w,'guard'),patch.object(w,'fresh_evaluator',return_value=failing):
            common=dict(references={})
            ref=w.run(0,0,0,expected_task_id=t['task_id'],common=common,execute=True)
            post=w.decode(Path(ref['path']).read_bytes());self.assertEqual(post['outcome'],'EVALUATION_EXCEPTION');self.assertEqual(post['status'],'TECHNICAL_FAILURE_NOT_INFEASIBILITY')
            raw=w.decode((Path(ref['path']).parent/'raw.json').read_bytes());self.assertIsNone(raw['result']);self.assertEqual(raw['returned_evaluation_count'],0)
            with patch.object(w,'load_common') as load,self.assertRaises(ValueError):w.run(0,0,0,expected_task_id=t['task_id'],execute=True)
            load.assert_not_called()

    def test_invalid_return_is_validation_failure_and_source_drift_keeps_raw(self):
        p,t=fixture();state=dict(prepared=p,task=t,contract_reference={'path':'c','sha256':'c'*64},task_reference={'path':'s','sha256':'d'*64},source_hashes={})
        for drift in (False,True):
            with self.subTest(drift=drift),tempfile.TemporaryDirectory() as tmp,patch.object(w,'OUTPUT',Path(tmp)),patch.object(w,'load_task',return_value=state),patch.object(w,'guard',side_effect=[None,ValueError('drift'),ValueError('drift')] if drift else None),patch.object(w,'fresh_evaluator',return_value=lambda **kwargs:{'wrong':'return'}):
                common=dict(references={})
                if drift:
                    with self.assertRaises(ValueError):w.run(0,0,0,expected_task_id=t['task_id'],common=common,execute=True)
                    folder=Path(tmp)/t['task_id'];self.assertTrue((folder/'raw.json').exists());self.assertTrue((folder/'failure.json').exists())
                else:
                    ref=w.run(0,0,0,expected_task_id=t['task_id'],common=common,execute=True)
                    self.assertEqual(w.decode(Path(ref['path']).read_bytes())['outcome'],'VALIDATION_FAILURE')

    def test_missing_shard_does_not_become_infeasible(self):
        p,t=fixture()
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'OUTPUT',Path(tmp)),patch.object(w,'load_task',side_effect=FileNotFoundError('missing')):
            with self.assertRaises(FileNotFoundError):w.run(0,0,0,expected_task_id=t['task_id'],common={},execute=True)
            self.assertFalse((Path(tmp)/t['task_id']).exists())

    def test_forged_cache_cannot_authorize_itself_or_supply_evaluator(self):
        fake=dict(preparation={'rows':[]},references={k:w.reference(p,h) for k,(p,h) in w.BOUND.items()},source_hashes={})
        fake['source_hashes']={**w.source_map(),**{r['path']:r['sha256'] for r in fake['references'].values()}}
        fake['metadata_sha256']=w.digest(fake)
        with patch.object(w,'guard') as guarded,self.assertRaises(ValueError):w.load_task(fake,0,0,0,'a'*64)
        guarded.assert_not_called()
        p,t=fixture();state=dict(prepared=p,task=t,contract_reference={'path':'c','sha256':'c'*64},task_reference={'path':'s','sha256':'d'*64},source_hashes={})
        def trap(**kwargs):raise AssertionError('Caller evaluator must not be used')
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'OUTPUT',Path(tmp)),patch.object(w,'load_task',return_value=state),patch.object(w,'guard'):
            ref=w.run(0,0,0,expected_task_id=t['task_id'],common=dict(references={},evaluator=trap),execute=True)
            self.assertEqual(w.decode(Path(ref['path']).read_bytes())['outcome'],'FEASIBLE')


if __name__=='__main__':unittest.main()
