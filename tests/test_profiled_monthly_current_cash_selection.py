"""Profiled monthly publication -> actual current-cash selection, isolated fixture."""
import json
import unittest
from fractions import Fraction
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from data.strategy_profiled_runtime import build_runtime
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from api.strategy_dynamic_monthly_target import create_dynamic_account_router, create_dynamic_monthly_target_router
import test_prepare_profiled_monthly_publication_v1 as fixtures


class ProfiledMonthlySelectionTests(unittest.TestCase):
    def test_adopt_then_current_cash_and_existing_holding_drive_new_month(self):
        f=fixtures.PublicationTests();f.setUp();self.addCleanup(f.doCleanups)
        f.f.f.add_departed_identity()
        identity=PinnedStrategyIdentity(f.root,'identity-release.json',f.f.f.entry['identity_sha256'])
        f.args['market_capture'].identity=identity
        original=f.f.f.identity['candidates'][0]
        for event_id,ticker,side,quantity in [('exit-original',original['ticker'],'SELL',1),('hold-departed','DEPARTED','BUY',2)]:
            evidence=identity(ticker)
            f.f.store.append(dict(event_id=event_id,kind='DIRECT_FILL',security_id=evidence['security_id'],
                side=side,quantity=quantity,price='10',fees='0',executed_at=f.f.now.isoformat(),identity_evidence=evidence),
                expected_revision=f.f.store.read()['revision'])
        fetch=f.args['market_capture'].fetch
        def minute_history(ticker):
            document=json.loads(fetch(ticker));row=document['chart']['result'][0]
            start=row['meta']['currentTradingPeriod']['regular']['start']
            row['timestamp']=list(range(start,start+1800,60))
            row['indicators']['quote']=[{key:[values[0]]*30 for key,values in row['indicators']['quote'][0].items()}]
            return canonical(document)
        f.args['market_capture'].fetch=minute_history
        observed=[]
        def after_adoption(activation,handoff,targets,old_configuration):
            prior=targets.current();shares=dict(f.f.store.read()['shares'])
            def builder(**kwargs):
                runtime=build_runtime(**kwargs)
                provider=runtime.execution_provider.__self__
                provider.market=f.args['market_capture'];provider.actions=f.args['action_capture']
                selection=provider.selection
                def capture(state):
                    observed.append(dict(cash=state['cash'],shares=dict(state['shares']),configuration=kwargs['configuration']))
                    return selection(state)
                provider.selection=capture
                return runtime
            monthly=ProfiledRollingMonthlyRuntimeRouter(root=f.root,initial_snapshot=handoff(),snapshot_provider=handoff,
                clock=lambda:f.f.now,runtime_builder=builder,identity_configuration=old_configuration)
            app=FastAPI();app.include_router(create_dynamic_account_router(service=monthly));app.include_router(create_dynamic_monthly_target_router(service=monthly))
            with TestClient(app) as client:
                account=client.get('/api/strategy-account').json()['account']
                response=client.post('/api/strategy-account/events',json=dict(expected_revision=account['revision'],event=dict(event_id='new-month-cash',kind='CASH_CONFIRM',amount='5',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(targets.current(),prior)
                current=f.f.store.read()
                result=client.post('/api/strategy-account/target/generate',json=dict(event_id='current-month-selection',reason='MONTHLY_SELECTION',expected_revision=current['revision'],previous_target_id=prior['target_id']))
                self.assertEqual(result.status_code,200,result.text)
                target=targets.current()
                self.assertEqual(target['payload']['target_month'],'2026-12')
                self.assertEqual(target['payload']['previous_target_id'],prior['target_id'])
                self.assertEqual(f.f.store.read(),current,'Target generation must not alter actual holdings/cash')
                self.assertEqual(observed[0]['shares'],shares)
                self.assertEqual(Fraction(observed[0]['cash']),5)
                binding=target['payload']['decision']['payload']['input_binding']
                self.assertEqual(Fraction(binding['strategy_equity']),25)
                self.assertEqual(shares.get('departed-id'),2)
                self.assertNotIn('departed-id',target['payload']['target_quantities'])
                self.assertNotEqual(binding['documents']['training_manifest'],old_configuration['training_manifest'])
                self.assertEqual(len(observed),1)
                if hasattr(self, 'verify_daily_handoff'):
                    self.verify_daily_handoff(f, monthly, target, current)
        f.after_adoption=after_adoption
        f.existing_target_case(first_adoption=True)
        self.assertEqual(len(observed),1)
