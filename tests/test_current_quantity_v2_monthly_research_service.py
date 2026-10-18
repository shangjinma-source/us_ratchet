from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
import subprocess
import sqlite3
from datetime import datetime,timezone
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_monthly_research_service import QuantityV2MonthlyResearchService
from test_current_quantity_v2_monthly_training import fixture as training_fixture
from test_current_quantity_v2_monthly_sources import fixture as source_fixture


def fixture(folder):
    source,paper,state,_,clock,calls,base=source_fixture(folder)
    registry,_,package,_=training_fixture(folder);registry.clock=lambda:clock[0]
    files=package['files'];files.update({p:b for p,b in base['files'].items() if p not in files})
    identities=json.loads(base['files'][base['documents']['identities']]);files['identities.json']=canonical(identities)
    manifest=json.loads(files['manifest.json']);manifest['candidates'][0]['issuer_id']=identities['securities']['B']['issuer_id']
    raw=json.loads(files['A.held'])
    for k in ('open','high','low','close'):raw['chart']['result'][0]['indicators']['quote'][0][k]=[500]
    files['A.held']=canonical(raw)
    review=json.loads(files['account_review.json']);review.update(account_id=state['ledger']['account_id'],state_revision=state['ledger']['revision'],reviewed_at=clock[0].isoformat());files['account_review.json']=canonical(review)
    manifest['source_hashes']={p:sha256(v).hexdigest() for p,v in files.items() if p!='manifest.json'};files['manifest.json']=canonical(manifest)
    package['source_hashes']={p:sha256(v).hexdigest() for p,v in files.items()}
    supplied=dict(source_package=package,manifest_path='manifest.json',calendar_path='calendar.json',account_review_path='account_review.json',identities_path='identities.json',held_bar_sources={'A':'A.held'})
    service=QuantityV2MonthlyResearchService(store=paper.store,registry=registry,selection_root=Path(folder)/'selection',training_reader=lambda _:deepcopy(supplied),clock=lambda:clock[0])
    return service,state,supplied,source,paper,clock


