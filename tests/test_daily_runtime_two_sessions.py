"""Actual temporary-ledger daily execution across a weekend; no market IO."""
import json
import unittest
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import test_run_current_quantity_v2_simulation as fixture
from backtest.current_quantity_v2_simulation_store import SimulationStore
from scripts.run_current_quantity_v2_simulation import run_runtime


class TwoSessionRuntimeTests(unittest.TestCase):
    setUpClass = classmethod(lambda cls: fixture.cash_fixture.CurrentCashTests.setUpClass())
    tearDownClass = classmethod(lambda cls: fixture.cash_fixture.CurrentCashTests.tearDownClass())

    def test_unfilled_orders_expire_and_renew_on_two_actual_daily_runs(self):
        with TemporaryDirectory() as folder:
            request, args, transport, calls = fixture.RuntimeTests.setup(self, folder)
            config = json.loads(request['config_path'].read_bytes())
            state = args['store'].read(args['simulation_id'])['simulation']
            calendar = state['valuation']['registration']['calendar']
            calendar['session_dates'].append('2026-10-19')
            calendar['closes']['2026-10-19'] = '2026-10-19T16:00:00-04:00'
            store = SimulationStore(Path(folder) / 'two-days.sqlite3')
            store.create(state)
            config['database_path'] = str(store.path)
            root = Path(config['root'])
            schedule = root / config['schedule_path']
            value = json.loads(schedule.read_bytes())
            value['sessions'].append(dict(date='2026-10-19', open_at='2026-10-19T09:30:00-04:00', close_at='2026-10-19T16:00:00-04:00'))
            schedule.write_text(json.dumps(value))
            config['schedule_sha256'] = sha256(schedule.read_bytes()).hexdigest()
            fees = root / config['fees_path']
            fees.write_text(json.dumps(dict(schema='EXPLICIT_SIMULATION_FEE_MODEL_V1', status='MODELLED_FEES_NOT_BROKER_FEES', fixed_per_order='0', notional_rate='0')))
            config['fees_sha256'] = sha256(fees.read_bytes()).hexdigest()
            request['config_path'].write_text(json.dumps(config))
            request['config_sha256'] = sha256(request['config_path'].read_bytes()).hexdigest()
            clock = [datetime.fromisoformat('2026-10-16T10:00:30-04:00')]
            original_minutes = transport['minutes']
            original_quote = transport['quotes']

            def no_fill(url):
                value = json.loads(original_minutes(url))
                quote = value['chart']['result'][0]['indicators']['quote'][0]
                for key in ('open', 'high', 'low', 'close'):
                    quote[key] = [1000000] * len(quote[key])
                return json.dumps(value).encode()

            def fresh_quote(ticker):
                value = json.loads(original_quote(ticker))
                row = value['chart']['result'][0]
                now = clock[0]
                row['meta']['regularMarketTime'] = int(now.timestamp()) - 1
                row['meta']['currentTradingPeriod']['regular'] = dict(start=int(now.replace(hour=9, minute=30, second=0).timestamp()), end=int(now.replace(hour=16, minute=0, second=0).timestamp()))
                row['timestamp'] = [int(now.replace(second=0).timestamp()) - 60]
                return json.dumps(value).encode()

            transport.update(minutes=no_fill, quotes=fresh_quote,
                rss=lambda: dict(status=200, body=('<rss><channel><title>Nasdaq</title><item><title>Unrelated notice</title><pubDate>' + clock[0].strftime('%a, %d %b %Y %H:%M:%S %z') + '</pubDate></item></channel></rss>').encode()))
            initial_cash = state['chain']['ledger']['cash']
            for day, prior in [('2026-10-16', '2026-10-15'), ('2026-10-19', '2026-10-16')]:
                clock[0] = datetime.fromisoformat(day + 'T10:00:30-04:00')
                request.update(session=day, triggered_at=day + 'T10:00:00-04:00')
                result = run_runtime(**request, execute=True, clock=lambda: clock[0], transports=transport)
                self.assertEqual(result['daily_status'], 'CONTINUATION_COMPLETE')
                ledger = result['simulation']['chain']['ledger']
                self.assertEqual(ledger['cash'], initial_cash)
                self.assertFalse(any(ledger['shares'].values()))
                self.assertTrue(ledger['orders'])
                self.assertTrue(all(not order['closed'] and order['session_close'].startswith(day) for order in ledger['orders'].values()))
                self.assertEqual(result['simulation']['valuation']['records'][-1]['session'], prior)
                before = tuple(map(len, calls))
                self.assertEqual(run_runtime(**request, execute=True, clock=lambda: clock[0], transports=transport)['daily_status'], 'ALREADY_COMPLETED')
                self.assertEqual(tuple(map(len, calls)), before)


if __name__ == '__main__':
    unittest.main()
