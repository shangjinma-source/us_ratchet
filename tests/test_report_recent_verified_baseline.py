from copy import deepcopy
from fractions import Fraction as F
import unittest
from scripts.report_recent_verified_baseline import build_report, drawdown


class ReportTests(unittest.TestCase):
    def fixture(self):
        plans=[{'decision_date':f'{y}-{m:02d}-28'} for y in (2021,2022,2023) for m in range(1,13) if (y,m)!=(2023,12)]
        plans.insert(0,{'decision_date':'2020-12-31'})
        a={'monthly_inputs':plans,'session_dates':['2020-12-31','2021-12-31','2022-12-30','2023-12-29']}
        b={'status':'COMPLETE','total_return':'1/5','daily_ledger':[{'date':day,'equity':equity} for day,equity in zip(a['session_dates'][1:],['110','88','120'])]}
        r={'status':'REVIEWED_ORDINARY_DIVIDEND_ACCOUNT','final_equity':'120','maximum_drawdown':'1/5','costs_checked':True,'risk_provider_certified':True,'selection_proof_checked':True,'selection_proofs_checked':36,'expected_selection_proofs':36}
        return b,r,a

    def test_full_return_and_recovery(self):
        b,r,a=self.fixture();result=build_report(b,r,a,initial_equity='100')
        self.assertEqual(result['drawdown']['recovery_date'],'2023-12-29')
        self.assertEqual(result['annual'][1]['return_fraction'],'-1/5')
        self.assertAlmostEqual(result['cagr'],1.2**(365.25/result['calendar_days'])-1)

    def test_partial_rejected(self):
        b,r,a=self.fixture();b['status']='BLOCKED'
        with self.assertRaises(ValueError):build_report(b,r,a,initial_equity='100')

    def test_missing_session_and_wrong_proof_rejected(self):
        for kind in ('session','proof','external_flow'):
            b,r,a=self.fixture()
            if kind=='session':b['daily_ledger'].pop(1)
            elif kind=='proof':r['final_equity']='121'
            else:b['daily_ledger'][0]['external_flow']='10'
            with self.assertRaises(ValueError):build_report(b,r,a,initial_equity='100')


if __name__=='__main__':unittest.main()
