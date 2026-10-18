from datetime import datetime
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse
import json
import unittest

from backtest.current_quantity_v2_simulation_bootstrap import bootstrap
from backtest.current_quantity_v2_simulation_store import SimulationStore
from backtest.current_quantity_v2_simulated_settlement import MODEL, record_close
from backtest.current_quantity_v2_daily_settlement_simulation import prepare_daily_settlement, apply_daily_settlement
from backtest.current_quantity_v2_monthly_simulation import digest
from data.current_quantity_v2_minute_close_marks import build_marks
from test_current_quantity_v2_current_cash_ledger import frozen_fixture
from test_current_quantity_v2_daily_settlement_simulation import reviews
import test_current_quantity_v2_current_cash_plan as cash_fixture


class SimulationLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cash_fixture.CurrentCashTests.setUpClass()

    @classmethod
    def tearDownClass(cls): cash_fixture.CurrentCashTests.tearDownClass()

    def test_cash_bootstrap_capture_settle_close_and_restart(self):
        with TemporaryDirectory() as folder:
            proposal, arguments = frozen_fixture(cash_fixture.CurrentCashTests.args)
            reference = next(iter(proposal['execution_references'].values()))
            session = reference['session']
            store = SimulationStore(Path(folder) / 'simulation.sqlite3')
            original = bootstrap(store=store, simulation_id='cash-lifecycle', proposal=proposal,
                account_state=arguments['account_state'], initial_cash=arguments['account_state']['cash'],
                model=MODEL, calendar=dict(session_dates=[session], closes={session:reference['session_close']},
                    source_references=['synthetic-calendar']), source_admission_guard=lambda pins: None,
                clock=lambda:datetime.fromisoformat(arguments['now']))
            calls = []

            def fetch(url):
                calls.append(url)
                query = parse_qs(urlparse(url).query)
                times = list(range(int(query['period1'][0]), int(query['period2'][0]), 60))
                chart = dict(meta=dict(symbol=urlparse(url).path.rsplit('/', 1)[1], currency='USD',
                    instrumentType='EQUITY', dataGranularity='1m', exchangeTimezoneName='America/New_York'),
                    timestamp=times, events={}, indicators=dict(quote=[dict(
                        **{key:[1]*len(times) for key in ('open','high','low','close','volume')})]))
                return json.dumps(dict(chart=dict(error=None, result=[chart]))).encode()

            prepared = prepare_daily_settlement(store=store, simulation_id='cash-lifecycle',
                expected_revision=original['revision'], session=session,
                fees={oid:'0' for oid in original['simulation']['chain']['ledger']['orders']},
                calendar_source_reference='synthetic-calendar', directory=Path(folder)/'capture', fetch=fetch,
                clock=lambda:datetime.fromisoformat('2026-10-16T09:00:00-04:00'))
            review = reviews(prepared, original['simulation'])
            settled = apply_daily_settlement(store=SimulationStore(store.path), prepared=prepared, **review)
            ledger = settled['simulation']['chain']['ledger']
            self.assertTrue(all(order['closed']=='FILLED' for order in ledger['orders'].values()))
            self.assertEqual(ledger['shares'], ledger['target_quantities'])
            captures = {sid:{key:digest(sid)+'/'+filename for key,filename in
                [('raw','response.bin'),('receipt','receipt.json'),('minutes','minutes.json')]}
                for sid, quantity in ledger['shares'].items() if quantity}
            pins = dict(review['source_hashes'])
            root = Path(prepared['directory'])
            for paths in captures.values():
                for name in paths.values(): pins[name] = sha256((root/name).read_bytes()).hexdigest()
            close = build_marks(root=root, chain=settled['simulation']['chain'], session=session,
                session_close=reference['session_close'], captures=captures, source_hashes=pins,
                unit_reviews=review['unit_reviews'], observed_at=review['evaluated_at'])
            request = dict(kind='TEST_CLOSE', session=session, marks=close['marks'], observed_at=close['observed_at'])
            operation = dict(simulation_id='cash-lifecycle', expected_revision=settled['revision'],
                operation_id='cash-lifecycle:close:'+session, request=request)
            completed = store.apply(**operation, transform=lambda state:record_close(simulation=state,
                **{key:request[key] for key in ('session','marks','observed_at')}))
            valuation = completed['simulation']['valuation']
            self.assertEqual(Fraction(valuation['records'][0]['equity']),
                Fraction(ledger['cash'])+sum(ledger['shares'].values()))
            self.assertEqual(valuation['initial_equity'], arguments['account_state']['cash'])
            repeated = SimulationStore(store.path).apply(**operation,
                transform=lambda state:self.fail('completed close must not execute twice'))
            self.assertTrue(repeated['replayed'])
            self.assertEqual(repeated['revision'], completed['revision'])
            self.assertEqual(len(calls), len(captures))
            self.assertFalse(completed['simulation']['forward_activated'])


if __name__ == '__main__': unittest.main()
