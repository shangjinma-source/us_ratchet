from copy import deepcopy
from fractions import Fraction
from unittest.mock import patch
import unittest
from backtest import ndx_registered_scoring_job_inputs_research as m
from backtest import ndx_multidecision_scoring_budget_research as budget
from scripts import ndx_multidecision_scoring_budget_20261003 as projection
from test_ndx_multidecision_scoring_budget_wrapper_20261003 import fixture as source_fixture


def fixture(mode=1):
    docs,refs,channels=source_fixture()
    for i,row in enumerate(docs['history_index']['rows']):
        row['coordinate']['risk_chain']='mixed_industry'
        docs['history_audit']['rows'][i]['coordinate']['risk_chain']='mixed_industry'
        for period in docs['mdv_result']['periods']:period['rows'][i]['coordinate']['risk_chain']='mixed_industry'
    args=projection.project_inputs(docs,refs,channels);plan=budget.plan_multidecision_scoring_budget(**args)
    node=plan['rows'][0]['mode_plans'][mode];job=node['tasks'][0];decision=args['decisions'][0];days=decision['scoring_price_dates'];ids=job['identity']['security_ids'];by={u['security_id']:u for u in args['universe']}
    def windows(style):
        out=[]
        for i in range(13):
            s=i*21;row=dict(window_index=i,status='CONDITIONAL_NUMERIC_WINDOW',training_freeze_close=days[s+126],evaluation_first_return_end=days[s+127],evaluation_last_return_end=days[s+252])
            if style=='control':row.update(training_return_start=s,training_return_stop=s+126,evaluation_return_start=s+126,evaluation_return_stop=s+252,blocked_return_indexes=[])
            else:
                row.update(training_price_predecessor=days[s],training_return_index_start=s,training_return_index_stop=s+126,evaluation_return_index_start=s+126,evaluation_return_index_stop=s+252)
                row['blocked_price_slots' if style=='channel' else 'missing_price_sessions']=[]
            out.append(row)
        return out
    bindings=[]
    for column,sid in enumerate(ids):
        i=next(i for i,u in enumerate(args['universe']) if u['security_id']==sid);ch=deepcopy(channels[i]);d=ch['decisions'][0]
        d.update(price_index_start=0,price_index_stop=505,windows=windows('channel'))
        ch['return_rows']=[dict(session=days[n+1],previous_session=days[n],status='CONDITIONAL_NUMERIC_SLOT',dividends_included=False,split_only_return_exact=str(Fraction(column+1,10000)),split_only_return_float=float(Fraction(column+1,10000))) for n in range(504)]
        bindings.append(dict(coordinate=by[sid],reference=docs['history_index']['rows'][i]['channel_reference'],channel=ch))
    control=docs['original8_inputs']['scoring_inputs'];control.update(account_simulated=False,missing_slots_dropped=False,original_control_preserved=dict(securities=[dict(ticker=f'C{i}',target_weight=.125) for i in range(8)]),normalized_scoring_weights={f'C{i}':.125 for i in range(8)})
    control['decisions'][0].update(return_rows=[dict(session=days[n+1],previous_session=days[n],return_float=.002,missing_security_ids=[]) for n in range(504)],windows=windows('control'))
    target=docs['target_inputs'];target.update(session_dates=days,**dict.fromkeys(('point_in_time_verified','benchmark_qualified','score_computed','fit_performed','mode_selected_using_results','partial_window_pooling_allowed','missing_values_filled'),False))
    for i,td in enumerate(target['modes']):
        td['return_slots']=[dict(session=days[n+1],previous_session=days[n],status='CONDITIONAL_NUMERIC_RETURN',return_exact='1/1000',return_float=.001) for n in range(504)]
        if i:td['decisions'][0]['windows']=windows('target')
    manifest=dict(schema='MULTIDECISION_ROLLING_SCORING_NUMERICAL_SOURCES_V1',required_worker_environment=dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0),first_anchored_fit_none_interpretation='LEGACY_EQUAL_WEIGHT_ANCHOR',first_anchored_fit_strength=.25,**dict.fromkeys(('execution_authorized','fit_performed','score_computed','point_in_time_verified','promotion_allowed','outer_cutoff_refit_substitution_allowed'),False))
    return dict(registered_job=job,registered_mode_plan=node,decision_inputs=decision,universe=args['universe'],channel_bindings=bindings,original8_inputs=control,original8_reference=refs['original8_inputs'],target_inputs=target,target_reference=refs['target_inputs'],fitter_manifest=manifest,fitter_reference=refs['rolling_fitter_manifest'],budget_reference=dict(path='/saved/plan.json',sha256='f'*64))


