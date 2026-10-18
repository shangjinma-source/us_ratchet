import hashlib
import json
from datetime import datetime
from copy import deepcopy
import unittest

from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_fill_ledger import initialize_paper_ledger, review_paper_ledger
from data.current_research_paper_charts import CurrentResearchPaperCharts


class PaperChartTests(unittest.TestCase):
    def setUp(self):
        self.path='synthetic/AAA.response.bin'
        self.raw=json.dumps({'chart':{'result':[{'meta':dict(symbol='AAA',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),
            'timestamp':[int(datetime.fromisoformat('2030-01-'+d+'T16:00:00-05:00').timestamp()) for d in ['01','02','03']],
            'indicators':{'quote':[dict(open=[9,10,100],high=[11,12,110],low=[8,9,90],close=[10,11,105],volume=[1,2,3])]}}], 'error':None}}).encode()
        digest=hashlib.sha256(self.raw).hexdigest()
        plan=build_current_research_limit_plan(research_snapshot=dict(research_id='a'*24,as_of='2030-01-01',stocks=[dict(security_id='a',ticker='AAA')],source_hashes={self.path:digest}),
            quotes=[dict(security_id='a',price='11',as_of='2030-01-02',price_kind='DECLARED_DECIMAL_REFERENCE',price_basis='SYNTHETIC',source_references=[self.path])],
            available_cash='100',shares={},account_revision='r',decision_date='2030-01-02',active_date='2030-01-03',calendar=['2030-01-02','2030-01-03'],strategy_version='test',target_quantities={'a':5})
        self.state=initialize_paper_ledger(plan,'synthetic')
        owner=self
        class Base:
            def _read_account(self, account):
                if account!='synthetic':raise ValueError('account')
                review_paper_ledger(owner.state)
                return deepcopy(owner.state)
            def _read_pin(self,path,sha):
                if path!=owner.path or hashlib.sha256(owner.raw).hexdigest()!=sha:raise ValueError('pin')
                return owner.raw
        self.service=CurrentResearchPaperCharts(Base())

    def test_cutoff_daily_weekly_monthly_and_identity(self):
        for interval in ['day','week','month']:
            result=self.service.bars('synthetic',self.state['plan']['plan_id'],'a',interval)
            self.assertEqual(result['daily_as_of'],'2030-01-02')
            self.assertEqual(result['bars'][-1]['close'],11)
            self.assertEqual(len(result['bars']),2 if interval=='day' else 1)
            self.assertTrue(result['execution_blocked'])
        for plan,sid,period in [('wrong','a','day'),(self.state['plan']['plan_id'],'other','day'),(self.state['plan']['plan_id'],'a','year')]:
            with self.assertRaises(ValueError):self.service.bars('synthetic',plan,sid,period)

    def test_changed_source_rejected_no_fallback(self):
        self.raw+=b' '
        with self.assertRaisesRegex(ValueError,'pin'):self.service.bars('synthetic',self.state['plan']['plan_id'],'a')


if __name__=='__main__':unittest.main()
