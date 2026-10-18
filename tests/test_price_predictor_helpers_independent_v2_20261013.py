"""Only changed-helper boundaries plus fresh prefix experiment; no old test replay."""
from pathlib import Path
from datetime import date,timedelta
from copy import deepcopy
import hashlib,importlib.util,math,unittest
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'backtest/return_priority_price_predictor_research.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='1c3275c590475691fa40853b0be3e8e0607f221d34118a14b26ca80df3eeecee'
spec=importlib.util.spec_from_file_location('independent_predictor_v2',SOURCE);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


class HelpersV2(unittest.TestCase):
    def test_changed_public_helpers_reject_missing_dimensions_and_bad_types_before_reads(self):
        model=dict(intercept=1.5,coefficients=[1.,2.,3.,4.],feature_means=[1.,1.,1.,1.],feature_scales=[1.,2.,3.,4.]);vector=[2.,2.,2.,2.]
        correct,reasons=s.project_feature_vector(model,tuple(vector));self.assertEqual(reasons,[]);self.assertEqual(correct['predicted_log_change_21'],5.5)
        for values in ([],[2.],[2.]*3,[2.]*5,[2.,2.,True,2.],[2.,2.,float('nan'),2.],[2.,2.,float('inf'),2.]):
            with self.subTest(vector=values),self.assertRaises(ValueError):s.project_feature_vector(model,values)
        for key in ('coefficients','feature_means','feature_scales'):
            for values in ([1.]*3,[1.]*5,[1.,True,1.,1.],[1.,float('nan'),1.,1.]):
                changed=deepcopy(model);changed[key]=values
                with self.subTest(key=key,values=values),self.assertRaises(ValueError):s.project_feature_vector(changed,vector)
        for scale in (0.,-1.):
            changed=deepcopy(model);changed['feature_scales'][2]=scale
            with self.assertRaises(ValueError):s.project_feature_vector(changed,vector)
        for intercept in (True,float('nan'),float('inf')):
            changed=deepcopy(model);changed['intercept']=intercept
            with self.assertRaises(ValueError):s.project_feature_vector(changed,vector)
        for index in (True,-1,1.,147):
            with self.assertRaises(ValueError):s.features_at([100.]*147,index)
        for anchor,cutoff in ((True,146),(120,True),(-1,146),(147,146),(0.,146),(126,147)):
            with self.assertRaises(ValueError):s.mature_label([100.]*147,anchor,cutoff)
        class UntouchedFuture:
            def __len__(self):raise AssertionError('Unmatured label inspected series length')
            def __getitem__(self,index):raise AssertionError('Unmatured label read future price')
        label,reasons=s.mature_label(UntouchedFuture(),137,147);self.assertIsNone(label);self.assertEqual(reasons,['LABEL_END_NOT_MATURE_AT_CUTOFF'])
        for bad in (True,float('nan'),float('inf'),0.,-3.):
            values=[100.]*148;values[146]=bad
            with self.assertRaises(ValueError):s.features_at(values,147)
            with self.assertRaises(ValueError):s.mature_label(values,126,147)

    def test_new_curved_series_whole_prefix_output_unchanged_by_future_poison(self):
        calendar=[(date(2023,4,1)+timedelta(days=i)).isoformat()for i in range(245)]
        prices={f'CURVE{k}':[71*math.exp(.000003*i*i/(k+1)+.0001*k*i)for i in range(245)]for k in range(8)}
        prices['CURVE7'][180]=None
        a=s.fit_predict_price_projection(calendar=calendar,prices_by_ticker=prices,cutoff_index=231,declared_price_basis='CONDITIONAL_NEW_CURVE_SYNTHETIC')
        modified=deepcopy(prices)
        for values in modified.values():values[232:]=[True,float('nan'),float('inf'),False,None,-1,0,None,True,float('nan'),float('inf'),0,-1]
        altered_calendar=list(calendar);altered_calendar[232:]=['unread-future']*13
        b=s.fit_predict_price_projection(calendar=altered_calendar,prices_by_ticker=modified,cutoff_index=231,declared_price_basis='CONDITIONAL_NEW_CURVE_SYNTHETIC')
        self.assertEqual(a,b);self.assertIsNotNone(a['model']);self.assertEqual(a['training_decision_anchors'],[210,189,168,147,126,105]);self.assertEqual(len(a['forecasts']),8)
        self.assertTrue(all(row['label_end_index']<=231 for row in a['training_examples']));self.assertGreaterEqual(len(a['training_examples']),30)
        self.assertTrue(any('MISSING' in reason for row in a['blocked_training_examples']for reason in row['reasons']))
        self.assertFalse(a['prediction_uses_future_prices']);self.assertFalse(a['predictive_alpha_causally_validated']);self.assertFalse(a['current_adoption_allowed'])


if __name__=='__main__':unittest.main()
