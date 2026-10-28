"""Synthetic exit authority with real source reviewer and immutable archive IO."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
import test_reentry_reference_evidence_v1 as source_fixture
from core.strategy_account_ledger import canonical
from data.strategy_daily_rebound_archive import archive_rebound_evidence
from data.reentry_reference_configuration_v1 import build_reference_sources, hashed


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=source_fixture.SourceTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;self.root=f.root
        (self.root/'data').mkdir(exist_ok=True)
        for name in ('reentry_reference_evidence_v1.py','saved_frontier_first_window_v1.py'):
            (self.root/'data'/name).write_bytes((Path('data')/name).read_bytes())
        source=dict(calendar=f.config['calendar'],identity=f.config['segments'][0]['identity'])
        self.source=f.put('source_configuration.json',source)
        receipt=dict(f.receipt,raw_path='daily.json')
        self.files={name:(self.root/name).read_bytes() for name in ('daily.json','rss.xml','rss_receipt.json','calendar.json')}
        self.files['receipt.json']=canonical(receipt)
        self.files['frontier/calendar.json']=self.files['calendar.json']
        self.files['frontier/capture.json']=canonical(dict(documents=dict(
            action_receipts={'S':'receipt.json'},rss_raw='rss.xml',rss_receipt='rss_receipt.json')))
        self.files['frontier/source-review.json']=canonical(dict(inputs=dict(histories={'S':dict(units={'basis_id':'u1'})})))
        self.state=dict(account_id='a',locks={'S':deepcopy(f.lock)})
        self.boundary=dict(status='SERVER_ARCHIVED_BOUNDARY_VERIFIED',
            decision_evidence=canonical(dict(account_id='a',session_date=f.days[0])),
            observation=dict(unit_ids={'S':'u1'},closes={'S':'100'}),archive_sha256='a'*64)

    def run_builder(self):
        receipt=canonical(dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',account_id='a',
            source_sha256={k:hashed(v) for k,v in self.files.items()}))
        archive=archive_rebound_evidence(root=self.root/'archive',receipt_bytes=receipt,files=self.files)
        return build_reference_sources(root=self.root,output_directory=self.root/'output',reference_state=self.state,
            reader_archive=archive,source_configuration_reference=self.source,
            exit_boundary_archive=SimpleNamespace(read_verified=lambda ref:deepcopy(self.boundary)),
            exit_boundary_references={'S':{}},decision_session=self.fixture.days[-1],as_of=self.fixture.now)

    def test_complete_real_reviewer_and_receipt_projection(self):
        result=self.run_builder()['locks']['S']
        self.assertEqual(result['status'],'REFERENCE_CONFIGURATION_READY_CONDITIONAL',result)
        import json
        config=json.loads((self.root/result['configuration_reference']['path']).read_bytes())
        projected=json.loads((self.root/config['segments'][0]['receipt']['path']).read_bytes())
        self.assertEqual(projected['received_at'],self.fixture.receipt['received_at'])
        self.assertEqual(projected['requested_through'],self.fixture.receipt['requested_through'])
        self.assertEqual(config['construction']['receipt_projection']['original_receipt']['sha256'],hashed(self.files['receipt.json']))

    def test_missing_domain_or_boundary_waits_without_disjoint(self):
        self.boundary={'status':'WAIT'}
        result=self.run_builder();self.assertEqual(result['locks']['S']['status'],'WAIT_REFERENCE_CONFIGURATION')
        self.assertFalse(result['disjoint_identity_certified'])

    def test_unknown_actions_do_not_make_approval_facts(self):
        import json
        raw=json.loads(self.files['daily.json']);raw['chart']['result'][0]['events']={'splits':{'x':{'date':1}}}
        self.files['daily.json']=canonical(raw)
        receipt=json.loads(self.files['receipt.json']);receipt['raw_sha256']=hashed(self.files['daily.json'])
        self.files['receipt.json']=canonical(receipt)
        result=self.run_builder()['locks']['S']
        self.assertEqual(result['reason'],'WAIT_REFERENCE_APPROVED_ACTION_FACTS_REQUIRED')

    def test_missing_interval_stays_wait(self):
        self.state['locks']['S']['exit_session']='2026-09-01'
        self.boundary['decision_evidence']=canonical(dict(account_id='a',session_date='2026-09-01'))
        self.assertEqual(self.run_builder()['locks']['S']['status'],'WAIT_REFERENCE_CONFIGURATION')

    def test_archive_tamper_rejected(self):
        self.run_builder()
        path=next((self.root/'archive').glob('*/sources/*.bin'))
        path.write_bytes(b'tampered')
        with self.assertRaises(ValueError):self.run_builder()


if __name__=='__main__':unittest.main()
