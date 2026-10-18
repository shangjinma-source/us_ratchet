from copy import deepcopy
from datetime import date,timedelta
from decimal import localcontext,Inexact
import unittest
from backtest import ndx_same_window_nav_reference_metrics_research as m

def weekdays(first,last):
    d=date.fromisoformat(first);out=[]
    while d<=date.fromisoformat(last):
        if d.weekday()<5:out.append(d.isoformat())
        d+=timedelta(days=1)
    return out
def fixture():
    a=weekdays('2025-09-18','2026-03-20');b=weekdays('2026-03-23','2026-09-21');days=a[:126]+[a[-1]]+b[:125]+[b[-1]]
    ref=dict(path='/synthetic/alignment.json',sha256='a'*64);calendar=dict(dates=days[126:],source_reference=dict(path='/synthetic/requirements.json',sha256='b'*64));rows=[]
    for i,d in enumerate(days):
        value='2' if i==126 else '1';conversions={mode:dict(denominator_basis='SESSION_ALIGNED_FX_NOT_NAV_DATE_FX',status='CONDITIONAL_NAV_USD_OBSERVATION',reason=None,nav_usd_exact=value,nav_usd_decimal=value,nav_date=d,fx_date=d) for mode in m.MODES}
        rows.append(dict(session=d,conversions=conversions,nav_date_fx_used_for_conversion=False,nav_observation={'date':d,'lag_calendar_days':0,'available_at':None},session_fx={'retained':'source references'}))
    alignment=dict(schema='NAV_USD_OBSERVATION_ALIGNMENT_V1',status='CONDITIONAL_HISTORICAL_CONVERSION_ONLY',modes=list(m.MODES),conversion_formula='BACKWARD_NAV_CNY / SESSION_ALIGNED_CNY_PER_USD',fx_context_preserved=dict(rate_direction='CNY_PER_USD',publication_time=None),session_dates=days,rows=rows,limitations=['NO_AVAILABLE_AT'],**dict.fromkeys(('point_in_time_verified','historical_available_at_verified','benchmark_qualified','formal_admission_allowed','account_executed','mode_selected_using_results','fit_performed','execution_authorized'),False))
    resign(alignment)
    return dict(alignment=alignment,alignment_reference=ref,reference_calendar=calendar)
def resign(value):value['content_sha256']=m.digest({k:v for k,v in value.items() if k!='content_sha256'})

class Tests(unittest.TestCase):
    def test_initial_peak_loss_and_exact_annualization(self):
        args=fixture();before=deepcopy(args);out=m.calculate_reference_metrics(**args)
        for mode in m.MODES:
            r=out['modes'][mode];self.assertEqual(r['metrics']['cumulative_return']['exact'],'-1/2');self.assertEqual(r['metrics']['annualized_return']['exact'],'-3/4');self.assertEqual(r['metrics']['maximum_drawdown']['exact'],'1/2');self.assertEqual(r['metrics']['drawdown']['peak_index'],0);self.assertEqual(r['metrics']['drawdown']['trough_index'],1);self.assertEqual(r['observations'][0]['normalized_value_exact'],'1')
        self.assertTrue(out['mode_values_exactly_equal']);self.assertEqual(len(out['modes']),2);self.assertIsNot(out['modes'][m.MODES[0]],out['modes'][m.MODES[1]]);self.assertEqual(args,before)

    def test_missing_does_not_compress_or_block_other_mode(self):
        args=fixture();v=args['alignment']['rows'][140]['conversions'][m.MODES[0]];v.update(status='MISSING_ALIGNMENT_INPUT',reason='SAME_SESSION_FX_ND',nav_usd_exact=None,nav_usd_decimal=None);resign(args['alignment']);out=m.calculate_reference_metrics(**args)
        row=out['modes'][m.MODES[0]];self.assertEqual(len(row['observations']),127);self.assertEqual(len(row['interval_returns']),126);self.assertIsNone(row['metrics']);self.assertTrue(all(r['normalized_value_exact'] is None for r in row['observations']));self.assertIsNotNone(out['modes'][m.MODES[1]]['metrics']);self.assertIsNone(out['mode_values_exactly_equal'])

    def test_training_missing_ignored_without_losing_evaluation_dates(self):
        args=fixture();v=args['alignment']['rows'][20]['conversions'][m.MODES[0]];v.update(status='MISSING_ALIGNMENT_INPUT',reason='SAME_SESSION_FX_ND',nav_usd_exact=None,nav_usd_decimal=None);resign(args['alignment']);out=m.calculate_reference_metrics(**args);self.assertTrue(out['both_modes_complete']);self.assertEqual(out['reference_calendar']['dates'],args['alignment']['session_dates'][126:])

    def test_direction_calendar_and_noncanonical_number_rejected(self):
        for change in (lambda a:a['alignment']['fx_context_preserved'].update(rate_direction='USD_PER_CNY'),lambda a:a['reference_calendar']['dates'].pop(0),lambda a:a['alignment']['rows'][130]['conversions'][m.MODES[0]].update(nav_usd_exact=1.0),lambda a:a['alignment']['rows'][130]['conversions'][m.MODES[0]].update(nav_usd_exact='2/2')):
            args=fixture();change(args);resign(args['alignment'])
            with self.assertRaises(ValueError):m.calculate_reference_metrics(**args)

    def test_decimal_context_and_modes_not_chosen_by_gain(self):
        args=fixture();v=args['alignment']['rows'][-1]['conversions'][m.MODES[1]];v.update(nav_usd_exact='7/3',nav_usd_decimal='ignored saved display');resign(args['alignment'])
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True;out=m.calculate_reference_metrics(**args)
        self.assertFalse(out['mode_values_exactly_equal']);self.assertEqual(out['modes'][m.MODES[1]]['metrics']['annualized_return']['exact'],'13/36');self.assertFalse(out['mode_selected_using_results']);self.assertFalse(out['cohort_p50_computed'])

if __name__=='__main__':unittest.main()
