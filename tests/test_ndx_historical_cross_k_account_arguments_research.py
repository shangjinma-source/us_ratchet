import copy
import json
from pathlib import Path
import unittest
from backtest import ndx_historical_cross_k_account_arguments_research as m

BASE=Path('data/cache/research')


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=json.loads((BASE/'latest_twenty_historical_inputs_20260919_v1/inputs.json').read_bytes())
        cls.target=json.loads((BASE/'latest_twenty_historical_single_target_20260919_v1/target.json').read_bytes())
        cls.saved=json.loads((BASE/'historical_single_window_accounts_20260920_v1/candidate/account.json').read_bytes())

    def arguments(self):
        task=copy.deepcopy(self.target['task']);result=copy.deepcopy(self.target['result']);inputs=copy.deepcopy(self.inputs)
        detail=m.scalar.inspect_result(result,task,{'returns':m.first_window(inputs)})
        return dict(inputs=inputs,task=task,result=result,numerical_sources=result['source_hashes'],audited_detail=detail)

    def test_real_existing_historical_account_exact_inputs_only(self):
        prepared=m.prepare_candidate_arguments(**self.arguments())
        self.assertEqual(prepared['status'],'READY_FOR_SOURCE_BOUND_SINGLE_ATTEMPT');self.assertEqual(len(prepared['account']['calendar']),127)
        proof=m.existing_account_equivalence(prepared,self.saved,source_input_reference=self.saved['input_reference'])
        self.assertTrue(proof['account_arguments_and_ledger_match_under_declared_input_reference']);self.assertFalse(proof['result_reused'])

    def test_real_risk_failure_retained_without_account_execution(self):
        args=self.arguments();selected=args['task']['selected']
        for row in args['inputs']['candidate_coordinate_and_risk_rows']:
            if row['security_id'] in selected:row['risk_chain']='one_concentrated_chain'
        for row in selected.values():row['risk_chain']='one_concentrated_chain'
        args['task']['task_id']=m.digest({k:v for k,v in args['task'].items() if k!='task_id'})
        args['result']['risk_chains_by_security']={s:'one_concentrated_chain' for s in selected}
        args['result']['declared_constraint_checks']['RISK_CHAIN_TOP1_WEIGHT']=False;args['result']['declared_constraints_passed']=False
        args['audited_detail']=m.scalar.inspect_result(args['result'],args['task'],{'returns':m.first_window(args['inputs'])})
        prepared=m.prepare_candidate_arguments(**args)
        self.assertEqual(prepared['failed_original_risk_checks'],['RISK_CHAIN_TOP1_WEIGHT']);self.assertIsNone(prepared['account']);self.assertFalse(prepared['execution_performed'])

    def test_wrong_cutoff_identity_audit_or_source_rejected(self):
        for defect in ('cutoff','issuer','audit','sources'):
            args=self.arguments()
            if defect=='cutoff':args['task']['cutoff']='2026-09-17';args['task']['task_id']=m.digest({k:v for k,v in args['task'].items() if k!='task_id'})
            elif defect=='issuer':args['task']['selected'][next(iter(args['task']['selected']))]['issuer_id']='wrong';args['task']['task_id']=m.digest({k:v for k,v in args['task'].items() if k!='task_id'})
            elif defect=='audit':args['audited_detail']['risk_pass']=1
            else:args['numerical_sources']={'wrong.py':'a'*64}
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.prepare_candidate_arguments(**args)

    def test_existing_ledger_or_fee_change_cannot_be_reused(self):
        prepared=m.prepare_candidate_arguments(**self.arguments())
        for defect in ('fee','cash','scope'):
            value=copy.deepcopy(self.saved)
            if defect=='fee':value['execution_contract']['transaction_cost_bps']=0
            elif defect=='cash':value['execution']['daily'][-1]['cash_usd']+=1
            else:value['promotion_allowed']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.existing_account_equivalence(prepared,value,source_input_reference=self.saved['input_reference'])


if __name__=='__main__':unittest.main()
