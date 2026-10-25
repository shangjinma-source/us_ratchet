"""Same isolated ledger: capital HTTP -> selection -> supplemental source -> advice HTTP.

Monthly runtime routing is supplied by a fixture adapter; market transports and
policy authority are fixtures. No production account or source is modified.
"""
from contextlib import nullcontext
from copy import deepcopy
from hashlib import sha256
from fractions import Fraction
import json
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.strategy_account_ledger import canonical
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from core.strategy_profiled_capital_journal_v2 import ProfiledCapitalJournalV2
from core.strategy_profiled_capital_intent_journal import ProfiledCapitalIntentJournal
from data.strategy_continuous32_target_service import StrategyContinuous32TargetService, MINIMUM_RUNTIME_PATHS
from data.strategy_capital_arrival_service_v2 import CapitalArrivalServiceV2
from data.strategy_daily_composition_v7 import DailyCompositionV7
from api.strategy_capital_arrival_v2 import create_router as capital_router
from api.strategy_daily_preview_v4 import create_router as advice_router
from api.strategy_account import create_router as account_router
import test_strategy_monthly_supplement_reader as fixture


class CapitalAdviceHTTPTests(fixture.SupplementReaderTests):
    contribution_amount = '200'
    def monthly_runtime(self, c, root, original_target):
        pins = {}
        for name in MINIMUM_RUNTIME_PATHS:
            raw = (fixture.ROOT/name).read_bytes()
            path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        selector = StrategyContinuous32TargetService(store=c.store, evidence_provider=c.provider.selection,
            runtime_root=root, runtime_pins=pins, maximum_mark_age_seconds=900,
            execution_fee_bps='10', clock=lambda:c.clock[0])
        targets = StrategyMonthlyTargetStore(root/'capital-targets.sqlite')
        initial = deepcopy(original_target['payload'])
        initial.update(previous_target_id=None, request=dict(event_id='fixture-initial', reason='INITIAL'),
            runtime_pins=pins)
        targets.append(initial)
        runtime = SimpleNamespace(selection=selector, execution_provider=c.provider.execution)
        configuration = dict(identity_manifest=c.identity_reference['path'], identity_sha256=c.identity_reference['sha256'])
        monthly = SimpleNamespace(root=root, accounts=c.store, targets=targets, current=targets.current,
            clock=lambda:c.clock[0], _month=lambda:'2026-11', _for_target=lambda target:(runtime,configuration),
            snapshot_operation=nullcontext, validate_current_target_pins=selector._pins)
        return monthly

    def publish_target(self, c, root, original_target, arguments):
        monthly = self.monthly_runtime(c, root, original_target)
        targets = monthly.targets
        selector = monthly._for_target(targets.current())[0].selection
        journal = ProfiledCapitalJournalV2(root/'capital-journal.sqlite')
        journal.initialize_from_legacy(ProfiledCapitalIntentJournal(root/'unused-legacy.sqlite'))
        capital = CapitalArrivalServiceV2(monthly=monthly,journal=journal,validate_code=selector._pins,
            capture_provider_builder=lambda rt:rt.selection.provider)
        app = FastAPI(); app.include_router(capital_router(service=capital))
        app.include_router(account_router(database_path=c.store.path,
            account_id=c.store.read()['account_id'],resolver=c.provider.market.identity,
            clock=lambda:c.clock[0]))
        c.capital_application=app
        client=TestClient(app)
        # Ordinary balance saves retain the monthly target and do not start selection.
        original=targets.current(); prior=c.store.read()
        balance=client.post('/api/strategy-account/events',json=dict(
            expected_revision=prior['revision'],event=dict(event_id='joint-balance-update',
            kind='CASH_CONFIRM',amount='100',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
        self.assertEqual(balance.status_code,200,balance.text)
        self.assertEqual(targets.current(),original)
        readback=client.get('/api/strategy-account')
        self.assertEqual(readback.json()['account']['revision'],c.store.read()['revision'])
        self.assertEqual(Fraction(readback.json()['account']['available_cash']),100)
        before = c.store.read(); old = targets.current()
        c.previous_advice_binding=dict(expected_revision=before['revision'],target_id=old['target_id'])
        body = dict(event_id='joint-new-capital', contribution_amount=self.contribution_amount,
            expected_revision=before['revision'], previous_target_id=old['target_id'])
        c.capital_monthly=monthly
        c.target=targets.current()
        self.perform_contribution(c, client, body)
        c.target=targets.current();self.assertNotEqual(c.target['target_id'],old['target_id'])
        # The vendor fixture marks every held security at USD100. Check the
        # optimization budget independently of its saved search arguments:
        # a deposit must not replace holdings with cash or count either twice.
        binding=c.target['payload']['decision']['payload']['input_binding']
        expected_cash=Fraction(before['available_cash'])+Fraction(self.contribution_amount)
        expected_equity=expected_cash+100*sum(before['shares'].values())
        self.assertEqual(binding['strategy_shares'],before['shares'])
        self.assertEqual(Fraction(binding['strategy_equity']),expected_equity)
        self.assertEqual(Fraction(binding['search_arguments']['entered_cash']),expected_equity)
        self.assertEqual(Fraction(c.store.read()['available_cash']),expected_cash)
        self.assertEqual(c.store.read()['shares'],before['shares'])
        print('CAPITAL_EQUITY_CHECK: cash='+str(expected_cash)+
              '; held_value='+str(100*sum(before['shares'].values()))+
              '; selection_equity='+str(expected_equity))

    def perform_contribution(self, c, client, body):
        before = c.store.read()
        response=client.post('/api/strategy-capital-v2/arrive',json=body)
        self.assertEqual(response.status_code,200,response.text)
        credited=c.store.read()
        self.assertEqual(Fraction(credited['available_cash']),Fraction(before['available_cash'])+Fraction(self.contribution_amount))
        self.assertEqual(client.post('/api/strategy-capital-v2/arrive',json=body).status_code,200)
        self.assertEqual(c.store.read(),credited)
        response=client.post('/api/strategy-capital-v2/configure',json=dict(event_id=body['event_id']))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'CONSUMED_BY_PUBLISHED_TARGET')
        c.target=c.capital_monthly.current()
        self.assertEqual(c.target['payload']['decision']['payload']['input_binding']['account_revision'],credited['revision'])

    def advice_application(self, c, risk_reader):
        service=DailyCompositionV7(monthly_service=c.capital_monthly,evidence_reader=risk_reader,
            execution_provider=c.provider.execution,clock=lambda:c.clock[0],
            policy_execution_enabled=True,policy_id='MONTHLY_CAP50_EXIT20',fee_bps='10')
        app=c.capital_application;app.include_router(advice_router(service=service));return app

    def verify_preview_response(self, response):
        pass

    def verify_advice_http(self, c, risk_reader):
        client=TestClient(self.advice_application(c, risk_reader))
        before=c.store.read();target=c.capital_monthly.current()
        for stale in [c.previous_advice_binding,
                dict(expected_revision=before['revision'],target_id=c.previous_advice_binding['target_id']),
                dict(expected_revision=c.previous_advice_binding['expected_revision'],target_id=target['target_id'])]:
            rejected=client.post('/api/strategy-daily-v3/preview',json=stale)
            self.assertEqual(rejected.status_code,409,rejected.text)
            self.assertEqual(rejected.json()['new_orders'],[])
            self.assertEqual(rejected.json()['reference_quotes'],{})
            self.assertEqual(c.store.read(),before)
            self.assertEqual(c.capital_monthly.current(),target)
        response=client.post('/api/strategy-daily-v3/preview',json=dict(
            expected_revision=before['revision'],target_id=target['target_id']))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'READY',response.text)
        self.assertEqual(response.json()['target_id'],target['target_id'])
        self.assertEqual(response.json()['account_revision'],before['revision'])
        self.verify_preview_response(response.json())
        orders=response.json()['new_orders']
        self.assertTrue(orders,'READY scenario must include actual buy/sell detail')
        buy_cost=sum((Fraction(str(order['limit_price']))*order['quantity']
            for order in orders if order['side']=='BUY'),Fraction(0))
        self.assertLessEqual(buy_cost,Fraction(before['available_cash']),
            'unsold proceeds cannot fund current buys')
        for order in orders:
            if order['side']=='SELL':
                self.assertLessEqual(order['quantity'],before['shares'][order['security_id']])
        self.assertFalse(response.json()['orders_created'])
        if Fraction(self.contribution_amount)>200:
            self.assertGreater(buy_cost,0,'larger capital fixture must exercise buy sizing: '+response.text)
        if Fraction(self.contribution_amount)>200:
            complete_fetch = c.provider.market.fetch
            def missing_minutes(ticker):
                document = json.loads(complete_fetch(ticker))
                result = document['chart']['result'][0]
                result['timestamp'] = result['timestamp'][-1:]
                for values in result['indicators']['quote']:
                    for field in values:
                        values[field] = values[field][-1:]
                return canonical(document)
            c.provider.market.fetch = missing_minutes
            try:
                incomplete = client.post('/api/strategy-daily-v3/preview',json=dict(
                    expected_revision=before['revision'],target_id=target['target_id']))
                self.assertEqual(incomplete.status_code,200,incomplete.text)
                blocked = incomplete.json()
                self.assertEqual(blocked['detail_status'],'CONDITIONAL_SELL_PREVIEW_BUYS_WAIT')
                self.assertEqual(blocked['buy_data_failure'],'NONCONTIGUOUS_OR_FUTURE_MINUTE')
                self.assertEqual([(r['security_id'],r['quantity']) for r in blocked['waiting_data']],[('B',9)])
                self.assertTrue(blocked['new_orders'])
                self.assertTrue(all(r['side']=='SELL' for r in blocked['new_orders']))
            finally:
                c.provider.market.fetch = complete_fetch
        self.assertEqual(c.store.read(),before)
        self.assertEqual(c.capital_monthly.current(),target)
        print('CAPITAL_ADVICE_HTTP_READY: credited once; new target; supplemented A once; '
            'orders='+str([(row['security_id'],row['side'],row['quantity']) for row in orders])+
            '; account/target unchanged by preview')


class LargerCapitalAdviceHTTPTests(CapitalAdviceHTTPTests):
    contribution_amount = '3000'
