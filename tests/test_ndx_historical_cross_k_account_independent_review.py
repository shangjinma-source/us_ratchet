import copy
import json
from decimal import Decimal,localcontext
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_historical_cross_k_account_arguments_research as m


def synthetic_equal(k):
    base=Path('data/cache/research')
    inputs=json.loads((base/'latest_twenty_historical_inputs_20260919_v1/inputs.json').read_bytes())
    original=json.loads((base/'latest_twenty_historical_single_target_20260919_v1/target.json').read_bytes())
    selected={r['security_id']:{name:r[name] for name in ('ticker','issuer_id','risk_chain')} for r in inputs['candidate_coordinate_and_risk_rows'][:k]}
    task=dict(selected=selected,holding_count=k,weight_spec='equal_weight',cutoff='2026-03-18',parameters=m.scalar.PARAMS,previous_target_weights=None);task['task_id']=m.digest(task)
    result=copy.deepcopy(original['result']);frame=m.first_window(inputs)
    tickers=[selected[s]['ticker'] for s in sorted(selected)];positions=[frame['columns'].index(t) for t in tickers]
    result.update(weight_spec='equal_weight',fit_data_sha256=m.digest(dict(dates=[d[:10] for d in frame['index']],tickers=tickers,returns=[[r[p] for p in positions] for r in frame['data']])),
                  targets={s:dict(ticker=r['ticker'],issuer_id=r['issuer_id'],target_weight=1./k) for s,r in selected.items()},anchor_by_security={s:0. for s in selected},risk_chains_by_security={s:r['risk_chain'] for s,r in selected.items()},single_name_projection_relaxed=False,top3_projection_semantics_relaxed=False)
    with localcontext() as context:
        context.prec=50;w=Decimal(str(1./k));tol=Decimal('1e-9');chain={}
        for row in selected.values():chain[row['risk_chain']]=chain.get(row['risk_chain'],Decimal(0))+w
        checks=dict(MAX_SINGLE_WEIGHT=w<=Decimal('.45')+tol,MIN_SINGLE_WEIGHT=w>=Decimal('.05')-tol,SECURITY_TOP3_WEIGHT=min(k,3)*w<=Decimal('.8')+tol,MINIMUM_EFFECTIVE_N=1/(k*w*w)>=Decimal(k)*Decimal('.7')-tol,RISK_CHAIN_TOP1_WEIGHT=max(chain.values())<=Decimal('.55')+tol)
    result.update(declared_constraint_checks=checks,declared_constraints_passed=all(checks.values()))
    detail=m.scalar.inspect_result(result,task,dict(returns=frame))
    return dict(inputs=inputs,task=task,result=result,numerical_sources=result['source_hashes'],audited_detail=detail)


class CrossKAccountReview(unittest.TestCase):
    def test_dynamic_four_and_fourteen_accounts_and_one_risk_failure_never_assembled(self):
        for k in (4,14):
            prepared=m.prepare_candidate_arguments(**synthetic_equal(k))
            self.assertEqual(prepared['status'],'READY_FOR_SOURCE_BOUND_SINGLE_ATTEMPT')
            self.assertEqual(len(prepared['account']['selected']['arguments']['schedule'][0]['targets']),k)
            self.assertEqual(len(prepared['account']['calendar']),127)
            self.assertFalse(prepared['control_executed'])
        with patch.object(m.assembly,'assemble_account_arguments',side_effect=AssertionError('risk failure cannot execute or assemble')) as assembler:
            prepared=m.prepare_candidate_arguments(**synthetic_equal(1))
        assembler.assert_not_called();self.assertIsNone(prepared['account']);self.assertIn('MAX_SINGLE_WEIGHT',prepared['failed_original_risk_checks'])

    def test_joint_result_and_audit_relabel_cannot_change_bound_identity_or_date(self):
        for defect in ('issuer','date','source','claim'):
            args=synthetic_equal(4)
            if defect=='issuer':
                sid=next(iter(args['task']['selected']));args['task']['selected'][sid]['issuer_id']='fabricated'
                args['result']['targets'][sid]['issuer_id']='fabricated'
                args['task']['task_id']=m.digest({k:v for k,v in args['task'].items() if k!='task_id'})
            elif defect=='date':args['inputs']['prices']['fit_return_dates']=args['inputs']['prices']['evaluation_return_dates']
            elif defect=='source':args['result']['source_hashes']={'fake':'0'*64}
            else:args['result']['promotion_allowed']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.prepare_candidate_arguments(**args)


if __name__=='__main__':unittest.main()
