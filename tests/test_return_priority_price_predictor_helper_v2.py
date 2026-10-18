from copy import deepcopy
import unittest
from backtest import return_priority_price_predictor_research as subject


class ChangedHelpers(unittest.TestCase):
    def test_projection_rejects_all_short_nonnumeric_or_nonpositive_coordinates(self):
        model=dict(intercept=.1,coefficients=[.1]*4,feature_means=[0.]*4,feature_scales=[1.]*4)
        with self.assertRaises(ValueError):subject.project_feature_vector(model,[0.])
        for key in ('coefficients','feature_means','feature_scales'):
            for value in ([0.],None,[0.,0.,0.,True],[0.,0.,0.,float('nan')]):
                altered=deepcopy(model);altered[key]=value
                with self.assertRaises(ValueError):subject.project_feature_vector(altered,[0.]*4)
        for intercept in (True,float('nan'),float('inf'),'1'):
            altered=deepcopy(model);altered['intercept']=intercept
            with self.assertRaises(ValueError):subject.project_feature_vector(altered,[0.]*4)
        for scale in (0.,-1.):
            altered=deepcopy(model);altered['feature_scales'][0]=scale
            with self.assertRaises(ValueError):subject.project_feature_vector(altered,[0.]*4)
        projection,reasons=subject.project_feature_vector(model,[1.,2.,3.,4.])
        self.assertEqual(reasons,[])
        self.assertAlmostEqual(projection['predicted_log_change_21'],1.1)

    def test_indices_valueerror_and_unmatured_label_does_not_touch_future(self):
        prices=[100.]*150
        for index in (-1,150,200,True):
            with self.assertRaises(ValueError):subject.features_at(prices,index)
        for anchor,cutoff in ((-1,149),(10,-1),(True,149),(0,160),(130,151)):
            with self.assertRaises(ValueError):subject.mature_label(prices,anchor,cutoff)
        class Untouchable:
            def __len__(self):raise AssertionError('No future length query')
            def __getitem__(self,index):raise AssertionError('No future value read')
        label,reasons=subject.mature_label(Untouchable(),140,149)
        self.assertIsNone(label)
        self.assertEqual(reasons,['LABEL_END_NOT_MATURE_AT_CUTOFF'])


if __name__=='__main__':unittest.main()
