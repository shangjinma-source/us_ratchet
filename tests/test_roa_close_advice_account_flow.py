"""Account-backed close exit regression; all fills belong to a temporary ledger."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from api.strategy_account import StrategyAccountService
from data.roa_execution_lifecycle import RoaExecutionLifecycle
from data.roa_strategy_service import RoaStrategyService


class CloseAdviceAccountFlowTests(unittest.TestCase):
    def test_close_exit_tracks_partial_fill_and_never_rewrites_cash(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [datetime.fromisoformat('2026-11-05T14:31:00+00:00')]
            account = StrategyAccountService(
                database_path=Path(directory) / 'test.sqlite3', account_id='test',
                clock=lambda: now[0], resolver=lambda ticker: dict(
                    ticker=ticker, security_id='A', source_references=['synthetic'],
                    source_hashes={'synthetic': 'b' * 64}))
            account.initialize({'event_id': 'init'})

            def append(event):
                return account.append(dict(expected_revision=account.store.read()['revision'], event=event))

            append(dict(kind='CASH_CONFIRM', event_id='cash', amount='1000', cash_basis='TOTAL_UNINVESTED'))
            append(dict(kind='DIRECT_FILL', event_id='buy', ticker='A', side='BUY',
                        quantity=9, price='10', fees='0', executed_at=now[0].isoformat()))
            append(dict(kind='CASH_CONFIRM', event_id='cash-after-buy', amount='910',
                        cash_basis='TOTAL_UNINVESTED'))
            life = RoaExecutionLifecycle(path=Path(directory) / 'life.json', account_id='test',
                                         strategy_epoch='e', contract_sha256='a' * 64)
            signal = dict(signal_id='s', signal_date='2026-11-04', decision_date='2026-10-30',
                          risk_on=True, weights={'A': '1/10'}, execution_not_before_session='2026-11-05',
                          securities=[dict(security_id='A', ticker='A')])

            def session(day):
                return dict(open_at=day + 'T14:30:00+00:00', close_at=day + 'T21:00:00+00:00')

            calls = []

            def quotes(state, identifiers, day, phase, clock):
                calls.append((day, phase))
                return dict(opening_session=day, opening_prices={'A': '10'},
                            quote_valid_until=(clock + timedelta(seconds=120)).isoformat(),
                            marks={'A': dict(security_id='A', currency='USD', price_basis='current',
                                             price='8', observed_at=clock.isoformat())},
                            limits={'A': dict(security_id='A', price_basis='current', buy='8.00',
                                              sell='8.00', observed_at=clock.isoformat())})

            service = RoaStrategyService(account_service=account, lifecycle=life,
                signal_provider=lambda: signal, session_provider=session, quote_provider=quotes,
                clock=lambda: now[0], execution_admission=dict(enabled=True, strategy_epoch='e',
                    contract_sha256='a' * 64, open_window_seconds=300, close_window_seconds=300))
            service.snapshot()
            life.close_observation(session='2026-11-05', shares={'A': 9}, closing_prices={'A': '10'})
            life.close_observation(session='2026-11-06', shares={'A': 9}, closing_prices={'A': '7.90'})
            signal.update(signal_id='next', signal_date='2026-11-06', execution_not_before_session='2026-11-09')
            now[0] = datetime.fromisoformat('2026-11-09T20:54:00+00:00')
            calls.clear()
            before = account.store.read()
            pending = service.snapshot()
            self.assertEqual(pending['status'], 'PENDING_CLOSE')
            self.assertFalse(pending['executable'])
            self.assertEqual(calls, [])
            self.assertEqual(account.store.read(), before)
            now[0] += timedelta(minutes=2)
            ready = service.snapshot()
            self.assertEqual(ready['status'], 'READY', ready)
            self.assertEqual((ready['rows'][0]['side'], ready['rows'][0]['quantity']), ('SELL', 9))
            append(dict(kind='DIRECT_FILL', event_id='partial', ticker='A', side='SELL',
                        quantity=4, price='8', fees='0', executed_at=now[0].isoformat()))
            append(dict(kind='CASH_CONFIRM', event_id='cash-after-partial', amount='942',
                        cash_basis='TOTAL_UNINVESTED'))
            after_partial = account.store.read()
            for _ in range(2):
                remainder = service.retry_advice()
                self.assertEqual(remainder['rows'][0]['quantity'], 5)
                self.assertIsNone(remainder['cash_saved'])
                self.assertEqual(account.store.read(), after_partial)
            append(dict(kind='DIRECT_FILL', event_id='complete', ticker='A', side='SELL',
                        quantity=5, price='8', fees='0', executed_at=now[0].isoformat()))
            completed = account.store.read()
            now[0] = datetime.fromisoformat('2026-11-09T21:01:00+00:00')
            result = service.snapshot()
            self.assertEqual(result['status'], 'HOLD', result)
            self.assertFalse(result['executable'])
            self.assertIsNone(result['rows'][0]['quantity'])
            self.assertEqual(account.store.read(), completed)


if __name__ == '__main__':
    unittest.main()
