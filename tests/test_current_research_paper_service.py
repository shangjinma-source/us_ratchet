from copy import deepcopy
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import data.current_research_paper_service as module
from data.current_quantity_portfolio_research import CurrentQuantityPortfolioResearch


class PaperServiceTests(unittest.TestCase):
    def rebuild(self, plan, *, market, decision=None, active=None, revision=None, research_id=None):
        from data.current_research_limit_plan import build_current_research_limit_plan
        c = deepcopy(plan['causal_inputs'])
        snapshot = c['research_snapshot']
        if research_id is not None:
            snapshot['research_id'] = research_id
        snapshot.pop('market_session', None)
        if market is not None:
            snapshot['market_session'] = market
        decision = decision or c['decision_date']
        active = active or c['active_date']
        return build_current_research_limit_plan(research_snapshot=snapshot,
            quotes=[dict(q, security_id=sid, as_of=decision) for sid, q in c['quotes'].items()],
            available_cash=c['available_cash'], shares=c['shares'], account_revision=revision or c['account_revision'],
            decision_date=decision, active_date=active, calendar=[decision, active],
            strategy_version=c['strategy_version'], target_quantities=c['target_quantities'])

    def test_response_rejects_missing_or_wrong_market_session(self):
        from data.current_research_fill_ledger import initialize_paper_ledger
        preview = self.service.preview('a'*24)
        market = preview['market_session']
        invalid = [None, dict(market, date='2026-10-15'), dict(market, timezone='UTC'),
            dict(market, open_at='2026-10-14T09:30:00'), dict(market, open_at=None),
            dict(market, open_at='2026-10-14T09:30:00+00:00'),
            dict(market, close_at='2026-10-15T16:00:00-04:00'),
            dict(market, close_at=market['open_at'])]
        for value in invalid:
            with self.subTest(market=value):
                plan = self.rebuild(preview['plan'], market=value)
                state = initialize_paper_ledger(plan, 'synthetic')
                with self.assertRaisesRegex(ValueError, '交易时段'):
                    self.service._response(state)

    def test_initial_preview_restores_current_rolled_plan(self):
        from data.current_research_paper_store import ResearchPaperStore
        initial = self.start()
        store = ResearchPaperStore(self.root/'paper')
        state = store.read(initial['account_id'])
        state = store.record_order_event(state['account_id'], dict(event_id='close-old', mode='PAPER_MANUAL_FILL',
            event_type='CANCEL', plan_id=state['active_plan_id'], order_id=state['plan']['orders'][0]['order_id'],
            expected_revision=state['revision']))
        market = dict(initial['market_session'], date='2026-10-15', open_at='2026-10-15T09:30:00-04:00', close_at='2026-10-15T16:00:00-04:00')
        plan = self.rebuild(initial['plan'], market=market, decision='2026-10-14', active='2026-10-15', revision=state['revision'], research_id='c'*24)
        state = store.activate_plan(state['account_id'], plan, dict(event_id='activate-next', mode='PAPER_MANUAL_FILL',
            event_type='ACTIVATE_PLAN', plan_id=plan['plan_id'], expected_revision=state['revision']))
        restored = self.service.preview('a'*24)
        self.assertEqual(restored, self.service.account(initial['account_id']))
        self.assertEqual(restored['plan'], plan)
        self.assertEqual(restored['review']['plan_id'], plan['plan_id'])
        self.assertEqual(restored['market_session'], market)
        self.assertEqual(restored['genesis_plan_id'], initial['plan']['plan_id'])
        self.assertEqual(restored['genesis_research_id'], 'a'*24)
        self.assertEqual(restored['plan']['research_id'], 'c'*24)
        self.assertEqual(restored['review']['research_id'], 'c'*24)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        directory = self.root / module.RAW_DIRECTORY
        directory.mkdir(parents=True)
        entries = []
        self.now = datetime.fromisoformat('2026-10-14T10:00:00-04:00')
        for ticker in ['AAA', 'QQQ']:
            raw = json.dumps({'chart': {'result': [{
                'timestamp': [1791898200],
                'meta': {'symbol': ticker, 'currency': 'USD', 'instrumentType': 'ETF' if ticker == 'QQQ' else 'EQUITY',
                         'exchangeTimezoneName': 'America/New_York', 'regularMarketTime': 1791921601,
                         'regularMarketPrice': 10.00, 'currentTradingPeriod': {'regular': {'start': 1791984600, 'end': 1792008000}}},
                'indicators': {'quote': [{'open': [10], 'high': [11], 'low': [9], 'close': [10.00000001]}]}}]}}).encode()
            compressed = gzip.compress(raw)
            digest = hashlib.sha256(compressed).hexdigest()
            receipt = json.dumps({'http_status': 200, 'ticker': ticker, 'raw_sha256': digest}).encode()
            (directory / (ticker + '.response.bin')).write_bytes(compressed)
            (directory / (ticker + '.receipt.json')).write_bytes(receipt)
            observation = json.dumps(dict(ticker=ticker, receipt_sha256=hashlib.sha256(receipt).hexdigest(), decoded_sha256=hashlib.sha256(raw).hexdigest())).encode()
            (directory / (ticker + '.decoded.json')).write_bytes(observation)
            entries.append(dict(ticker=ticker, raw_sha256=digest, decoded_sha256=hashlib.sha256(observation).hexdigest(), receipt_sha256=hashlib.sha256(receipt).hexdigest()))
        index = json.dumps({'entries': entries}).encode()
        (directory / 'completion_index_104.json').write_bytes(index)
        patcher = patch.object(module, 'INDEX_SHA', hashlib.sha256(index).hexdigest())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.snap = dict(research_id='a'*24, status='AVAILABLE', as_of='2026-10-13', sources={'source':'b'*64},
            stocks=[dict(ticker='AAA', security_id='A', units=9, close=10.00000001)], budget_identity_exact={'entered_cash':'105/1'})
        self.service = module.CurrentResearchPaperService(root=self.root, directory=self.root/'paper', snapshot=lambda _:deepcopy(self.snap), clock=lambda:self.now)

    def start(self):
        preview = self.service.preview('a'*24)
        return self.service.start('a'*24, preview['plan']['plan_id'])

    def test_preview_nonseed_budget_frozen_units_and_no_write(self):
        result = self.service.preview('a'*24)
        self.assertFalse((self.root/'paper').exists())
        self.assertEqual(result['plan']['available_cash'], '105')
        self.assertEqual(result['plan']['target_quantities'], {'A':9})
        self.assertEqual(result['plan']['reserved_cash'], '90')
        self.assertIsNone(result['review'])
        with self.assertRaises(ValueError): self.service.start('a'*24, 'wrong')
        self.assertFalse((self.root/'paper').exists())
        started = self.start()
        self.assertEqual(started, self.start())
        self.assertEqual(self.service.preview('a'*24)['review'], started['review'])

    def test_source_tamper_and_unsupported_date_fail_closed(self):
        self.snap['as_of'] = '2026-10-14'
        with self.assertRaises(ValueError): self.service.preview('a'*24)
        self.snap['as_of'] = '2026-10-13'
        (self.root/module.RAW_DIRECTORY/'AAA.response.bin').write_bytes(b'bad')
        with self.assertRaises(ValueError): self.service.preview('a'*24)
        self.assertFalse((self.root/'paper').exists())

    def test_clock_revision_fill_and_expiry(self):
        response = self.start(); account = response['account_id']; plan = response['plan']
        event = dict(event_id='fill1', mode='PAPER_MANUAL_FILL', plan_id=plan['plan_id'], order_id=plan['orders'][0]['order_id'], qty=1, price='9', fees='0', session='2026-10-14', expected_revision=response['review']['revision'])
        self.now = datetime.fromisoformat('2026-10-13T16:00:00-04:00')
        with self.assertRaises(ValueError): self.service.fill(account,event)
        self.now = datetime.fromisoformat('2026-10-14T09:00:00-04:00')
        with self.assertRaises(ValueError): self.service.fill(account,event)
        self.now = datetime.fromisoformat('2026-10-14T10:00:00-04:00')
        filled = self.service.fill(account,event)
        self.assertEqual(filled['review']['cash'],'96')
        self.assertEqual(filled['market_session'],response['market_session'])
        self.assertEqual(self.service.fill(account,event),filled)
        expiry = dict(event_id='expire',mode='PAPER_MANUAL_FILL',event_type='EXPIRE',plan_id=plan['plan_id'],order_id=plan['orders'][0]['order_id'],completed_session='2026-10-14',expected_revision=filled['review']['revision'])
        with self.assertRaises(ValueError): self.service.order(account,expiry)
        self.now = datetime.fromisoformat('2026-10-14T16:00:00-04:00')
        expired = self.service.order(account,expiry)
        self.assertEqual(expired['review']['reserved_cash'],'0')

    def test_snapshot_no_search_deepcopy_and_eviction(self):
        source = CurrentQuantityPortfolioResearch(search=lambda **_: self.fail('search called'))
        source._load = lambda: None
        source.results['a'*24] = deepcopy(self.snap)
        value = source.snapshot('a'*24)
        value['stocks'].clear()
        self.assertEqual(len(source.results['a'*24]['stocks']),1)
        source.results.clear()
        with self.assertRaises(Exception): source.snapshot('a'*24)

    def test_market_review_is_read_only_and_does_not_use_prior_day_as_touch(self):
        response = self.start()
        database = self.root/'paper'/'research_paper.sqlite3'
        before = database.read_bytes()
        reviewed = self.service.review(response['account_id'])
        self.assertEqual(reviewed['review'], response['review'])
        self.assertEqual(reviewed['market_review']['observed_through'], '2026-10-13')
        self.assertEqual(reviewed['market_review']['orders'][0]['observed_touch'], 'UNKNOWN')
        self.assertEqual(reviewed['market_review']['generated_fill_count'], 0)
        self.assertEqual(database.read_bytes(), before)
        self.now = datetime.fromisoformat('2026-10-13T12:00:00-04:00')
        with self.assertRaises(ValueError): self.service.review(response['account_id'])
        self.assertEqual(database.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
