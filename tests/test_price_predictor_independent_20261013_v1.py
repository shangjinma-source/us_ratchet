"""Fresh small predictor hand oracles and prefix boundaries; no real fitting."""
from pathlib import Path
from datetime import date,timedelta
from fractions import Fraction as F
from copy import deepcopy
import hashlib,importlib.util,math,unittest
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'backtest/return_priority_price_predictor_research.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='e9b851a4ca85dfb010ccd4bf880612863cc98419e7838f81e011694adeb1863e'
spec=importlib.util.spec_from_file_location('independent_predictor',SOURCE);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


class IndependentPredictor(unittest.TestCase):
    def test_alternating_log_features_and_four_row_ridge_unpenalized_intercept(self):
        increments=[F(1,100)if i%2 else F(-1,50)for i in range(1,201)];log=[F(0)]
        for value in increments:log.append(log[-1]+value)
        prices=[97*math.exp(float(v))for v in log];features,reasons=s.features_at(prices,200)
        expected=[log[200]-log[200-k]for k in (21,63,126)];recent=increments[-21:];mean=sum(recent,F(0))/21;variance=sum((r-mean)**2 for r in recent)/20
        self.assertEqual(reasons,[])
        for got,want in zip(features[:3],expected):self.assertAlmostEqual(got,float(want),places=13)
        self.assertAlmostEqual(features[3],math.sqrt(float(variance)),places=13)
        model=s.fit_registered_ridge([[-3.,9.,-4.,7.],[-1.,9.,-4.,7.],[1.,9.,-4.,7.],[3.,9.,-4.,7.]],[-5.,-1.,3.,7.])
        self.assertEqual(model['feature_means'],[0.,9.,-4.,7.]);self.assertAlmostEqual(model['feature_scales'][0],math.sqrt(5))
        self.assertEqual(model['feature_scales'][1:],[1.,1.,1.]);self.assertAlmostEqual(model['intercept'],1.)
        self.assertAlmostEqual(model['coefficients'][0],8/math.sqrt(5));self.assertEqual(model['coefficients'][1:],[0.,0.,0.]);self.assertFalse(model['intercept_penalized'])

    def test_entire_early_output_unchanged_by_future_nan_bool_dates_and_missing_not_compressed(self):
        calendar=[(date(2025,1,1)+timedelta(days=i)).isoformat()for i in range(280)]
        prices={f'X{k}':[100*math.exp(.0002*i*(k+1)+(.0004 if i%3==0 else -.0002)*(k+1))for i in range(280)]for k in range(12)}
        a=s.fit_predict_price_projection(calendar=calendar,prices_by_ticker=prices,cutoff_index=252,declared_price_basis='CONDITIONAL_SYNTHETIC')
        altered=deepcopy(prices)
        for values in altered.values():values[253:]=[float('nan'),True,float('inf'),None]*6+[False,0,-1]
        future_dates=list(calendar);future_dates[253:]=[None]*27
        b=s.fit_predict_price_projection(calendar=future_dates,prices_by_ticker=altered,cutoff_index=252,declared_price_basis='CONDITIONAL_SYNTHETIC')
        self.assertEqual(a,b);self.assertEqual(len(a['training_examples']),72);self.assertEqual(a['training_decision_anchors'],[231,210,189,168,147,126]);self.assertTrue(all(x['label_end_index']<=252 for x in a['training_examples']))
        class Unreadable:
            def __getitem__(self,index):raise AssertionError('Unmatured label touched price')
        label,reasons=s.mature_label(Unreadable(),240,252);self.assertIsNone(label);self.assertEqual(reasons,['LABEL_END_NOT_MATURE_AT_CUTOFF'])
        missing=deepcopy(prices);missing['X0'][251]=None;c=s.fit_predict_price_projection(calendar=calendar,prices_by_ticker=missing,cutoff_index=252,declared_price_basis='CONDITIONAL_SYNTHETIC')
        x=next(row for row in c['forecasts']if row['ticker']=='X0');self.assertEqual(x['status'],'BLOCKED');self.assertIn('MISSING_FEATURE_PRICE_AT_COMMON_INDEX_251',x['reasons']);self.assertEqual(c['cutoff_index'],252);self.assertEqual(len(c['forecasts']),12)

    def test_public_projection_short_vector_must_refuse_instead_of_silent_zip(self):
        model=s.fit_registered_ridge([[-3.,9.,-4.,7.],[-1.,9.,-4.,7.],[1.,9.,-4.,7.],[3.,9.,-4.,7.]],[-5.,-1.,3.,7.])
        # A partial vector is missing three registered features. It must not forecast.
        with self.assertRaises(ValueError):s.project_feature_vector(model,[0.])


if __name__=='__main__':unittest.main()
