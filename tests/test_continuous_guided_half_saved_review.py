from copy import deepcopy
from fractions import Fraction as F
import unittest
from scripts.review_continuous_guided_half_exposure import review_signal, review_call_arguments
from test_current_quantity_v2_risk_overlays import fixture


def example(last=100, quantity=7):
    inputs=fixture({'A':[100]*19+[last]},quantities={'A':quantity})
    day=inputs['signal_date'];base=inputs['base_target'];mean=F(1900+last,20);on=F(last)>mean
    risk=dict(policy='SMA20_HALF_OFF_RESEARCH',signal_date=day,observed_at=inputs['observed_at'],
        execution='NEXT_SESSION_OPEN_ONLY_BY_SEPARATE_RUNNER',base_target=base,
        target_quantities={'A':quantity if on else quantity//2},diagnostics={'A':dict(close=str(last),sma20=str(mean),on=on,
        monthly_ceiling=quantity,off_exposure_fraction='1/2',rounding='FLOOR_MONTHLY_TARGET_NOT_CURRENT_HOLDINGS')})
    return dict(day=day,ceiling=base['quantities'],monthly=base['monthly_decision_date'],risk=risk,
        snapshot=dict(observed_at=inputs['observed_at'],review_reference=base['origin_reference'],histories=inputs['histories']),
        schedule=dict(inputs['session_close_times'],session_dates=inputs['session_dates']),close_prices={'A':{day:str(last)}})


class HalfSavedReviewTests(unittest.TestCase):
    def test_only_declared_assembler_fields_and_own_equity_binding(self):
        core=dict(decision_date='2026-01-30',entered_cash='20000',prices={'A':'10'})
        saved=dict(core,quote_as_of='2026-01-30',price_basis='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED')
        call=dict(decision_date='2026-01-30',search_arguments=deepcopy(saved),source_hashes={'source':'a'*64})
        binding=dict(search_arguments=dict(core,entered_cash='23000'),investable_equity='23000',source_hashes=deepcopy(call['source_hashes']))
        review_call_arguments(call,core,saved,binding)
        for key,value in [('quote_as_of','2026-02-02'),('price_basis','OTHER'),('extra',True)]:
            bad=deepcopy(call);bad['search_arguments'][key]=value
            with self.assertRaisesRegex(ValueError,'FULL_CALL_ARGUMENTS'):review_call_arguments(bad,core,saved,binding)
        bad=deepcopy(binding);bad['search_arguments']['entered_cash']='20000'
        with self.assertRaisesRegex(ValueError,'CALL_CORE_BINDING'):review_call_arguments(call,core,saved,bad)

    def test_equality_is_off_floor_and_recovery(self):
        self.assertEqual(review_signal(**example()),{'A':3})
        self.assertEqual(review_signal(**example(101)),{'A':7})

    def test_arithmetic_and_target_tampering_rejected(self):
        for key,value in [('on',True),('sma20','99'),('monthly_ceiling',8),('off_exposure_fraction','0')]:
            with self.subTest(key=key):
                args=example();args['risk']['diagnostics']['A'][key]=value
                with self.assertRaises(ValueError):review_signal(**args)
        args=example();args['risk']['target_quantities']['A']=4
        with self.assertRaisesRegex(ValueError,'SIGNAL_TARGET'):review_signal(**args)

    def test_future_missing_and_unit_tampering_rejected(self):
        for mode in ['future','missing','unit','nominal']:
            with self.subTest(mode=mode):
                args=example();history=args['snapshot']['histories']['A']
                if mode=='future':history['closes'][-1]['completed_at']='2099-01-01T16:00:00-05:00'
                elif mode=='missing':history['closes'].pop(0)
                elif mode=='unit':history['units']['unit_asof']='2000-01-01'
                else:args['close_prices']['A'][args['day']]='200'
                with self.assertRaises(ValueError):review_signal(**args)


if __name__=='__main__':unittest.main()
