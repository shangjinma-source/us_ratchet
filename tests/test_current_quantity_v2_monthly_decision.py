from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import json
import gzip
import sqlite3
from contextlib import closing
import subprocess
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from hashlib import sha256
from data.current_quantity_v2_monthly_decision import QuantityV2MonthlyDecisionRegistry
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_research_capital_decision_v2 import VERSION
from data.current_quantity_v2_paper_chain import review_chain
from test_current_quantity_portfolio_research_v2 import fixture as training_fixture
from test_current_quantity_v2_paper_chain import ready


def fixture(folder,state=None):
    state=ready()[0] if state is None else state;ledger=state['ledger'];root=Path(folder)/'training';root.mkdir()
    _,_,descriptor=training_fixture(root,128)
    files={p:(root/p).read_bytes() for p in descriptor['source_hashes']}
    data=json.loads(files['input.json']);day='2026-10-30'
    data['search_arguments'].update(decision_date=day,quote_as_of=day,scenario_dates=['2026-09-30',day])
    for q in data['valuation_quotes']:q['as_of']=day
    for sid in ('A','B'):
        raw=json.loads(files[sid+'.json']);raw['chart']['result'][0]['timestamp']=[int(datetime(2026,10,d,20,tzinfo=timezone.utc).timestamp()) for d in (29,30,31)]
        files[sid+'.json']=canonical(raw)
    files['input.json']=canonical(data)
    now=datetime(2026,11,2,15,tzinfo=timezone.utc)
    files['calendar.json']=canonical(dict(decision_date=day,target_month='2026-11',active_date='2026-11-02',decision_close_at='2026-10-30T20:00:00+00:00',active_open_at='2026-11-02T14:30:00+00:00',source_references=['calendar-source']))
    files['calendar-source']=b'synthetic official-calendar fixture, not exchange certification'
    files['identities.json']=canonical(dict(securities=data['search_arguments']['metadata'],source_references=['calendar-source']))
    files['admission.json']=canonical(dict(status='ADMITTED_MONTHLY_FULL_ACCOUNT_V2',method=VERSION,account_id=ledger['account_id'],state_revision=ledger['revision'],target_month='2026-11',input_path='input.json',input_sha256=sha256(files['input.json']).hexdigest(),complete_candidate_domain=True,mature_training_reviewed=True,pending_rights=[],reviewed_at=now.isoformat(),source_references=['calendar-source']))
    package=dict(files=files,source_hashes={p:sha256(v).hexdigest() for p,v in files.items()},documents=dict(training='input.json',admission='admission.json',calendar='calendar.json',identities='identities.json'))
    registry=QuantityV2MonthlyDecisionRegistry(storage_root=Path(folder)/'registry',clock=lambda:now)
    return registry,state,package


