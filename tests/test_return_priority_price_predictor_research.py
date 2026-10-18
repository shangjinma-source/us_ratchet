from copy import deepcopy
from datetime import date,timedelta
import math
import unittest
from backtest import return_priority_price_predictor_research as subject


def fixture():
    calendar=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(325)]
    prices={f'T{i}':[100*math.exp(.0005*j+(.008+i*.0001)*math.sin(j/11+i)) for j in range(325)] for i in range(10)}
    return calendar,prices


class Predictor(unittest.TestCase):
    def test_independent_feature_and_small_ridge_oracles(self):
        logvalues=[.001*i+.0001*(i%3) for i in range(160)]
        prices=[100*math.exp(value) for value in logvalues]
        vector,reasons=subject.features_at(prices,150)
        self.assertEqual(reasons,[])
        expected=[logvalues[150]-logvalues[150-period] for period in (21,63,126)]
        changes=[logvalues[i]-logvalues[i-1] for i in range(130,151)]
        mean=sum(changes)/21
        expected.append(math.sqrt(sum((value-mean)**2 for value in changes)/20))
        for observed,value in zip(vector,expected):self.assertAlmostEqual(observed,value,places=13)
        model=subject.fit_registered_ridge([[-1.,7.,7.,7.],[1.,7.,7.,7.]],[0.,2.])
        self.assertEqual(model['feature_means'],[0.,7.,7.,7.])
        self.assertEqual(model['feature_scales'],[1.,1.,1.,1.])
        self.assertAlmostEqual(model['intercept'],1.)
        self.assertAlmostEqual(model['coefficients'][0],2/3)
        self.assertEqual(model['coefficients'][1:],[0.,0.,0.])
        self.assertFalse(model['intercept_penalized'])

    def test_future_values_do_not_affect_features_normalizer_model_or_predictions(self):
        calendar,prices=fixture()
        expected=subject.fit_predict_price_projection(calendar=calendar,prices_by_ticker=prices,cutoff_index=300,declared_price_basis='CONDITIONAL_PROVIDER_CLOSE_UNVERIFIED')
        altered=deepcopy(prices)
        for ticker in altered:altered[ticker][301:]=[float('nan'),True,None,float('inf')]*6
        observed=subject.fit_predict_price_projection(calendar=calendar,prices_by_ticker=altered,cutoff_index=300,declared_price_basis='CONDITIONAL_PROVIDER_CLOSE_UNVERIFIED')
        self.assertEqual(expected,observed)
        self.assertEqual(len(expected['training_examples']),60)
        self.assertTrue(all(row['label_end_index']<=300 for row in expected['training_examples']))
        self.assertEqual(expected['model_parameters_authority'],'ROOT_RESEARCH_METHOD_NOT_USER_PREFERENCE')

    def test_started_but_unmatured_label_is_never_read_or_fit(self):
        prices=[100.]*190
        label,reasons=subject.mature_label(prices,180,189)
        self.assertIsNone(label)
        self.assertEqual(reasons,['LABEL_END_NOT_MATURE_AT_CUTOFF'])
        calendar,channels=fixture()
        result=subject.fit_predict_price_projection(calendar=calendar,prices_by_ticker=channels,cutoff_index=189,declared_price_basis='CONDITIONAL_NOMINAL_ASSUMPTION')
        self.assertEqual(len(result['training_examples']),30)
        self.assertEqual(result['distinct_used_training_anchors'],[126,147,168])
        self.assertTrue(all(row['label_end_index']<=189 for row in result['training_examples']))

    def test_missing_prices_preserve_ticker_and_common_index_nan_bool_rejected(self):
        calendar,prices=fixture();prices['T0'][299]=None
        result=subject.fit_predict_price_projection(calendar=calendar,prices_by_ticker=prices,cutoff_index=300,declared_price_basis='CONDITIONAL_CLOSE')
        row=next(row for row in result['forecasts'] if row['ticker']=='T0')
        self.assertEqual(row['status'],'BLOCKED')
        self.assertIn('MISSING_FEATURE_PRICE_AT_COMMON_INDEX_299',row['reasons'])
        self.assertEqual(len(result['forecasts']),10)
        for value in (float('nan'),True,float('inf'),0.,-1.):
            altered=deepcopy(prices);altered['T1'][299]=value
            with self.assertRaises(ValueError):subject.fit_predict_price_projection(calendar=calendar,prices_by_ticker=altered,cutoff_index=300,declared_price_basis='CONDITIONAL_CLOSE')
        with self.assertRaises(ValueError):subject.fit_predict_price_projection(calendar=calendar,prices_by_ticker=prices,cutoff_index=True,declared_price_basis='CONDITIONAL_CLOSE')


if __name__=='__main__':unittest.main()
