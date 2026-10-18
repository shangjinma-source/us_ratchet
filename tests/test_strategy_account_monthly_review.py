from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from data.strategy_account_runtime import RUNTIME_PATHS,ACCOUNT_ID
from data.strategy_account_monthly_review import StrategyAccountMonthlyReview
from data.strategy_account_market_capture import StrategyAccountMarketCapture
import test_strategy_account_evidence_provider as fixture_module


class MonthlyReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        provider,state,self.now,self.root=fixture_module.ProviderTests().fixture(self.temp.name)
        pins={}
        for name in RUNTIME_PATHS:
            raw=(Path(__file__).resolve().parents[1]/name).read_bytes();path=self.root/name
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
        self.configuration=dict(schema='REAL_STRATEGY_RUNTIME_V1',target_month='2026-11',
            training_manifest=provider.manifest_path,training_sha256=provider.manifest_hash,
            training_closed_at=provider.closed,identity_manifest='identity.json',identity_sha256='1'*64,runtime_pins=pins)
        self.store=StrategyAccountStore(self.root/'data/strategy_account/real_strategy.sqlite3',clock=lambda:self.now[0])
        self.store.initialize(ACCOUNT_ID,operation_id='init')
        for row in state['events']:
            self.append(row['payload'])
        identity=lambda ticker:dict(ticker=ticker,security_id={'AAA':'A','BBB':'B','CCC':'C'}[ticker],
            source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
        class Resolver:
            def __call__(self,ticker):return identity(ticker)
            def _read(self,path,digest):return b'id'
        self.append(dict(event_id='outside-pending',kind='ORDER_OPEN',order_id='outside',security_id='C',
            side='BUY',quantity=1,limit_price='10',fee_per_share='0',identity_evidence=identity('CCC')))
        self.fetched=[]
        def fetch(ticker):
            self.fetched.append(ticker)
            start=int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp());last=start+1800
            return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',
                instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',
                regularMarketPrice=10,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),
                timestamp=[last-60],indicators=dict(quote=[dict(open=[10],high=[11],low=[9],close=[10],volume=[10])]))])))
        self.review=StrategyAccountMonthlyReview(root=self.root,configuration=self.configuration,
            output_directory='review-output',clock=lambda:self.now[0],
            market_capture=StrategyAccountMarketCapture(identity_resolver=Resolver(),fetch=fetch,clock=lambda:self.now[0]),
            action_capture=provider.actions)

    def append(self,event):
        self.store.append(event,expected_revision=self.store.read()['revision'])

    def test_real_provider_reviews_unconfirmed_cash_and_outside_holdings_pending(self):
        state=self.store.read();before=self.store.path.read_bytes()
        self.assertFalse(state['cash_confirmation_valid'])
        with patch('data.strategy_account_evidence_provider.build_target_inputs',side_effect=AssertionError('no inputs')),             patch('data.strategy_account_target_service.StrategyAccountTargetService.select',side_effect=AssertionError('no select')):
            result=self.review.review(expected_revision=state['revision'])
        self.assertEqual(result['securities'],['A','B','C'])
        self.assertEqual(set(self.fetched),{'AAA','BBB','CCC'})
        self.assertEqual(self.store.path.read_bytes(),before)
        self.assertFalse(result['cash_confirmation_valid'])
        self.assertEqual(result['zero_quantities_purpose'],'REVIEW_DOMAIN_ONLY_NOT_TARGET')
        self.assertTrue((self.root/result['review_path']).is_file())
        with self.assertRaisesRegex(ValueError,'REVIEW_ALREADY_ATTEMPTED'):
            self.review.review(expected_revision=state['revision'])

    def test_concurrent_account_revision_rejected_after_capture(self):
        state=self.store.read();original=self.review.provider.actions.capture
        def changed(*args,**kwargs):
            result=original(*args,**kwargs)
            self.append(dict(event_id='concurrent',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'))
            return result
        self.review.provider.actions.capture=changed
        with self.assertRaisesRegex(ValueError,'ACCOUNT_CHANGED_DURING_REVIEW'):
            self.review.review(expected_revision=state['revision'])

    def test_wrong_month_and_existing_output_refused_before_fetch(self):
        self.now[0]=datetime.fromisoformat('2026-12-01T15:00:00+00:00')
        with self.assertRaisesRegex(ValueError,'CURRENT_MONTH_TRAINING_DEPLOYMENT_REQUIRED'):
            self.review.review(expected_revision=self.store.read()['revision'])
        self.assertEqual(self.fetched,[])
        (self.root/'review-output').mkdir()
        with self.assertRaisesRegex(ValueError,'REVIEW_CREATE_ONLY_OUTPUT_EXISTS'):
            self.review.review(expected_revision=self.store.read()['revision'])


if __name__=='__main__':unittest.main()

