from copy import deepcopy
from hashlib import sha256
from tempfile import TemporaryDirectory
from datetime import datetime,timedelta
from pathlib import Path
import json
import unittest
from unittest.mock import patch
from core.strategy_account_ledger import canonical,create_account
from data.strategy_prospective_paper_unit_review_v1 import review_prospective_units,review_prospective_execution_sources,CODE_PATHS
from data.strategy_prospective_paper_source_capture_v1 import capture_prospective_sources
from data.strategy_account_unit_review import review_interval
import test_strategy_prospective_paper_source_capture_v1 as fixtures
import test_strategy_prospective_paper_settlement_v1 as settlement_fixture
from data.strategy_prospective_paper_settlement_v1 import produce_prospective_settlement
from backtest.current_strategy_prospective_paper_book_v1 import transact
from test_strategy_paper_execution_preview_v1 import capture
import test_current_strategy_prospective_paper_book_v1 as book_fixture
from data.strategy_account_identity import PinnedStrategyIdentity


class PaperUnitTests(unittest.TestCase):
    def setup(self,folder,mode=None):
        with patch.object(fixtures,'CODE_PATHS',fixtures.CODE_PATHS|CODE_PATHS):
            source=fixtures.SourceCaptureTests().arguments(folder)
        if mode=='split':
            def fetch(ticker,start,end):
                return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={'splits':{'1':{'date':1}}})]))))
            source['action_fetch']=fetch
        result=capture_prospective_sources(**source)
        return dict(book=source['book'],authority=source['authority'],admitted_decisions={},securities=source['securities'],
            market_capture=result['market_capture'],action_package=result['action_capture'],training_manifest_sha256='1'*64,
            historical_search_arguments_sha256='2'*64,historical_price_basis='saved-conditional',
            training_closed_at=source['window_start'],clock=source['clock'])

    def test_same_actual_captured_sources_match_current_real_unit_rules(self):
        with TemporaryDirectory() as folder:
            args=self.setup(folder);before=deepcopy(args['book'])
            paper=review_prospective_units(**args)
            values={k:args[k] for k in ('securities','action_package','training_manifest_sha256','historical_search_arguments_sha256','historical_price_basis','training_closed_at')}
            marks=args['market_capture']['marks']
            real=review_interval(state=create_account('reference-unit-fixture-only'),marks=marks,marks_sha256=sha256(canonical(marks)).hexdigest(),now=args['clock']().isoformat(),**values)
            real['account_revision']=paper['account_revision']
            self.assertEqual(paper,real);self.assertEqual(args['book'],before)
            combined=review_prospective_execution_sources(**args)
            self.assertEqual(combined['unit_review'],paper)
            self.assertTrue(set(paper['source_references'])<=set(combined['market_capture']['source_hashes']))

    def test_unit_event_and_mark_value_forgery_fail_closed(self):
        for mode in ('split','mark'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args=self.setup(folder,mode)
                if mode=='mark':args['market_capture']['marks']['B']['price']='1'
                with self.assertRaisesRegex(ValueError,'KNOWN_UNIT_CHANGE|MARK_VALUE'):
                    review_prospective_units(**args)

    def test_actual_paper_fill_history_retains_cash_rights_review(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'settle').mkdir();(root/'sources').mkdir()
            with patch.object(settlement_fixture,'CODE_PATHS',settlement_fixture.CODE_PATHS|CODE_PATHS|fixtures.CODE_PATHS):
                settled=settlement_fixture.setup(root/'settle',production_halt=True)
            result=produce_prospective_settlement(**settled);e=result['evidence']
            evidence={result['settlement_sha256']:result['settlement_bytes']}
            book=transact(settled['book'],dict(kind='SETTLE',operation_id='filled',expected_revision=settled['book']['revision'],
                minutes=e['minutes'],observed_through=e['observed_through'],settlement_bytes=result['settlement_bytes'].decode()),
                authority=settled['authority'],admitted_decisions=settled['admitted_decisions'],admitted_settlements=evidence,clock=lambda:settlement_fixture.NOW)
            source=fixtures.SourceCaptureTests().arguments(root/'sources')
            now=datetime.fromisoformat('2026-11-04T15:00:10+00:00');raw,_=capture(book,now)
            source.update(book=book,authority=settled['authority'],admitted_decisions=settled['admitted_decisions'],admitted_settlements=evidence,
                clock=lambda:now,market_fetch=lambda ticker:raw['files'][ticker+'.raw'])
            def dividend(ticker,start,end):
                return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={'dividends':{'known':{'amount':1}}})]))))
            source['action_fetch']=dividend
            sources=capture_prospective_sources(**source)
            with self.assertRaisesRegex(ValueError,'POSSIBLE_CASH_RIGHTS_REQUIRES_REVIEW'):
                review_prospective_units(book=book,authority=settled['authority'],admitted_decisions=settled['admitted_decisions'],admitted_settlements=evidence,
                    securities=source['securities'],market_capture=sources['market_capture'],action_package=sources['action_capture'],
                    training_manifest_sha256='1'*64,historical_search_arguments_sha256='2'*64,historical_price_basis='saved-conditional',
                    training_closed_at=source['window_start'],clock=lambda:now)

    def test_final_clock_rollback_and_expiry_rejected(self):
        for delta in (-1,121):
            with self.subTest(delta=delta),TemporaryDirectory() as folder:
                args=self.setup(folder);now=args['clock']();ticks=iter([now,now+timedelta(seconds=delta)])
                args['clock']=lambda:next(ticks)
                with self.assertRaises(ValueError):review_prospective_units(**args)

    def test_omitted_pending_held_and_fully_sold_history_rejected_by_both_wrappers(self):
        for mode in ('pending','held','sold'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                f=book_fixture.ProspectiveBookTests()
                with patch.object(book_fixture,'CODE_PATHS',book_fixture.CODE_PATHS|CODE_PATHS|fixtures.CODE_PATHS):f.setUp()
                book=f.accept(f.book)
                if mode!='pending':book=f.fill(book)
                if mode=='sold':
                    raw=f.decision(book,[dict(security_id='A',side='SELL',quantity=10,limit_price='100')],day='2026-11-02',effective={'A':0})
                    book=f.apply(book,dict(kind='ACCEPT',operation_id='sell',expected_revision=book['revision'],decision_bytes=raw),'2026-11-02T15:00:10+00:00')
                    oid=next(oid for oid,o in book['orders'].items() if o['closed'] is None)
                    minutes={oid:[dict(security_id='A',start='2026-11-02T15:01:00+00:00',end='2026-11-02T15:02:00+00:00',open='100',high='101',low='99',close='100')]}
                    book=f.apply(book,f.settlement_request(book,'sold',minutes,'2026-11-02T15:02:00+00:00'),'2026-11-02T15:02:01+00:00')
                    self.assertEqual(book['shares'].get('A',0),0)
                common=dict(book=book,authority=f.authority,admitted_decisions=f.admitted,admitted_settlements=f.settlements,
                    securities={'B':{'ticker':'B'}},clock=lambda:datetime.fromisoformat('2026-11-02T15:03:00+00:00'))
                with self.assertRaisesRegex(ValueError,'PAPER_UNIT_EXPOSURE_DOMAIN'):
                    review_prospective_units(**common,market_capture={},action_package={},training_manifest_sha256='1'*64,
                        historical_search_arguments_sha256='2'*64,historical_price_basis='fixture',training_closed_at='2026-10-29T20:00:00+00:00')
                with self.assertRaisesRegex(ValueError,'PAPER_CAPTURE_SECURITY_DOMAIN'):
                    capture_prospective_sources(**common,identity_resolver=PinnedStrategyIdentity(folder,'manifest.json','0'*64),
                        target_quantities={'B':1},window_start='2026-10-29T20:00:00+00:00',output_directory=Path(folder)/'capture')
                self.assertFalse((Path(folder)/'capture').exists())


if __name__=='__main__':unittest.main()