class RegistryTests(unittest.TestCase):
    def test_real_isolated_full_account_immutable_reopen_and_package(self):
        with tempfile.TemporaryDirectory() as folder:
            registry,state,package=fixture(folder);before=deepcopy(state)
            self.assertFalse(registry.root.exists())
            result=registry.generate(state,package);decision=result['capital_decision']
            self.assertEqual(decision['binding']['shares'],state['ledger']['shares'])
            self.assertEqual(decision['available_cash'],state['ledger']['cash'])
            self.assertNotEqual(decision['investable_equity'],decision['available_cash'])
            key=result['registration_id'];result['capital_decision']['target_quantities'].clear()
            reopened=QuantityV2MonthlyDecisionRegistry(storage_root=registry.root,clock=lambda:self.fail('read clock'))
            self.assertTrue(reopened.read(key,state)['capital_decision']['target_quantities'])
            with patch('data.current_quantity_v2_monthly_decision.subprocess.run',side_effect=AssertionError('search on retry')):
                self.assertEqual(registry.generate(state,package)['registration_id'],key)
                saved=reopened.decision_package(key,state)
            self.assertEqual(set(saved['documents']),{'capital_decision','target_mandate','identities'})
            self.assertEqual(state,before)
            blob=registry.root/'inputs'/package['source_hashes']['A.json'];blob.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'REGISTRY_SOURCE_CHANGED'):reopened.read(key,state)

    def test_historical_audit_snapshot_integrity_and_readonly_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            registry,state,package=fixture(folder)
            result=registry.generate(state,package);key=result['registration_id'];aid=state['ledger']['account_id']
            path=registry.root/'inputs'/(key+'.state.json');saved=path.read_bytes()
            def forbidden(*a,**k):raise AssertionError('audit side effect')
            reopened=QuantityV2MonthlyDecisionRegistry(storage_root=registry.root,clock=forbidden)
            with patch('data.current_quantity_v2_monthly_decision.subprocess.run',side_effect=forbidden):
                audit=reopened.audit(key,aid)
                self.assertEqual(audit['result'],result);self.assertTrue(audit['audit_only'])
                self.assertFalse(audit['selected_for_current_account']);self.assertTrue(audit['execution_blocked'])
                with self.assertRaisesRegex(ValueError,'ACCOUNT_BINDING_MISMATCH'):reopened.audit(key,'other')
                path.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'SNAPSHOT_CHANGED'):reopened.audit(key,aid)
                path.write_bytes(saved);path.unlink()
                with self.assertRaisesRegex(ValueError,'SNAPSHOT_UNAVAILABLE'):reopened.audit(key,aid)
                self.assertEqual(registry.generate(state,package),result)
                self.assertFalse(path.exists()) # Cached success cannot invent old evidence.

    def test_failed_and_unfinished_audit_and_legacy_retry_no_backfill(self):
        with tempfile.TemporaryDirectory() as folder:
            registry,state,p=fixture(folder);aid=state['ledger']['account_id']
            with patch('data.current_quantity_v2_monthly_decision.subprocess.run',side_effect=subprocess.TimeoutExpired('SECRET',300)):
                with self.assertRaises(subprocess.TimeoutExpired):registry.generate(state,p)
            with closing(sqlite3.connect(registry.root/'monthly_decisions.sqlite3')) as con:
                key=con.execute('SELECT id FROM monthly_decisions').fetchone()[0]
            result=registry.audit(key,aid)
            self.assertEqual(result['result']['status'],'FAILED');self.assertNotIn('SECRET',json.dumps(result))
            path=registry.root/'inputs'/(key+'.state.json');path.unlink()
            result=registry.generate(state,p,retry_failed=True)
            self.assertEqual(result['status'],'READY');self.assertFalse(path.exists())
            with self.assertRaisesRegex(ValueError,'SNAPSHOT_UNAVAILABLE'):registry.audit(key,aid)
        with tempfile.TemporaryDirectory() as folder:
            registry,state,p=fixture(folder);result=registry.generate(state,p);key=result['registration_id']
            with closing(sqlite3.connect(registry.root/'monthly_decisions.sqlite3')) as con:
                con.execute("UPDATE monthly_decisions SET status='ATTEMPT_STARTED'");con.commit()
            registry.clock=lambda: self.fail('audit clock')
            with patch('data.current_quantity_v2_monthly_decision.subprocess.run',side_effect=AssertionError('audit worker')):
                audit=registry.audit(key,state['ledger']['account_id'])
            self.assertEqual(audit['result']['status'],'ATTEMPT_STARTED')
            self.assertEqual(audit['result']['worker_liveness'],'UNKNOWN')

    def test_preflight_rejects_missing_held_wrong_account_and_coordinate(self):
        for mode in ('account','missing','price','open'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                registry,state,p=fixture(folder)
                if mode=='account':
                    d=json.loads(p['files']['admission.json']);d['state_revision']='wrong';p['files']['admission.json']=canonical(d)
                elif mode=='missing':
                    d=json.loads(p['files']['input.json']);d['valuation_quotes']=d['valuation_quotes'][1:];p['files']['input.json']=canonical(d)
                elif mode=='price':
                    d=json.loads(p['files']['A.json']);d['chart']['result'][0]['indicators']['quote'][0]['close'][1]=59;p['files']['A.json']=canonical(d)
                else:state['ledger']['cash']='999'
                p['source_hashes']={k:sha256(v).hexdigest() for k,v in p['files'].items()}
                with patch('data.current_quantity_v2_monthly_decision.subprocess.run',side_effect=AssertionError('must not search')):
                    with self.assertRaises(ValueError):registry.generate(state,p)
                self.assertFalse(registry.root.exists())

    def test_timeout_explicit_retry_and_stuck_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            registry,state,p=fixture(folder)
            with patch('data.current_quantity_v2_monthly_decision.subprocess.run',side_effect=subprocess.TimeoutExpired('worker',300)):
                with self.assertRaises(subprocess.TimeoutExpired):registry.generate(state,p)
            db=registry.root/'monthly_decisions.sqlite3'
            with closing(sqlite3.connect(db)) as c:key,status=c.execute('SELECT id,status FROM monthly_decisions').fetchone()
            self.assertEqual(status,'FAILED');self.assertEqual(registry.read(key,state)['status'],'FAILED')
            with self.assertRaisesRegex(ValueError,'RETRY_REQUIRED'):registry.generate(state,p)
            result=registry.generate(state,p,retry_failed=True);self.assertEqual(result['status'],'READY')
            with closing(sqlite3.connect(db)) as c:c.execute("UPDATE monthly_decisions SET status='ATTEMPT_STARTED'");c.commit()
            reopened=QuantityV2MonthlyDecisionRegistry(storage_root=registry.root,clock=registry.clock)
            with patch('data.current_quantity_v2_monthly_decision.subprocess.run',side_effect=AssertionError('unknown orphan must not rerun')):
                with self.assertRaisesRegex(ValueError,'IN_PROGRESS'):reopened.generate(state,p,retry_failed=True)

    def test_gzip_and_worker_cross_month_final_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            registry,state,p=fixture(folder)
            for sid in ('A','B'):
                p['files'][sid+'.json']=gzip.compress(p['files'][sid+'.json'])
                p['source_hashes'][sid+'.json']=sha256(p['files'][sid+'.json']).hexdigest()
            actual=subprocess.run;clock=[datetime(2026,11,30,23,tzinfo=timezone.utc)];registry.clock=lambda:clock[0]
            def crosses(*args,**kwargs):
                result=actual(*args,**kwargs);clock[0]=datetime(2026,12,1,15,tzinfo=timezone.utc);return result
            with patch('data.current_quantity_v2_monthly_decision.subprocess.run',side_effect=crosses):
                with self.assertRaisesRegex(ValueError,'MONTHLY_CALENDAR_MISMATCH'):registry.generate(state,p)
            with closing(sqlite3.connect(registry.root/'monthly_decisions.sqlite3')) as c:
                self.assertEqual(c.execute('SELECT status FROM monthly_decisions').fetchone()[0],'FAILED')

    def test_registered_decision_through_actual_raw_source_bridge(self):
        from test_current_quantity_v2_monthly_sources import fixture as source_fixture
        from data.current_quantity_v2_monthly_service import QuantityV2MonthlySourceBridge
        with tempfile.TemporaryDirectory() as folder:
            provider,paper,state,_,clock,calls,base=source_fixture(folder)
            registry,_,p=fixture(folder,state)
            registry.clock=lambda:clock[0]
            identities=json.loads(base['files'][base['documents']['identities']])
            data=json.loads(p['files']['input.json']);data['search_arguments']['metadata']=identities['securities']
            p['files']['input.json']=canonical(data);p['files']['identities.json']=canonical(identities)
            admission=json.loads(p['files']['admission.json']);admission['input_sha256']=sha256(p['files']['input.json']).hexdigest();p['files']['admission.json']=canonical(admission)
            p['files']={**base['files'],**p['files']};p['source_hashes']={k:sha256(v).hexdigest() for k,v in p['files'].items()}
            result=registry.generate(state,p);did=result['capital_decision']['decision_id']
            provider.decision_reader=lambda chain:registry.decision_package(result['registration_id'],chain)
            oldreview=provider.review_reader
            def review(snapshot):
                reviewed=oldreview(snapshot)
                path=reviewed['documents']['unit_continuity'];units=json.loads(reviewed['files'][path])
                for sid,unit in units.items():
                    unit['capital_decision_id']=did;unit['valuation_source_references']=[sid+'.json']
                reviewed['files'][path]=canonical(units);reviewed['source_hashes'][path]=sha256(reviewed['files'][path]).hexdigest()
                return reviewed
            provider.review_reader=review
            provider.capture(state,expected_decision_id=did)
            bridge=QuantityV2MonthlySourceBridge(store=paper.store,resolver=provider.resolve,clock=lambda:clock[0])
            v=bridge.preview(account_id=state['ledger']['account_id'],decision_id=did,expected_revision=state['ledger']['revision'])
            self.assertEqual(v['status'],'READY');self.assertEqual(v['capital_decision_id'],did)
            self.assertEqual(calls,['AAA','BBB']);self.assertEqual(paper.store.read(state['ledger']['account_id']),state)
            changed=paper.store.accept_monthly_retarget(account_id=state['ledger']['account_id'],
                proposal_id=v['proposal_id'],operation_id='audit-account-change',
                expected_revision=state['ledger']['revision'],
                factory=lambda chain,now:bridge.monthly_resolver(chain,v['proposal_id'],now),clock=lambda:clock[0])
            self.assertNotEqual(changed['ledger']['revision'],state['ledger']['revision'])
            with self.assertRaisesRegex(ValueError,'REGISTERED_ACCOUNT_CHANGED'):
                registry.read(result['registration_id'],changed)
            with self.assertRaisesRegex(ValueError,'REGISTERED_ACCOUNT_CHANGED'):
                registry.decision_package(result['registration_id'],changed)
            historical=registry.audit(result['registration_id'],state['ledger']['account_id'])
            self.assertEqual(historical['result'],result)
            self.assertFalse(historical['selected_for_current_account'])


    def test_no_selection_terminal_and_review_before_data_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            registry,state,p=fixture(folder)
            data=json.loads(p['files']['input.json']);data['search_arguments']['max_objective_evaluations']=1
            p['files']['input.json']=canonical(data);p['source_hashes']['input.json']=sha256(p['files']['input.json']).hexdigest()
            admission=json.loads(p['files']['admission.json']);admission['input_sha256']=p['source_hashes']['input.json']
            p['files']['admission.json']=canonical(admission);p['source_hashes']['admission.json']=sha256(p['files']['admission.json']).hexdigest()
            result=registry.generate(state,p);self.assertEqual(result['status'],'INCOMPLETE')
            with self.assertRaisesRegex(ValueError,'MONTHLY_RESULT_NOT_READY'):registry.decision_package(result['registration_id'],state)
            with patch('data.current_quantity_v2_monthly_decision.subprocess.run',side_effect=AssertionError('must not rerun terminal')):
                self.assertEqual(registry.generate(state,p),result)
            admission['reviewed_at']='2026-10-29T20:00:00+00:00';p['files']['admission.json']=canonical(admission);p['source_hashes']['admission.json']=sha256(p['files']['admission.json']).hexdigest()
            with self.assertRaisesRegex(ValueError,'MONTHLY_ADMISSION_SOURCE_REQUIRED'):registry.generate(state,p)

    def test_concurrent_single_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            registry,state,p=fixture(folder);started=Event();release=Event();actual=subprocess.run;calls=[]
            def blocked(*args,**kwargs):calls.append(1);started.set();self.assertTrue(release.wait(5));return actual(*args,**kwargs)
            with patch('data.current_quantity_v2_monthly_decision.subprocess.run',side_effect=blocked):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first=pool.submit(registry.generate,state,p);self.assertTrue(started.wait(5))
                    with self.assertRaisesRegex(ValueError,'IN_PROGRESS'):QuantityV2MonthlyDecisionRegistry(storage_root=registry.root,clock=registry.clock).generate(state,p)
                    release.set();self.assertEqual(first.result()['status'],'READY')
            self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
