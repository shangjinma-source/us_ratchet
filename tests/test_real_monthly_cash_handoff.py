"""Isolated HTTP handoff: reviewed monthly data to real selection and cash-limited orders."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import json
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_runtime import build_runtime, ACCOUNT_ID
from data.strategy_account_release_activation import MonthlyReleaseActivation
from api.strategy_rolling_composition import create_rolling_strategy_router, ROLLING_SOURCE_PATHS
from scripts.review_prepare_real_monthly_release import run as prepare
import test_review_prepare_real_monthly_release as fixtures


class MonthlyCashHandoffTests(unittest.TestCase):
    def test_adoption_then_http_cash_new_month_real_selection_and_sell_cash_isolation(self):
        f=fixtures.ReviewPrepareTests();f.setUp();self.addCleanup(f.doCleanups)
        f.f.add_departed_identity()
        identity=PinnedStrategyIdentity(f.root,'identity-release.json',f.f.entry['identity_sha256'])
        f.arguments['market_capture'].identity=identity
        fetch=f.arguments['market_capture'].fetch
        def complete_minutes(ticker):
            document=json.loads(fetch(ticker));result=document['chart']['result'][0]
            start=result['meta']['currentTradingPeriod']['regular']['start']
            result['timestamp']=list(range(start,start+1800,60))
            result['indicators']['quote']=[{key:values*30 for key,values in result['indicators']['quote'][0].items()}]
            return canonical(document)
        f.arguments['market_capture'].fetch=complete_minutes
        original=f.f.identity['candidates'][0]
        def append(event):
            f.store.append(event,expected_revision=f.store.read()['revision'])
        append(dict(event_id='exit-fixture-b',kind='DIRECT_FILL',security_id=original['security_id'],
            side='SELL',quantity=1,price='10',fees='0',executed_at=f.now.isoformat(),identity_evidence=identity(original['ticker'])))
        append(dict(event_id='hold-old-a',kind='DIRECT_FILL',security_id='departed-id',side='BUY',quantity=2,
            price='10',fees='0',executed_at=f.now.isoformat(),identity_evidence=identity('DEPARTED')))
        old_configuration=dict(f.f.resolve(),target_month='2026-11')
        old_training=json.loads((f.root/old_configuration['training_manifest']).read_bytes())
        old_configuration.update(training_manifest='old-training.json',training_sha256=f.f.put('old-training.json',old_training))
        old_hash=f.f.put('old-runtime.json',old_configuration)
        archive=dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[dict(configuration_path='old-runtime.json',configuration_sha256=old_hash)])
        f.arguments['archive_sha256']=f.f.put('archive.json',archive)
        binding=dict(documents={'training_manifest':old_configuration['training_manifest']},
            source_hashes={old_configuration['training_manifest']:old_configuration['training_sha256'],
                           old_configuration['identity_manifest']:old_configuration['identity_sha256']})
        payload=dict(input_binding=binding,input_id=sha256(canonical(binding)).hexdigest(),target_quantities={'departed-id':2})
        targets=StrategyMonthlyTargetStore(f.root/'data/strategy_account/monthly_targets.sqlite3')
        old=targets.append(dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',account_id=ACCOUNT_ID,target_month='2026-11',
            runtime_pins=old_configuration['runtime_pins'],request={'event_id':'old-fixture'},previous_target_id=None,
            target_quantities=payload['target_quantities'],decision=dict(payload=payload,decision_id=sha256(canonical(payload)).hexdigest())))
        ready=prepare(**f.arguments)
        configuration=json.loads((f.root/'reviewed-package/candidate/runtime.json').read_bytes())
        pins={};source=Path(__file__).resolve().parents[1]
        for name in ROLLING_SOURCE_PATHS:
            raw=(source/name).read_bytes();destination=f.root/name
            destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
        initial={k:f.arguments[k] for k in ('registry_path','registry_sha256','archive_path','archive_sha256')}
        observed=[]
        def builder(**kwargs):
            service=build_runtime(**kwargs)
            provider=service.execution_provider.__self__
            provider.market=f.arguments['market_capture'];provider.actions=f.arguments['action_capture']
            original_selection=provider.selection
            def selection(state):
                observed.append(dict(configuration=kwargs['configuration'],state=state))
                return original_selection(state)
            provider.selection=selection
            return service
        app=FastAPI();app.include_router(create_rolling_strategy_router(root=f.root,**initial,source_pins=pins,
            bootstrap_configuration=old_configuration,identity_configuration=old_configuration,
            clock=lambda:f.now,runtime_builder=builder))
        http=TestClient(app);self.addCleanup(http.close)
        before=f.store.path.read_bytes()
        activation=MonthlyReleaseActivation(root=f.root,initial_snapshot=initial,validate_code=lambda:None,clock=lambda:f.now)
        activation.adopt(receipt_path='reviewed-package/ready.json',
            receipt_sha256=sha256((f.root/'reviewed-package/ready.json').read_bytes()).hexdigest(),expected_release_revision=0)
        self.assertEqual(f.store.path.read_bytes(),before)
        self.assertEqual(targets.current(),old)
        prior_preview=http.post('/api/strategy-account/target/preview',json=dict(target_id=old['target_id'],expected_revision=f.store.read()['revision']))
        self.assertEqual(prior_preview.status_code,422)
        self.assertEqual(prior_preview.json()['reason'],'MONTHLY_TARGET_REQUIRED')
        cash=http.post('/api/strategy-account/events',json=dict(expected_revision=f.store.read()['revision'],
            event=dict(event_id='cash-http',kind='CASH_CONFIRM',amount='5',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
        self.assertEqual(cash.status_code,200,cash.text)
        response=http.post('/api/strategy-account/target/generate',json=dict(event_id='dec-target',reason='MONTHLY_SELECTION',
            expected_revision=f.store.read()['revision'],previous_target_id=old['target_id']))
        self.assertEqual(response.status_code,200,response.text)
        new=targets.current()
        self.assertEqual(response.json()['target_id'],new['target_id'])
        self.assertEqual(new['payload']['target_month'],'2026-12')
        self.assertEqual(new['payload']['previous_target_id'],old['target_id'])
        decision_binding=new['payload']['decision']['payload']['input_binding']
        self.assertEqual(decision_binding['documents']['training_manifest'],configuration['training_manifest'])
        self.assertNotEqual(decision_binding['documents']['training_manifest'],old_configuration['training_manifest'])
        self.assertEqual(decision_binding['strategy_equity'],'25')
        self.assertEqual(len(observed),1)
        self.assertEqual(observed[0]['configuration'],configuration)
        self.assertEqual(observed[0]['state']['shares'].get('departed-id'),2)
        self.assertEqual(observed[0]['state']['cash'],'5')
        self.assertNotIn('departed-id',new['payload']['target_quantities'])
        self.assertGreater(new['payload']['target_quantities'][original['security_id']],0)
        preview=http.post('/api/strategy-account/target/preview',json=dict(target_id=new['target_id'],expected_revision=f.store.read()['revision']))
        self.assertEqual(preview.status_code,200,preview.text)
        difference=preview.json()['difference']
        self.assertEqual(difference['spendable_cash'],'5')
        self.assertTrue(any(o['side']=='SELL' and o['security_id']=='departed-id' and o['quantity']==2 for o in difference['new_orders']))
        self.assertFalse(any(o['side']=='BUY' for o in difference['new_orders']))
        self.assertEqual(f.store.read()['shares'].get('departed-id'),2)
        self.assertEqual(len(observed),1)
        sold=http.post('/api/strategy-account/events',json=dict(expected_revision=f.store.read()['revision'],
            event=dict(event_id='sold-a',kind='DIRECT_FILL',ticker='DEPARTED',side='SELL',quantity=2,
                       price='10',fees='0',executed_at=f.now.isoformat())))
        self.assertEqual(sold.status_code,200,sold.text)
        blocked=http.post('/api/strategy-account/target/preview',json=dict(target_id=new['target_id'],expected_revision=f.store.read()['revision']))
        self.assertEqual(blocked.status_code,422)
        self.assertEqual(blocked.json()['reason'],'CASH_RECONFIRMATION_REQUIRED')
        confirmed=http.post('/api/strategy-account/events',json=dict(expected_revision=f.store.read()['revision'],
            event=dict(event_id='settled-cash',kind='CASH_CONFIRM',amount='25',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        f.now+=timedelta(seconds=1)
        final=http.post('/api/strategy-account/target/preview',json=dict(target_id=new['target_id'],expected_revision=f.store.read()['revision']))
        self.assertEqual(final.status_code,200,final.text)
        self.assertTrue(any(o['side']=='BUY' and o['security_id']==original['security_id'] for o in final.json()['difference']['new_orders']))
        self.assertEqual(final.json()['difference']['spendable_cash'],'25')
        self.assertEqual(len(observed),1)
        self.assertEqual(targets.current()['target_id'],new['target_id'])



if __name__=='__main__':unittest.main()


