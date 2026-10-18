import copy
import json
from pathlib import Path
import unittest
from backtest import ndx_historical_cross_k_account_independent_research as m

BASE=Path('data/cache/research')


def fixture():
    load=lambda p:json.loads(p.read_bytes())
    inputs=load(BASE/'latest_twenty_historical_inputs_20260919_v1/inputs.json')
    target=load(BASE/'latest_twenty_historical_single_target_20260919_v1/target.json')
    candidate=load(BASE/'historical_single_window_accounts_20260920_v1/candidate/account.json')
    raw=load(BASE/'historical_single_window_accounts_20260920_v1/candidate/raw_execution.json')
    control=load(BASE/'historical_single_window_accounts_20260923_control_recovery_v2/account.json')
    frame=copy.deepcopy(inputs['prices']['returns']);frame['index']=frame['index'][:126];frame['data']=frame['data'][:126]
    detail=m.scalar.inspect_result(target['result'],target['task'],dict(returns=frame))
    return dict(inputs=inputs,task=target['task'],result=target['result'],numerical_sources=target['result']['source_hashes'],audited_detail=detail,
        raw_execution=raw['execution'],execution=candidate['execution'],effective_schedule=candidate['effective_schedule'],normalization_evidence=candidate['normalization_evidence'],
        control_execution=control['execution'],nav_csv=(BASE/'latest_conditional_input_readiness_20260919_v1/observed_inputs/nav.csv').read_text(encoding='utf-8-sig'))


class IndependentAccountTests(unittest.TestCase):
    def test_real_saved_account_and_shared_control_no_execution(self):
        report=m.audit_candidate(**fixture())
        self.assertEqual(report['candidate_accounting']['rejected_count'],1)
        self.assertEqual(report['candidate_accounting']['trade_count'],0)
        self.assertEqual(report['comparison']['candidate']['path_return'],'0')
        self.assertTrue(report['control_accounting']['filled'])
        self.assertTrue(all(report[k] is False for k in m.FALSE))

    def test_dynamic_four_security_risk_failure_kept_without_account(self):
        args=fixture();task=args['task'];selected={s:task['selected'][s] for s in sorted(task['selected'])[:4]}
        for r in selected.values():r['risk_chain']='synthetic_concentrated'
        for r in args['inputs']['candidate_coordinate_and_risk_rows']:
            if r['security_id'] in selected:r['risk_chain']='synthetic_concentrated'
        task.update(selected=selected,holding_count=4,weight_spec='equal_weight');task['task_id']=m.digest({k:v for k,v in task.items() if k!='task_id'})
        result=args['result'];result.update(weight_spec='equal_weight',targets={s:dict(ticker=r['ticker'],issuer_id=r['issuer_id'],target_weight=.25) for s,r in selected.items()},
            risk_chains_by_security={s:'synthetic_concentrated' for s in selected},anchor_by_security={s:0. for s in selected},declared_constraints_passed=False)
        result['declared_constraint_checks']['RISK_CHAIN_TOP1_WEIGHT']=False
        frame=copy.deepcopy(args['inputs']['prices']['returns']);frame['index']=frame['index'][:126];frame['data']=frame['data'][:126]
        tickers=[selected[s]['ticker'] for s in sorted(selected)];positions=[frame['columns'].index(t) for t in tickers]
        result['fit_data_sha256']=m.digest(dict(dates=[d[:10] for d in frame['index']],tickers=tickers,returns=[[r[i] for i in positions] for r in frame['data']]))
        args['audited_detail']=m.scalar.inspect_result(result,task,dict(returns=frame))
        for k in ('raw_execution','execution','effective_schedule','normalization_evidence'):args[k]=None
        report=m.audit_candidate(**args)
        self.assertEqual(report['holding_count'],4);self.assertEqual(report['status'],'NOT_EXECUTED_ORIGINAL_FIVE_RISK_FAILURE')
        self.assertIsNone(report['comparison']);self.assertEqual(report['failed_original_risk_checks'],['RISK_CHAIN_TOP1_WEIGHT'])
        args['execution']={}
        with self.assertRaises(ValueError):m.audit_candidate(**args)

    def test_future_weight_import_raw_cash_and_normalization_rejected(self):
        for defect in ('future','cash','label','normalization','source','audit','scope','control'):
            args=fixture()
            if defect=='future':args['task']['cutoff']='2026-09-17';args['task']['task_id']=m.digest({k:v for k,v in args['task'].items() if k!='task_id'})
            elif defect=='cash':args['execution']['daily'][2]['cash_usd']+=1
            elif defect=='label':args['raw_execution']['decisions'][0]['targets'][next(iter(args['task']['selected']))]['ticker']='WRONG'
            elif defect=='normalization':args['normalization_evidence']['extra']=True
            elif defect=='source':args['numerical_sources']={}
            elif defect=='audit':args['audited_detail']['risk_pass']=1
            elif defect=='scope':args['inputs']['point_in_time_verified']=True
            else:args['control_execution']['daily'][-1]['total_value_usd']+=1
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.audit_candidate(**args)


if __name__=='__main__':unittest.main()
