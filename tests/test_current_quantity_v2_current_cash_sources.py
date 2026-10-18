from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event,get_ident
import unittest
from unittest.mock import patch
import subprocess
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_portfolio_research_v2 import fixture as tiny_fixture
from test_current_quantity_v2_intraday_reference import NOW,raw
from data.current_quantity_portfolio_research_v2 import CurrentQuantityPortfolioResearchV2
from data.current_quantity_v2_verified_snapshot_bundle import VerifiedSnapshotBundleService
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources,MANIFEST
from data.current_quantity_v2_current_cash_service import CurrentQuantityV2CurrentCashService
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from api.current_quantity_v2_difference import create_router as difference_router
from api.current_quantity_v2_paper import create_router as paper_router,PREFIX


def snapshot_fixture(root):
    _,_,descriptor=tiny_fixture(root)
    def put(name,value):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);data=json.dumps(value).encode();path.write_bytes(data)
        descriptor['source_hashes'][name]=sha256(data).hexdigest()
    evidence='identity/official-observation.json';put(evidence,{'synthetic':True})
    admission='identity/admission.json'
    rows=[dict(security_id=sid,ticker=ticker,issuer_id=issuer,security_class='Common stock',status='READY_CONDITIONAL_IDENTITY',
        identity_reviewed=True,no_unresolved_identifier_conflict=True,unresolved=[],source_references=[evidence.replace('/','\\')])
        for sid,ticker,issuer in [('A','AAA','IA'),('B','BBB','IB')]]
    put(admission,dict(rows=rows,source_hashes={evidence.replace('/','\\'):descriptor['source_hashes'][evidence]}))
    put(MANIFEST,dict(candidates=[dict(security_id=r['security_id'],ticker=r['ticker'],issuer_id=r['issuer_id'],
        identity_reviewed=True,status='READY_CONDITIONAL',identity_source_references=[admission,evidence],true_share_events=[]) for r in rows]))
    snapshots=CurrentQuantityPortfolioResearchV2(root=root,source_loader=lambda:deepcopy(descriptor))
    with patch('data.current_quantity_portfolio_research_v2.subprocess.run',wraps=subprocess.run) as worker:
        view=snapshots.calculate('110');assert worker.call_count==1
    decision=snapshots.decision(view['research_id']);anchor=next(iter(decision['binding']['source_hashes']))
    mandate=dict(schema='V2_INITIAL_EXECUTION_MONTH_V1',mode='INITIAL_CURRENT_MONTH_BOOTSTRAP',
        decision_date=decision['decision_date'],target_month='2026-10',first_active_session=decision['decision_date'],
        original_source_hashes=deepcopy(decision['binding']['source_hashes']),source_hashes={},calendar_path=None)
    (root/'month.json').write_bytes(json.dumps(mandate).encode())
    return VerifiedSnapshotBundleService(snapshots),view


def month_config(root):
    return dict(path='month.json',sha256=sha256((Path(root)/'month.json').read_bytes()).hexdigest())


class CurrentCashSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory();cls.root=Path(cls.temp.name);cls.snapshots,cls.view=snapshot_fixture(cls.root)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def provider(self,fetch=None):
        calls=[];clock=[NOW]
        def getter(ticker):calls.append(ticker);return raw(ticker,10)
        p=CurrentQuantityV2CurrentCashSources(root=self.root,snapshot_service=self.snapshots,server_account_id='fixed-paper-pool',
            fetch=fetch or getter,clock=lambda:clock[0],execution_month_mandate=month_config(self.root))
        return p,calls,clock

    def test_capture_once_resolve_zero_fetch_actual_http_preview_accept(self):
        p,calls,clock=self.provider();did=self.view['decision_id'];original=self.snapshots.decision(did[:24])
        with patch.object(self.snapshots,'calculate',side_effect=AssertionError('no search')):
            cap=p.capture(did);self.assertEqual(cap['selected_security_ids'],['A','B']);self.assertEqual(calls,['AAA','BBB'])
            first=p.resolve(did);self.assertEqual(first['capital_decision'],original);self.assertEqual(first['account_state']['shares'],{})
            self.assertEqual(first['account_state']['account_id'],'fixed-paper-pool')
            first['account_state']['cash']='999';self.assertEqual(p.resolve(did)['account_state']['cash'],'110')
            with TemporaryDirectory() as folder:
                source=CurrentQuantityV2CurrentCashService(resolver=p.resolve,account_reader=p.account_reader,clock=lambda:clock[0])
                paper=QuantityV2PaperService(store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3'),initial_resolver=source.initial_resolver,clock=lambda:clock[0])
                app=FastAPI();app.include_router(difference_router(service=source));app.include_router(paper_router(service=paper))
                with TestClient(app) as client:
                    preview=client.post('/api/current_portfolio_research/difference',json={'decision_id':did})
                    self.assertEqual(preview.status_code,200,preview.text);proposal=preview.json()
                    clock[0]+=timedelta(seconds=1)
                    r=client.post(PREFIX+'/accept',json=dict(account_id='fixed-paper-pool',proposal_id=proposal['proposal_id'],operation_id='capture-accept'))
                    self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['cash'],'110')
                    self.assertEqual(r.json()['target_quantities'],{'A':6,'B':4})
            self.assertEqual(calls,['AAA','BBB']);self.assertEqual(self.snapshots.decision(did[:24]),original)

    def test_optional_genesis_audit_partial_failure_and_success_restart(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'audit';p,calls,clock=self.provider();p.audit_storage_root=path
            self.assertFalse(path.exists());original=p.fetch
            def second_failure(ticker):
                if ticker=='BBB':raise ValueError('PRIVATE upstream')
                return original(ticker)
            p.fetch=second_failure
            with self.assertRaises(ValueError) as failure:p.capture(self.view['decision_id'])
            failed=p.audit(failure.exception.capture_id,'fixed-paper-pool')
            self.assertEqual(failed['status'],'FAILED');self.assertEqual(len(failed['raw_files']),1)
            self.assertEqual(failed['binding_scope']['binding_kind'],'DECLARED_EMPTY_GENESIS')
            self.assertIsNone(failed['binding_scope']['chain_sha256'])
            self.assertNotIn('PRIVATE',json.dumps(failed['events']))
            p.fetch=original;captured=p.capture(self.view['decision_id'])
            receipt=p.audit(captured['capture_id'],'fixed-paper-pool')['events'][-1]['payload']['receipt']
            manifest=json.loads(Path(receipt['path']).read_bytes())
            self.assertEqual(manifest['source_hashes'],p.resolve(self.view['decision_id'])['execution_package']['source_hashes'])
            self.assertEqual(manifest['audit_context']['genesis_declaration']['purpose'],'PAPER_INITIALIZATION_NOT_BROKER_BALANCE')
            def forbidden(*a,**k):raise AssertionError('audit side effect')
            restarted=CurrentQuantityV2CurrentCashSources(root=self.root,snapshot_service=None,server_account_id='fixed-paper-pool',
                fetch=forbidden,clock=forbidden,audit_storage_root=path)
            self.assertEqual(restarted.audit(captured['capture_id'],'fixed-paper-pool')['status'],'CAPTURED')
            with self.assertRaisesRegex(ValueError,'CAPTURE_REQUIRED'):restarted.resolve(self.view['decision_id'])
            with self.assertRaisesRegex(ValueError,'ACCOUNT_MISMATCH'):restarted.audit(captured['capture_id'],'other')
            # Even internally rehashed archive bytes cannot bind another account
            # context to this declared genesis scope.
            manifest['audit_context']['account_state']['account_id']='other'
            changed=json.dumps(manifest).encode();Path(receipt['path']).write_bytes(changed)
            audit_dir=path/'captures'/'audit'/captured['capture_id'];terminal=sorted(audit_dir.iterdir())[-1]
            event=json.loads(terminal.read_bytes());event['payload']['receipt']['sha256']=sha256(changed).hexdigest()
            terminal.write_bytes(json.dumps(event).encode())
            with self.assertRaisesRegex(ValueError,'GENESIS_AUDIT_CONTEXT_MISMATCH'):
                restarted.audit(captured['capture_id'],'fixed-paper-pool')


    def test_static_prearchive_is_durable_before_fetch_without_authority(self):
        from data.current_quantity_v2_monthly_capture_audit import publish_blob
        with TemporaryDirectory() as folder:
            p,calls,_=self.provider();p.audit_storage_root=Path(folder)/'audit'
            did=self.view['decision_id'];_,_,files,_=p._base(did);original=p.fetch
            def fetch(ticker):
                self.assertIsNone(p._current)
                for data in files.values():
                    self.assertEqual((p.audit_storage_root/'blobs'/sha256(data).hexdigest()).read_bytes(),data)
                self.assertFalse(list((p.audit_storage_root/'captures').glob('*.json')))
                return original(ticker)
            p.fetch=fetch
            with patch('data.current_quantity_v2_monthly_capture_audit.publish_blob',wraps=publish_blob) as publish:
                p.capture(did)
                self.assertGreater(publish.call_count,len(files))
            self.assertEqual(calls,['AAA','BBB'])
            self.assertFalse(list(Path(folder).rglob('*.sqlite3')))

    def test_prearchive_failure_zero_fetch_and_source_change_final_rejected(self):
        from data.current_quantity_v2_monthly_capture_audit import publish_blob
        with TemporaryDirectory() as folder:
            p,calls,_=self.provider();p.audit_storage_root=Path(folder)/'audit'
            with patch('data.current_quantity_v2_monthly_capture_audit.publish_blob',side_effect=OSError('private')):
                with self.assertRaises(OSError) as failure:p.capture(self.view['decision_id'])
            self.assertEqual(calls,[]);self.assertIsNone(p._current)
            recorded=p.audit(failure.exception.capture_id,'fixed-paper-pool')
            self.assertEqual(recorded['events'][-1]['payload']['stage'],'STATIC_PREARCHIVE')
            self.assertEqual(recorded['status'],'FAILED');self.assertEqual(recorded['raw_files'],{})
            source=self.root/'identity/official-observation.json';old=source.read_bytes();changed=[]
            def drift(root,data,limit):
                result=publish_blob(root,data,limit)
                if not changed:source.write_bytes(b'drift');changed.append(True)
                return result
            try:
                with patch('data.current_quantity_v2_monthly_capture_audit.publish_blob',side_effect=drift):
                    with self.assertRaises(ValueError):p.capture(self.view['decision_id'])
                self.assertIsNone(p._current)
            finally:source.write_bytes(old)

    def test_superseded_static_prearchive_never_fetches(self):
        from data.current_quantity_v2_monthly_capture_audit import publish_blob
        with TemporaryDirectory() as folder:
            p,calls,_=self.provider();p.audit_storage_root=Path(folder)/'audit';once=[]
            def supersede(root,data,limit):
                result=publish_blob(root,data,limit)
                if not once:
                    with p.lock:p._attempt+=1
                    once.append(True)
                return result
            with patch('data.current_quantity_v2_monthly_capture_audit.publish_blob',side_effect=supersede):
                with self.assertRaisesRegex(ValueError,'SUPERSEDED'):p.capture(self.view['decision_id'])
            self.assertEqual(calls,[]);self.assertIsNone(p._current)

    def test_unconfigured_capture_does_not_prearchive(self):
        p,_,_=self.provider()
        with patch('data.current_quantity_v2_monthly_capture_audit.publish_blob',side_effect=AssertionError('no audit write')):
            p.capture(self.view['decision_id'])

    def test_archive_latency_cannot_admit_expired_genesis(self):
        from data.current_quantity_v2_monthly_capture_audit import CaptureAudit
        with TemporaryDirectory() as folder:
            p,_,clock=self.provider();p.audit_storage_root=Path(folder)/'audit';original=CaptureAudit.package
            def slow(audit,*args,**kwargs):
                result=original(audit,*args,**kwargs);clock[0]+=timedelta(minutes=5);return result
            with patch.object(CaptureAudit,'package',slow):
                with self.assertRaises(ValueError) as failure:p.capture(self.view['decision_id'])
            self.assertIsNone(p._current)
            self.assertEqual(p.audit(failure.exception.capture_id,'fixed-paper-pool')['status'],'FAILED')

    def test_base_bundle_single_full_load_and_legacy_still_reads_sources(self):
        p,_,_=self.provider();did=self.view['decision_id']
        with patch.object(self.snapshots._service,'_load',wraps=self.snapshots._service._load) as load:
            expected=p._base(did);self.assertEqual(load.call_count,1)
        with patch.object(self.snapshots,'verified_snapshot_bundle',None):
            with patch.object(p,'_read',wraps=p._read) as read:
                self.assertEqual(p._base(did),expected)
                self.assertEqual(read.call_count,len(expected[3]))
        original=self.snapshots.verified_snapshot_bundle
        def corrupt(rid):
            bundle=original(rid);bundle['files']['identity/official-observation.json']=b'bad';return bundle
        with patch.object(self.snapshots,'verified_snapshot_bundle',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_CHANGED'):p._base(did)

    def test_new_capture_failure_and_source_drift_never_return_old(self):
        p,calls,clock=self.provider();did=self.view['decision_id'];p.capture(did);saved=p.resolve(did)
        clock[0]+=timedelta(seconds=1);p.capture(did);self.assertNotEqual(saved,p.resolve(did))
        p.fetch=lambda ticker:(_ for _ in ()).throw(ValueError('network failure'))
        with self.assertRaises(ValueError):p.capture(did)
        with self.assertRaisesRegex(ValueError,'CAPTURE_REQUIRED'):p.resolve(did)
        p,calls,clock=self.provider();p.capture(did);path=self.root/'identity/official-observation.json';old=path.read_bytes()
        try:
            path.write_bytes(b'drift')
            with self.assertRaises(ValueError):p.resolve(did)
        finally:path.write_bytes(old)
        clock[0]+=timedelta(seconds=121)
        with self.assertRaises(ValueError):p.resolve(did)

    def test_slow_old_capture_cannot_overwrite_new_failure(self):
        entered=Event();release=Event();owner=[]
        def fetch(ticker):
            if not owner:owner.append(get_ident());entered.set();self.assertTrue(release.wait(5))
            if get_ident()==owner[0]:return raw(ticker,10)
            raise ValueError('latest failed')
        p,_,_=self.provider(fetch);did=self.view['decision_id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            old=pool.submit(p.capture,did);self.assertTrue(entered.wait(5))
            with self.assertRaises(ValueError):p.capture(did)
            release.set()
            with self.assertRaisesRegex(ValueError,'CAPTURE_SUPERSEDED'):old.result(5)
        with self.assertRaises(ValueError):p.resolve(did)

    def test_class_not_inferred_equity_or_known_action_and_unknown_decision_zero_fetch(self):
        p,calls,_=self.provider();did=self.view['decision_id'];decision,snapshot,files,pins=p._base(did)
        manifest=json.loads(files[MANIFEST]);manifest['candidates'][0]['true_share_events']=[{'date':'2026-10-14'}]
        bad=deepcopy(files);bad[MANIFEST]=json.dumps(manifest).encode()
        with self.assertRaisesRegex(ValueError,'KNOWN_POST'):p._identity(decision,bad,pins,'A','2026-10-15')
        bad=deepcopy(files);admission=json.loads(bad['identity/admission.json']);admission['rows'][0].pop('security_class')
        bad['identity/admission.json']=json.dumps(admission).encode()
        with self.assertRaisesRegex(ValueError,'CLASS_REQUIRED'):p._identity(decision,bad,pins,'A','2026-10-15')
        with self.assertRaises(ValueError):p.capture('f'*64)
        self.assertEqual(calls,[])


class ExplicitIdentityManifestTests(unittest.TestCase):
    def test_explicit_manifest_preserves_pin_and_class_requirements(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);name='identity/new-domain.json';evidence='identity/evidence.json';admission='identity/class.json'
            row=dict(security_id='A',ticker='AAA',issuer_id='IA',status='READY_CONDITIONAL_IDENTITY',
                     identity_reviewed=True,no_unresolved_identifier_conflict=True,unresolved=[],
                     security_class='Common stock',source_references=[evidence])
            files={evidence:b'{}'};pins={evidence:sha256(files[evidence]).hexdigest()}
            files[admission]=json.dumps(dict(rows=[row],source_hashes=dict(pins))).encode()
            files[name]=json.dumps(dict(candidates=[dict(security_id='A',ticker='AAA',issuer_id='IA',
                status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=[admission,evidence])])).encode()
            pins.update({p:sha256(raw).hexdigest() for p,raw in files.items()})
            source=CurrentQuantityV2CurrentCashSources(root=root,snapshot_service=None,server_account_id='test',identity_manifest_path=name)
            decision=dict(decision_date='2026-10-14',binding=dict(search_arguments=dict(metadata={'A':dict(ticker='AAA',issuer_id='IA')})))
            self.assertIn(name,source._identity(decision,files,pins,'A','2026-10-16')['source_references'])
            with self.assertRaisesRegex(ValueError,'CLASS_ADMISSION_SOURCE_MISMATCH'):
                source._identity(decision,files,{**pins,evidence:'0'*64},'A','2026-10-16')
            with self.assertRaisesRegex(ValueError,'SAFE_SOURCE_PATH_REQUIRED'):
                CurrentQuantityV2CurrentCashSources(root=root,snapshot_service=None,server_account_id='test',identity_manifest_path='../escape')

if __name__=='__main__':unittest.main()
