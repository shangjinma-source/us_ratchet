from copy import deepcopy
from decimal import localcontext, Inexact
import unittest
from backtest import ndx_dated_per_task_comparison_research as core
from test_ndx_dated_economic_comparison_research import fixture_comparison


def fixture():
    old=fixture_comparison()
    result={k:old[k] for k in ('candidate_account','incumbent_account','nav_metrics')}
    for role in ('candidate','incumbent'):
        result[role+'_continuous']=old['continuous_document']['tracks'][role]
        result[role+'_account']['decisions'][0]['status']='FROZEN'
    result['source_references']={k:dict(path=k+'.json',sha256='a'*64,json_pointer='/actual/'+k) for k in ('candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous','nav_metrics')}
    result['candidate_integer_status']=dict(status='AVAILABLE',reason=None,evidence_reference=dict(path='audit.json',sha256='b'*64,json_pointer='/account_outcome'))
    return result


class Tests(unittest.TestCase):
    def test_complete_exact_metrics_separate_sources_and_modes(self):
        a=fixture();before=deepcopy(a);r=core.compare_per_task_paths(**a)
        self.assertEqual(a,before)
        self.assertEqual(r['tracks']['candidate_integer']['metrics']['annualized_return']['exact'],'11/25')
        for mode in core.MODES:
            self.assertEqual(r['absolute_distance_comparisons'][mode]['integer']['annualized_return']['candidate_minus_incumbent_distance']['exact'],'-11/25')
        self.assertEqual(len(r['nav_modes']),2)
        self.assertNotEqual(r['tracks']['candidate_continuous']['source_reference'],r['tracks']['incumbent_continuous']['source_reference'])
        self.assertTrue(all(r[k] is False for k in core.FLAGS))

    def test_zero_missing_integer_not_fake_cash(self):
        a=fixture();a['candidate_continuous']['positions_preserved'][0]['target_weight']=0.0
        a['candidate_account']=None;a['source_references']['candidate_integer']=None
        a['candidate_integer_status'].update(status='NOT_EXECUTED_NONPOSITIVE_TARGET',reason='Original zero coordinate blocks integer input')
        r=core.compare_per_task_paths(**a)
        self.assertIsNone(r['tracks']['candidate_integer']['stored_values_exact'])
        self.assertIsNone(r['tracks']['candidate_integer']['metrics'])
        self.assertEqual(len(r['tracks']['candidate_continuous']['original_track_preserved']['positions_preserved']),4)
        self.assertEqual(r['tracks']['candidate_continuous']['original_track_preserved']['positions_preserved'][0]['target_weight'],0.0)
        for mode in core.MODES:
            self.assertIsNone(r['absolute_distance_comparisons'][mode]['integer']['maximum_drawdown']['candidate_minus_incumbent_distance'])
            self.assertIsNotNone(r['absolute_distance_comparisons'][mode]['integer']['maximum_drawdown']['incumbent_absolute_distance'])
            self.assertIsNotNone(r['absolute_distance_comparisons'][mode]['continuous']['maximum_drawdown']['candidate_minus_incumbent_distance'])

    def test_technical_absence_and_false_reason_reject(self):
        a=fixture();a['candidate_account']=None;a['source_references']['candidate_integer']=None
        a['candidate_integer_status'].update(status='TECHNICAL_MISSING',reason='Saved numerical exception; no returned ledger')
        r=core.compare_per_task_paths(**a)
        self.assertEqual(r['tracks']['candidate_integer']['status'],'TECHNICAL_MISSING')
        a['candidate_integer_status']['reason']=' '
        with self.assertRaises(ValueError):core.compare_per_task_paths(**a)
        a['candidate_integer_status'].update(status='NOT_EXECUTED_NONPOSITIVE_TARGET',reason='Claimed zero')
        with self.assertRaises(ValueError):core.compare_per_task_paths(**a)

    def test_actual_no_plan_or_rejected_account_retained(self):
        for state in ('NO_PLAN','REJECTED'):
            a=fixture();account=a['candidate_account']
            for row in account['daily']:row.update(total_value_usd=25000.,cash_usd=25000.,shares={})
            if state=='NO_PLAN':account['decisions'][0]['status']='NO_PLAN';account['executions']=[]
            else:account['executions'][0]['status']='REJECTED'
            r=core.compare_per_task_paths(**a)
            self.assertEqual(r['tracks']['candidate_integer']['status'],'AVAILABLE')
            self.assertEqual(r['tracks']['candidate_integer']['metrics']['cumulative_return']['exact'],'0')
            self.assertEqual(r['tracks']['candidate_integer']['original_account_preserved'],account)

    def test_initial_peak_hostile_context_and_invalid_contracts(self):
        a=fixture()
        for row in a['candidate_account']['daily'][1:]:row['total_value_usd']=20000.
        with localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True;r=core.compare_per_task_paths(**a)
        m=r['tracks']['candidate_integer']['metrics']
        self.assertEqual(m['maximum_drawdown']['exact'],'1/5');self.assertEqual(m['annualized_return']['exact'],'-9/25')
        self.assertEqual(m['drawdown']['peak_index'],0)
        for case in ('missing','bool','source_conflict','fake_available_zero'):
            a=fixture()
            if case=='missing':a['candidate_continuous']['path'].pop(5)
            elif case=='bool':a['nav_metrics']['modes'][core.MODES[0]]['interval_count']=True
            elif case=='source_conflict':a['source_references']['candidate_continuous'].update(path='audit.json',sha256='c'*64)
            else:a['candidate_continuous']['positions_preserved'][0]['target_weight']=0.
            with self.subTest(case=case),self.assertRaises(ValueError):core.compare_per_task_paths(**a)


if __name__=='__main__':unittest.main()