class ResearchTests(unittest.TestCase):
    def test_actual_generate_reopen_read_and_immutable_public(self):
        with TemporaryDirectory() as folder:
            service,state,supplied,_,paper,clock=fixture(folder);aid=state['ledger']['account_id'];rev=state['ledger']['revision']
            self.assertFalse(service.path.exists())
            self.assertEqual(service.current(account_id=aid)['status'],'UNAVAILABLE')
            self.assertFalse(service.path.exists())
            result=service.generate(account_id=aid,expected_revision=rev);self.assertEqual(result['status'],'READY')
            self.assertNotIn('capital_decision',result);self.assertNotIn('source_hashes',result);key=result['registration_id']
            self.assertTrue(result['portfolio']['stocks']);self.assertIsNone(result['portfolio']['executable_buy_quantities'])
            text=json.dumps(result);self.assertNotIn('source_hashes',text);self.assertNotIn('source_references',text);self.assertNotIn('files',text)
            def forbidden(*a):raise AssertionError('read invoked compiler/source/clock')
            reopened=QuantityV2MonthlyResearchService(store=paper.store,registry=service.registry,selection_root=service.path.parent,training_reader=forbidden,clock=forbidden)
            with patch('subprocess.run',side_effect=forbidden):
                self.assertEqual(reopened.read(account_id=aid,registration_id=key),result)
                self.assertEqual(reopened.current(account_id=aid),result)
                package=reopened.decision_reader(state);package['files'].clear();self.assertTrue(reopened.decision_reader(state)['files'])
                self.assertEqual(service.generate(account_id=aid,expected_revision=rev),result)
            self.assertEqual(paper.store.read(aid),state)
            service.training_reader=lambda _:None
            with self.assertRaisesRegex(ValueError,'MONTHLY_RESEARCH_UNAVAILABLE'):service.generate(account_id=aid,expected_revision=rev)
            self.assertFalse(service.read(account_id=aid,registration_id=key)['selected_for_current_account'])
            with self.assertRaisesRegex(ValueError,'SELECTION_UNAVAILABLE'):service.decision_reader(state)

    def test_attempt_history_failures_success_isolation_and_read_only(self):
        with TemporaryDirectory() as folder:
            service,state,supplied,_,paper,clock=fixture(folder)
            aid=state['ledger']['account_id'];rev=state['ledger']['revision']
            self.assertEqual(service.history(account_id=aid)['events'],[])
            self.assertFalse(service.path.exists())
            def failed(_):raise ValueError('SECRET arbitrary token must not be recorded')
            service.training_reader=failed
            for _ in range(2):
                with self.assertRaises(ValueError):service.generate(account_id=aid,expected_revision=rev)
            before=service.history(account_id=aid)
            self.assertEqual(len(before['events']),4)
            self.assertNotIn('SECRET',json.dumps(before))
            self.assertEqual(before['events'][-1]['reason'],'SOURCE_VALIDATION_FAILED')
            service._fail(aid,2,'ValueError','SOURCE_VALIDATION_FAILED')
            self.assertEqual(service.history(account_id=aid),before)
            with self.assertRaisesRegex(ValueError,'ATTEMPT_TERMINAL_CONFLICT'):
                service._fail(aid,2,'TimeoutError','SOURCE_TIMEOUT')
            service.training_reader=lambda _:deepcopy(supplied)
            result=service.generate(account_id=aid,expected_revision=rev)
            self.assertEqual(result['status'],'READY')
            history=service.history(account_id=aid)
            self.assertEqual(history['events'][:4],before['events'])
            self.assertEqual(history['events'][-1]['status'],'READY')
            self.assertEqual(history['events'][-1]['state_revision'],rev)
            self.assertTrue(all(e['recorded_at'].endswith('+00:00') for e in history['events']))
            self.assertEqual(service.history(account_id='other-account')['events'],[])
            with closing(sqlite3.connect(service.path)) as con:
                with self.assertRaises(sqlite3.IntegrityError):con.execute('DELETE FROM monthly_attempt_events')
            def forbidden(*a,**k):raise AssertionError('history performed side effect')
            service.clock=forbidden;service.training_reader=forbidden
            with patch.object(service.store,'read',side_effect=forbidden),patch('subprocess.run',side_effect=forbidden):
                self.assertEqual(service.history(account_id=aid),history)
            self.assertEqual(paper.store.read(aid),state)

    def test_history_does_not_migrate_legacy_database(self):
        with TemporaryDirectory() as folder:
            service,state,_,_,_,_=fixture(folder)
            service.path.parent.mkdir(parents=True)
            with closing(sqlite3.connect(service.path)) as con:
                con.execute('CREATE TABLE monthly_selection(account_id TEXT PRIMARY KEY,attempt INTEGER,chain_hash TEXT,status TEXT,registration_id TEXT,reason TEXT)')
                con.execute('INSERT INTO monthly_selection VALUES(?,?,?,?,?,?)',(state['ledger']['account_id'],7,'old','FAILED',None,'ValueError'))
                con.commit()
            before=service.path.read_bytes()
            history=service.history(account_id=state['ledger']['account_id'])
            self.assertEqual(history['coverage'],'LEGACY_DATABASE_WITHOUT_ATTEMPT_HISTORY')
            self.assertFalse(history['legacy_history_complete']);self.assertEqual(history['events'],[])
            self.assertEqual(service.path.read_bytes(),before)

    def test_cross_instance_latest_failure_prevents_late_publish(self):
        with TemporaryDirectory() as folder:
            service,state,supplied,_,paper,clock=fixture(folder);aid=state['ledger']['account_id'];rev=state['ledger']['revision']
            entered=Event();release=Event();actual=subprocess.run
            def slow(*a,**k):entered.set();self.assertTrue(release.wait(10));return actual(*a,**k)
            second=QuantityV2MonthlyResearchService(store=paper.store,registry=service.registry,selection_root=service.path.parent,training_reader=lambda _:None,clock=lambda:clock[0])
            with patch('subprocess.run',side_effect=slow),ThreadPoolExecutor(1) as pool:
                first=pool.submit(service.generate,account_id=aid,expected_revision=rev);self.assertTrue(entered.wait(10))
                pending=second.current(account_id=aid);self.assertEqual(pending['status'],'PENDING');self.assertEqual(pending['worker_liveness'],'UNKNOWN')
                with self.assertRaises(ValueError):second.generate(account_id=aid,expected_revision=rev)
                release.set()
                with self.assertRaisesRegex(ValueError,'SUPERSEDED'):first.result()
            with self.assertRaisesRegex(ValueError,'SELECTION_UNAVAILABLE'):service.decision_reader(state)
            events=service.history(account_id=aid)['events']
            self.assertEqual(len(events),4)
            self.assertEqual(next(e for e in events if e['attempt']==1 and e['phase']=='TERMINAL')['reason'],'MONTHLY_RESEARCH_SUPERSEDED')
            self.assertEqual(paper.store.read(aid),state)

    def test_incomplete_is_recoverable_but_not_selected(self):
        from data.current_quantity_v2_monthly_training import build_monthly_training_package as compile_actual
        with TemporaryDirectory() as folder:
            service,state,_,_,_,_=fixture(folder)
            def tiny_budget(*args,**kwargs):
                # Test-only worker budget: still real raw compilation and real
                # isolated worker; production compiler's 8192 policy is unchanged.
                package=compile_actual(*args,**kwargs);files=package['files'];pins=package['source_hashes'];docs=package['documents']
                data=json.loads(files[docs['training']]);data['search_arguments']['max_objective_evaluations']=1
                files[docs['training']]=canonical(data);pins[docs['training']]=sha256(files[docs['training']]).hexdigest()
                admission=json.loads(files[docs['admission']]);admission['input_sha256']=pins[docs['training']]
                files[docs['admission']]=canonical(admission);pins[docs['admission']]=sha256(files[docs['admission']]).hexdigest()
                return package
            aid=state['ledger']['account_id']
            with patch('data.current_quantity_v2_monthly_research_service.build_monthly_training_package',side_effect=tiny_budget):
                result=service.generate(account_id=aid,expected_revision=state['ledger']['revision'])
            self.assertEqual(result['status'],'INCOMPLETE');self.assertFalse(result['selected_for_current_account'])
            self.assertEqual(service.current(account_id=aid),result)
            with self.assertRaisesRegex(ValueError,'SELECTION_UNAVAILABLE'):service.decision_reader(state)

    def test_publication_wait_rechecks_month_under_paper_lock(self):
        with TemporaryDirectory() as folder:
            service,state,_,_,paper,clock=fixture(folder);aid=state['ledger']['account_id'];rev=state['ledger']['revision']
            generated=Event();release=Event();actual=service.registry.generate
            def paused(*a,**k):
                result=actual(*a,**k);generated.set();self.assertTrue(release.wait(10));return result
            service.registry.generate=paused
            with ThreadPoolExecutor(1) as pool:
                future=pool.submit(service.generate,account_id=aid,expected_revision=rev);self.assertTrue(generated.wait(10))
                con=sqlite3.connect(paper.store.path,isolation_level=None)
                try:
                    con.execute('BEGIN IMMEDIATE');release.set();clock[0]=datetime(2026,12,1,15,tzinfo=timezone.utc);con.commit()
                finally:con.close()
                with self.assertRaisesRegex(ValueError,'MONTHLY_RESEARCH_EXPIRED'):future.result()
            self.assertEqual(service.current(account_id=aid)['status'],'FAILED');self.assertEqual(paper.store.read(aid),state)
            events=service.history(account_id=aid)['events']
            self.assertEqual(events[0]['request_month'],events[-1]['request_month'])
            self.assertNotEqual(events[-1]['request_month'],'2026-12')

    def test_real_account_change_before_worker_does_not_publish(self):
        from data.current_quantity_v2_monthly_service import QuantityV2MonthlySourceBridge
        with TemporaryDirectory() as folder:
            service,state,supplied,source,paper,clock=fixture(folder);aid=state['ledger']['account_id'];rev=state['ledger']['revision']
            source.capture(state);did=source._current['decision_id'] if 'decision_id' in source._current else json.loads(source.decision_reader(state)['files'][source.decision_reader(state)['documents']['capital_decision']])['decision_id']
            bridge=QuantityV2MonthlySourceBridge(store=paper.store,resolver=source.resolve,clock=lambda:clock[0])
            p=bridge.preview(account_id=aid,decision_id=did,expected_revision=rev)
            def changed(_):
                paper.store.accept_monthly_retarget(account_id=aid,proposal_id=p['proposal_id'],operation_id='other-monthly',expected_revision=rev,factory=lambda s,n:bridge.monthly_resolver(s,p['proposal_id'],n),clock=lambda:clock[0])
                return deepcopy(supplied)
            service.training_reader=changed
            with patch('subprocess.run',side_effect=AssertionError('stale account must not search')):
                with self.assertRaisesRegex(ValueError,'ACCOUNT_CHANGED'):service.generate(account_id=aid,expected_revision=rev)
            with self.assertRaisesRegex(ValueError,'SELECTION_UNAVAILABLE'):service.decision_reader(paper.store.read(aid))

if __name__=='__main__':unittest.main()
