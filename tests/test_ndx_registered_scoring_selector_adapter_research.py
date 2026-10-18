from copy import deepcopy
import unittest
from test_ndx_multidecision_scoring_budget_research import fixture as budget_fixture
from backtest import ndx_multidecision_scoring_budget_research as budget
from backtest import ndx_registered_scoring_selector_adapter_research as m
from backtest import ndx_full_ndx_multidecision_selector_research as selector


def fixture():
    policy,u,ds=budget_fixture();r=dict(path='policy.json',sha256=m.POLICY_SHA)
    for v in u:v['risk_chain']='CHAIN'+v['security_id']
    for d in ds:
        for i,q in enumerate(d['qualifications']):q['history_13_complete']=i<4
    b=budget.plan_multidecision_scoring_budget(registration=policy,registration_reference=r,universe=u,decisions=ds)
    base=dict(path='evidence.json',sha256='a'*64,json_pointer='/rows/0');by={v['security_id']:v for v in u};ps=[];first=True
    for row,d in zip(b['rows'],ds):
        for mode in row['mode_plans']:
            for job in mode['tasks']:
                p=dict(job_id=job['job_id'],outcome='SOURCE_BLOCKED',source_kind='REGISTERED_SOURCE_BLOCKED',score=None,inspection=None,score_reference=None,inspection_reference=None,evidence_reference=base,error=None)
                if job['status']!='SOURCE_BLOCKED':
                    windows=[];days=d['scoring_price_dates']
                    for i in range(13):
                        l=i*21;f=dict(window_index=i,fit_data_sha256='b'*64,fit_first_return_end=days[l+1],fit_last_return_end=days[l+126],evaluation_first_return_end=days[l+127],evaluation_last_return_end=days[l+252])
                        windows.append(dict(window_index=i,fitted_window_preserved=f,risk_checks=dict.fromkeys(m.RISK,True)))
                    metrics=dict.fromkeys(m.SAVED_METRICS,.1)
                    score=dict(schema='MULTIDECISION_FITTED_WINDOW_SCORE_REDUCTION_V1',cutoff=d['cutoff'],securities=[{k:by[s][k] for k in ('security_id','ticker','issuer_id','risk_chain')} for s in job['identity']['security_ids']],metrics=metrics,windows=windows,fractional_risk_passed=True,risk_gate_semantics='ALL_FIVE_DECLARED_FRACTIONAL_CONSTRAINTS_EVERY_WINDOW',score_computed=True,**dict.fromkeys(('source_bytes_authenticated','fit_performed','point_in_time_verified','selected_rolling_weights_are_execution_targets','whole_lot_gate_evaluated','formal_benchmark_passed','account_executed','promotion_allowed'),False))
                    ar=dict(schema='MULTIDECISION_WINDOW_SCORING_INSPECTION_V1',status='PASS',window_count=13,window_return_count=126,metric_count=17,binary64_comparison='EXACT_HEX_NO_TOLERANCE',**dict.fromkeys(('source_bytes_authenticated','fit_performed','formal_benchmark_passed','account_executed','promotion_allowed'),False))
                    ins=dict(schema='REGISTERED_SCORING_RESULT_INSPECTION_V1',status='PASS',job_id=job['job_id'],window_count=13,fit_matrix_hashes=['b'*64]*13,score_arithmetic=ar,**dict.fromkeys(('optimization_rerun','optimized_weights_independently_verified','recovery_certificates_recomputed','source_bytes_authenticated','fit_performed','account_executed','promotion_allowed'),False))
                    sr=dict(base,json_pointer='/result') if first else dict(journal_reference=dict(path='journal.jsonl',sha256='c'*64),record_locator=dict(sequence=7,byte_start=100,byte_stop=1000,record_sha256='d'*64,stage='RAW_SCORE'),result_field='payload.result')
                    p.update(outcome=m.SUCCESS,source_kind='FIRST_EXTERNAL' if first else 'JOURNAL',score=score,inspection=ins,score_reference=sr,inspection_reference=base);first=False
                ps.append(p)
    return dict(budget_plan=b,budget_reference=dict(path='budget.json',sha256='e'*64),budget_audit_reference=dict(path='audit.json',sha256='f'*64),projections=ps,selection_registration_reference=dict(path='selection.json',sha256='0'*64))


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.args=fixture()
    def test_complete_projection_feeds_frozen_selector_without_mode_substitution(self):
        out=m.assemble_registered_selector_inputs(**deepcopy(self.args));self.assertEqual(out['logical_task_count'],36);self.assertEqual(out['source_blocked_task_count'],18)
        selected=selector.select_full_ndx_lanes(registration=out['registration'],records=out['records'])
        self.assertEqual(len(selected['rows']),12)
        for i,row in enumerate(selected['rows']):
            self.assertFalse(row['input_errors'])
            self.assertTrue(all(c['status']==('SOURCE_BLOCKED' if i%2==0 else 'SELECTED_REQUIRES_NEW_CUTOFF_REFIT') for c in row['choices']))
        self.assertEqual(len(out['registration']['universe']),77);self.assertEqual(len(out['registration']['all_k_denominators']),76)
        self.assertFalse(out['selector_called']);self.assertFalse(out['point_in_time_verified'])
    def test_risk_failure_rejected_errors_not_cash(self):
        a=deepcopy(self.args);p=next(p for p in a['projections'] if p['outcome']==m.SUCCESS)
        p['score']['windows'][0]['risk_checks'][m.RISK[0]]=False;p['score']['fractional_risk_passed']=False
        o=m.assemble_registered_selector_inputs(**a);s=selector.select_full_ndx_lanes(registration=o['registration'],records=o['records']);self.assertEqual(len(s['rows'][1]['rejections']),1)
        p.update(outcome='NUMERICAL_EXCEPTION',score=None,inspection=None,score_reference=None,inspection_reference=None,error={'message':'saved failure'})
        o=m.assemble_registered_selector_inputs(**a);s=selector.select_full_ndx_lanes(registration=o['registration'],records=o['records']);self.assertTrue(all(c['status']=='INPUT_INVALID' and c['selected'] is None for c in s['rows'][1]['choices']))
    def test_missing_reordered_sourceblock_and_audit_tampering(self):
        for mode in ('missing','order','blocked','inspection','window','bool'):
            a=deepcopy(self.args);p=next(p for p in a['projections'] if p['outcome']==m.SUCCESS)
            if mode=='missing':a['projections'].pop()
            elif mode=='order':a['projections'].reverse()
            elif mode=='blocked':a['projections'][0]['score']={}
            elif mode=='inspection':p['inspection']['job_id']='f'*64
            elif mode=='window':p['score']['windows'][12]['fitted_window_preserved']['evaluation_last_return_end']='2026-09-21'
            else:p['score']['windows'][0]['risk_checks'][m.RISK[0]]=1
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.assemble_registered_selector_inputs(**a)
    def test_full_domain_and_original_order_independent_of_projection_semantics(self):
        a=deepcopy(self.args);a['budget_plan']['rows'][0]['domain_coverage'][0]['qualification_excluded_combination_count']+=1
        a['budget_plan']['content_sha256']=m.digest({k:v for k,v in a['budget_plan'].items() if k!='content_sha256'})
        with self.assertRaises(ValueError):m.assemble_registered_selector_inputs(**a)

if __name__=='__main__':unittest.main()