class Tests(unittest.TestCase):
    def test_ordered_504_copy_and_thirteen_windows(self):
        args=fixture();before=deepcopy(args);out=m.assemble_registered_scoring_job_inputs(**args)
        self.assertEqual(args,before);self.assertEqual(out['status'],'ASSEMBLED_NOT_DISPATCHED')
        self.assertEqual(out['rolling_inputs']['candidate_returns'][0],[.0001,.0002,.0003,.0004])
        self.assertEqual(len(out['rolling_inputs']['return_dates']),504);self.assertEqual(len(out['window_metadata']),13)
        self.assertNotIn('fitted_windows',out['reducer_inputs']);self.assertFalse(out['fit_performed'])
        self.assertEqual(out['reducer_inputs']['original_incumbent_weights'],{f'C{i}':.125 for i in range(8)})
    def test_strict_blocked_no_numeric_projection(self):
        args=fixture(0);args['channel_bindings']=None;args['original8_inputs']=None
        with patch.object(m,'finite',side_effect=AssertionError('numeric')):
            out=m.assemble_registered_scoring_job_inputs(**args)
        self.assertEqual(out['status'],'SOURCE_BLOCKED');self.assertIsNone(out['rolling_inputs']);self.assertIsNone(out['reducer_inputs'])
        args['registered_job']['status']='PLANNED_NOT_ATTEMPTED'
        with self.assertRaises(ValueError):m.assemble_registered_scoring_job_inputs(**args)
    def test_original_weight_sum_overflow_rejected(self):
        args=fixture()
        for row in args['original8_inputs']['original_control_preserved']['securities']:row['target_weight']=1e308
        args['original8_inputs']['normalized_scoring_weights']={f'C{i}':0. for i in range(8)}
        with self.assertRaisesRegex(ValueError,'Finite positive original weight sum'):m.assemble_registered_scoring_job_inputs(**args)

    def test_reject_id_rank_order_and_wrong_mode(self):
        for edit in (lambda a:a['registered_job']['identity'].update(cutoff='2026-09-21'),lambda a:a['registered_job']['position'].update(rank=999999),lambda a:a['channel_bindings'].reverse(),lambda a:a['registered_mode_plan']['tasks'].pop(0),lambda a:a['decision_inputs']['mode_sources'].reverse(),lambda a:a['universe'].pop()):
            args=fixture();edit(args)
            with self.assertRaises(ValueError):m.assemble_registered_scoring_job_inputs(**args)
    def test_reject_numeric_bool_missing_and_window_drift(self):
        for edit in (lambda a:a['channel_bindings'][0]['channel']['return_rows'][0].update(split_only_return_float=True),lambda a:a['original8_inputs']['decisions'][0]['return_rows'].pop(),lambda a:a['target_inputs']['modes'][1]['return_slots'][0].update(return_float=.9),lambda a:a['channel_bindings'][0]['channel']['decisions'][0]['windows'][12].update(training_return_index_start=0),lambda a:a['original8_inputs']['normalized_scoring_weights'].update(C0=.9)):
            args=fixture();edit(args)
            with self.assertRaises(ValueError):m.assemble_registered_scoring_job_inputs(**args)

if __name__=='__main__':unittest.main()
