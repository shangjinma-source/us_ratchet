import copy
import unittest
import pandas as pd
from test_ndx_conditional_panel_incremental_plan_research import fixture,build
from backtest import ndx_conditional_panel_incremental_plan_research as m


class IncrementalIndependentTests(unittest.TestCase):
    def test_intraday_duplicate_session_is_not_126_sessions(self):
        a,b=fixture(4),fixture(5)
        for value in (a,b):
            index=list(value['returns'].index);index[1]=index[0]+pd.Timedelta(hours=1)
            value['returns'].index=pd.DatetimeIndex(index)
            value['panel_content_sha256']=m.core.panel_digest(value)
        with self.assertRaises(ValueError):build(a,b)

    def test_new_only_matrix_change_never_inherits_old_task(self):
        a,b=fixture(4),fixture(5)
        b['returns'].iloc[0,-1]=.02;b['panel_content_sha256']=m.core.panel_digest(b)
        result=build(a,b)
        self.assertEqual(result['input_equivalent_old_count'],2)
        for row in result['tasks']:
            if any(r['ticker']=='T4' for r in row['task']['selected'].values()):self.assertFalse(row['input_equivalent_to_old_task'])
            self.assertFalse(row['result_reused'])

    def test_cutoff_and_coordinate_assumption_change_fail_closed(self):
        a,b=fixture(4),fixture(5)
        for kind in ('cutoff','assumption'):
            bad=copy.deepcopy(b)
            if kind=='cutoff':bad['cutoff']='2026-09-16'
            else:bad['observed_provenance_and_missing'][0]['coordinate_assumption']['id']=999
            bad['panel_content_sha256']=m.core.panel_digest(bad)
            with self.subTest(kind=kind),self.assertRaises(ValueError):build(a,bad)


if __name__=='__main__':unittest.main()
