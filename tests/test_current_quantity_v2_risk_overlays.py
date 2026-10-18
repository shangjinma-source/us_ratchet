import unittest
from copy import deepcopy
from datetime import date,timedelta
from fractions import Fraction as F
from math import isqrt
from backtest.current_quantity_v2_risk_overlays import volatility20_target20,sma20_target,UNIT_SCHEMA


def fixture(values,quantities=None):
    dates=[];day=date(2026,1,2)
    while len(dates)<len(next(iter(values.values()))):
        if day.weekday()<5:dates.append(day.isoformat())
        day+=timedelta(days=1)
    quantities=quantities or {s:100 for s in values}
    base=dict(quantities=quantities,price_units={s:'unit:'+s for s in values},origin_reference='frozen-monthly-selection',monthly_decision_date=dates[-1])
    histories={s:dict(units=dict(schema=UNIT_SCHEMA,unit_asof=dates[-1],currency='USD',basis_id='unit:'+s,review_reference='unit-review'),source_reference='source:'+s,
        closes=[dict(date=d,completed_at=d+'T16:00:00-05:00',close=str(v)) for d,v in zip(dates,series)]) for s,series in values.items()}
    return dict(base_target=base,signal_date=dates[-1],observed_at=dates[-1]+'T16:01:00-05:00',session_dates=dates,
        session_close_times=dict(review_reference='calendar-review',closes={d:d+'T16:00:00-05:00' for d in dates}),histories=histories)


class OverlayTests(unittest.TestCase):
    def test_volatility_sample_variance_and_exact_floor(self):
        values=[F(100)]
        for i in range(20):values.append(values[-1]*(F(11,10) if i%2==0 else F(9,10)))
        args=fixture({'A':values});before=deepcopy(args);r=volatility20_target20(**args)
        expected_variance=F(1,5)/19
        self.assertEqual(F(r['diagnostics']['sample_variance']),expected_variance)
        self.assertEqual(F(r['diagnostics']['annual_variance']),252*expected_variance)
        squared=F(1,25)/(252*expected_variance)
        self.assertEqual(r['target_quantities']['A'],isqrt((10000*squared.numerator)//squared.denominator))
        self.assertEqual(args,before);self.assertFalse(r['performance_validated'])

    def test_zero_volatility_no_leverage_and_portfolio_covariance(self):
        a=fixture({'A':[100]*21},quantities={'A':17})
        self.assertEqual(volatility20_target20(**a)['target_quantities'],{'A':17})
        # Equal final marked weights, perfectly opposite daily return histories:
        # portfolio variance must use weighted returns, not sum of stock vols.
        x=[F(100)];y=[F(100)]
        for i in range(20):
            shift=F(1,10) if i%2==0 else F(-1,10)
            x.append(x[-1]*(1+shift));y.append(y[-1]*(1-shift))
        r=volatility20_target20(**fixture({'A':x,'B':y}))
        self.assertEqual(r['diagnostics']['annual_variance'],'0')

    def test_sma_equality_off_reentry_respects_immutable_ceiling(self):
        args=fixture({'A':[100]*20},quantities={'A':7});base=deepcopy(args['base_target'])
        self.assertEqual(sma20_target(**args)['target_quantities'],{'A':0})
        args['histories']['A']['closes'][-1]['close']='101'
        self.assertEqual(sma20_target(**args)['target_quantities'],{'A':7})
        self.assertEqual(args['base_target'],base)

    def test_future_missing_and_raw_split_units_rejected(self):
        for kind in ['future','missing','raw','target_basis']:
            args=fixture({'A':[100]*21})
            if kind=='future':args['histories']['A']['closes'][-1]['completed_at']='2099-01-01T16:00:00-05:00'
            if kind=='missing':args['histories']['A']['closes'].pop(3)
            if kind=='raw':
                args['histories']['A']['units']['schema']='RAW_NOMINAL'
                args['histories']['A']['closes'][-1]['close']='50'
            if kind=='target_basis':args['base_target']['price_units']['A']='pre-split-unit'
            with self.assertRaises(ValueError):volatility20_target20(**args)

    def test_r1_cannot_retarget_on_daily_continuation(self):
        args=fixture({'A':[100]*21})
        args['base_target']['monthly_decision_date']=args['session_dates'][0]
        with self.assertRaisesRegex(ValueError,'MONTHLY_DECISION_ONLY'):volatility20_target20(**args)

    def test_future_monthly_target_rejected_by_sma(self):
        args=fixture({'A':[100]*20});args['base_target']['monthly_decision_date']='2099-01-01'
        with self.assertRaisesRegex(ValueError,'MONTHLY_TARGET_DATE'):sma20_target(**args)

    def test_late_observation_cannot_authorize_historical_decision(self):
        args=fixture({'A':[100]*20})
        args['observed_at']='2099-01-01T16:01:00-05:00'
        with self.assertRaisesRegex(ValueError,'OBSERVATION_MUST_BE_DECISION'):
            sma20_target(**args)

    def test_empty_target_retains_cash_without_warmup(self):
        args=fixture({'A':[100]})
        args['base_target'].update(quantities={},price_units={});args['histories']={}
        self.assertEqual(volatility20_target20(**args)['target_quantities'],{})
        self.assertEqual(sma20_target(**args)['target_quantities'],{})

    def test_completed_close_requires_reviewed_session_close(self):
        args=fixture({'A':[100]*20});day=args['signal_date']
        args['histories']['A']['closes'][-1]['completed_at']=day+'T09:00:00-05:00'
        args['observed_at']=day+'T09:01:00-05:00'
        with self.assertRaisesRegex(ValueError,'SESSION_NOT_COMPLETED'):sma20_target(**args)
        args['observed_at']=day+'T16:01:00-05:00'
        with self.assertRaisesRegex(ValueError,'COMPLETED_CLOSE'):sma20_target(**args)
        # Caller-reviewed early close is allowed; no fixed16:00 rule.
        args['session_close_times']['closes'][day]=day+'T13:00:00-05:00'
        args['histories']['A']['closes'][-1]['completed_at']=day+'T13:00:00-05:00'
        args['observed_at']=day+'T13:01:00-05:00'
        self.assertEqual(sma20_target(**args)['target_quantities'],{'A':0})

if __name__=='__main__':unittest.main()
