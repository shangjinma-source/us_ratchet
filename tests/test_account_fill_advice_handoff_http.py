"""Isolated real account HTTP and daily composition; fixture market, no live writes."""
from fractions import Fraction
from datetime import timedelta
from fastapi.testclient import TestClient
import test_capital_supplement_advice_http as fixture


class FillHandoffHTTPTests(fixture.LargerCapitalAdviceHTTPTests):
    def advice_application(self, c, risk_reader):
        import json
        from hashlib import sha256
        from types import SimpleNamespace
        from unittest.mock import patch
        from fastapi import APIRouter
        from core.strategy_account_ledger import canonical
        from data.strategy_daily_composition_v7 import DailyCompositionV7
        from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
        from data.strategy_unified_server_preparation_v24 import SOURCES, build_unified_server_preparation_v24
        from test_capital_supplement_v23_mount import SourceWrapper
        packet = risk_reader.source_reader
        root = packet.root
        pins = {}
        for name in SOURCES:
            raw = (fixture.fixture.ROOT/name).read_bytes()
            path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        config = dict(schema='RISK_HISTORY_CONTINUATION_PREPARATION_V24',
            base_v23=dict(path='fixture-base.json',sha256='0'*64), source_pins=pins,
            risk_history_capture=dict(authorized=True,capture_root='risk-handoff-capture',archive_root='risk-v24'))
        raw=canonical(config);(root/'v24.json').write_bytes(raw)
        risk_reader.source_reader=SourceWrapper(packet)
        daily=DailyCompositionV7(monthly_service=c.capital_monthly,evidence_reader=risk_reader,
            execution_provider=c.provider.execution,clock=lambda:c.clock[0],
            policy_execution_enabled=True,policy_id='MONTHLY_CAP50_EXIT20',fee_bps='10')
        old=SimpleNamespace(service=SimpleNamespace(service=daily),
            journal=DailyAdviceJournalV1(root/'v24-journal.sqlite',clock=lambda:c.clock[0]),
            clock=lambda:c.clock[0],policy_references={'fixture':'base'})
        router=APIRouter()
        async def unused():
            raise AssertionError('old route must be replaced')
        router.add_api_route('/api/strategy-daily-v3/preview',unused,methods=['POST'])
        base=dict(monthly=c.capital_monthly,observed_daily=old,router=router,
            validate_code=c.capital_monthly.validate_current_target_pins)
        with patch('data.strategy_unified_server_preparation_v24.build_unified_server_preparation_v23',return_value=base):
            prepared=build_unified_server_preparation_v24(root=root,configuration_path='v24.json',
                configuration_sha256=sha256(raw).hexdigest())
        self.assertIs(prepared['observed_daily'].service.reader.risk_store,risk_reader.risk_store)
        self.assertIs(prepared['observed_daily'].monthly,c.capital_monthly)
        app=c.capital_application;app.include_router(prepared['router'])
        return app

    def verify_fill_handoff(self, c, risk_reader):
        c.clock[0] += timedelta(minutes=1)
        client = TestClient(c.capital_application)
        target = c.capital_monthly.current()
        before = c.store.read()
        binding = dict(expected_revision=before['revision'], target_id=target['target_id'])
        preview = client.post('/api/strategy-daily-v3/preview', json=binding)
        self.assertEqual(preview.status_code, 200, preview.text)
        sell = next(row for row in preview.json()['new_orders'] if row['side'] == 'SELL')
        previous_risk = risk_reader.risk_store.read(before['account_id'])
        holdings = client.get('/api/strategy-account').json()['account']['holdings']
        ticker = next(row['ticker'] for row in holdings if row['security_id'] == sell['security_id'])
        body = dict(expected_revision=before['revision'], event=dict(
            event_id='handoff-sell', kind='DIRECT_FILL', ticker=ticker, side='SELL',
            quantity=sell['quantity'], price='100', fees='0', executed_at=c.clock[0].isoformat()))
        fill = client.post('/api/strategy-account/events', json=body)
        self.assertEqual(fill.status_code, 200, fill.text)
        filled = c.store.read()
        self.assertEqual(filled['shares'][sell['security_id']],
                         before['shares'][sell['security_id']] - sell['quantity'])
        self.assertFalse(filled['cash_confirmation_valid'])
        self.assertEqual(client.post('/api/strategy-account/events', json=body).status_code, 200)
        self.assertEqual(c.store.read(), filled, 'retry must not duplicate the fill')
        stale = client.post('/api/strategy-daily-v3/preview', json=binding)
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()['new_orders'], [])
        # Explicit hypothetical broker balance in this isolated test only.
        cash = str(Fraction(before['available_cash']) + 100 * sell['quantity'])
        saved = client.post('/api/strategy-account/events', json=dict(
            expected_revision=filled['revision'], event=dict(event_id='handoff-balance',
            kind='CASH_CONFIRM', amount=cash, cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
        self.assertEqual(saved.status_code, 200, saved.text)
        current = c.store.read()
        c.clock[0] += timedelta(minutes=1)
        refreshed = client.post('/api/strategy-daily-v3/preview', json=dict(
            expected_revision=current['revision'], target_id=target['target_id']))
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(refreshed.json()['status'], 'READY', refreshed.text)
        orders = refreshed.json()['new_orders']
        self.assertFalse(any(row['side']=='SELL' and row['security_id']==sell['security_id'] for row in orders))
        self.assertTrue(any(row['side']=='BUY' for row in orders))
        self.assertEqual(c.capital_monthly.current(), target)
        self.assertEqual(c.store.read(), current)

        self.assertEqual(risk_reader.risk_store.read(before['account_id']), previous_risk,
                         'same-session liquidation must retain all monthly risk state')
        # Re-open the on-disk store and request once more with newer quote time.
        from data.monthly_peak_exit_store import MonthlyPeakExitStore
        self.assertEqual(MonthlyPeakExitStore(risk_reader.risk_store.path).read(before['account_id']), previous_risk)
        c.clock[0] += timedelta(minutes=1)
        repeated = client.post('/api/strategy-daily-v3/preview', json=dict(
            expected_revision=current['revision'], target_id=target['target_id']))
        self.assertEqual(repeated.status_code, 200, repeated.text)
        def actions(rows):
            return [(row['security_id'],row['side'],row['quantity'],row['limit_price']) for row in rows]
        self.assertEqual(actions(repeated.json()['new_orders']), actions(orders))
        self.assertEqual(risk_reader.risk_store.read(before['account_id']), previous_risk)
        self.assertEqual(c.store.read(), current)

        # A partial purchase must be included in the next difference calculation.
        # This is an isolated broker-fill record, not assumed live execution.
        buy = next(row for row in orders if row['side'] == 'BUY')
        self.assertGreater(buy['quantity'], 1)
        purchased = buy['quantity'] // 2
        from api.strategy_monthly_target import compact
        buy_ticker = next(row['ticker'] for row in compact(target)['targets']
                          if row['security_id'] == buy['security_id'])
        price = Fraction(buy['limit_price'])
        partial_body = dict(expected_revision=current['revision'], event=dict(
            event_id='handoff-partial-buy', kind='DIRECT_FILL', ticker=buy_ticker,
            side='BUY', quantity=purchased, price=str(price), fees='0',
            executed_at=c.clock[0].isoformat()))
        partial = client.post('/api/strategy-account/events', json=partial_body)
        self.assertEqual(partial.status_code, 200, partial.text)
        after_purchase = c.store.read()
        self.assertEqual(after_purchase['shares'][buy['security_id']],
                         current['shares'].get(buy['security_id'], 0) + purchased)
        self.assertFalse(after_purchase['cash_confirmation_valid'])
        self.assertEqual(client.post('/api/strategy-account/events', json=partial_body).status_code, 200)
        self.assertEqual(c.store.read(), after_purchase)
        remaining_cash = Fraction(current['available_cash']) - purchased * price
        saved_purchase = client.post('/api/strategy-account/events', json=dict(
            expected_revision=after_purchase['revision'], event=dict(
                event_id='handoff-post-buy-balance', kind='CASH_CONFIRM',
                amount=str(remaining_cash), cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
        self.assertEqual(saved_purchase.status_code, 200, saved_purchase.text)
        after_confirmation = c.store.read()
        c.clock[0] += timedelta(minutes=1)
        remaining = client.post('/api/strategy-daily-v3/preview', json=dict(
            expected_revision=after_confirmation['revision'], target_id=target['target_id']))
        self.assertEqual(remaining.status_code, 200, remaining.text)
        self.assertEqual(remaining.json()['status'], 'READY', remaining.text)
        remaining_buys = [row for row in remaining.json()['new_orders']
                          if row['side'] == 'BUY' and row['security_id'] == buy['security_id']]
        self.assertEqual(len(remaining_buys), 1)
        self.assertEqual(remaining_buys[0]['quantity'], buy['quantity'] - purchased)
        self.assertFalse(any(row['side'] == 'SELL' and row['security_id'] == sell['security_id']
                             for row in remaining.json()['new_orders']))
        self.assertEqual(c.capital_monthly.current(), target)
        self.assertEqual(c.store.read(), after_confirmation)
