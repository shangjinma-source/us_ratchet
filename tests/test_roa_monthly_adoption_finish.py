import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.research.finish_roa_monthly_adoption import finish


class FinishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'adoption').mkdir()
        (self.root/'active.json').write_text('{}')
        self.digest = sha256(b'{}').hexdigest()
        receipt = dict(status='ACTIVE_POINTER_SWITCHED_RESTART_VALIDATION_REQUIRED',
                       expected_active={'path':'active.json'}, active_sha256=self.digest)
        (self.root/'adoption/adoption.json').write_text(json.dumps(receipt))
        (self.root/'adoption/validated.json').write_text(json.dumps(dict(status='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED', month='2026-12', next_active={'sha256':self.digest})))
        self.account = {'cash':'11742.25'}; self.ledger = {'fills':['six buys','sell all SNDK']}
        self.runtime = dict(healthy=True, active_sha256='old', month='2026-11',
                            epoch='epoch', process_identity={'pid':123,'started':'known'})
        self.restarts = 0
    def ready(self):
        self.runtime.update(active_sha256=self.digest, month='2026-12')
    def restart(self, **expected):
        self.assertEqual(expected['expected_process_identity'], self.runtime['process_identity'])
        self.restarts += 1; self.ready()
    def run_it(self, restart=None):
        return finish(root=self.root, adoption_directory='adoption', evidence_directory='evidence',
                      expected_month='2026-12', expected_epoch='epoch',
                      read_account=lambda:dict(self.account), read_ledger=lambda:dict(self.ledger),
                      inspect_runtime=lambda:dict(self.runtime), restart=restart or self.restart)
    def test_success_retry_does_not_restart(self):
        self.assertEqual(self.run_it()['status'],'MONTH_RUNTIME_VERIFIED')
        self.run_it(); self.assertEqual(self.restarts,1)
    def test_timeout_after_actual_restart_reconciles(self):
        def uncertain(**kw):
            self.restart(**kw); raise TimeoutError('lost acknowledgment')
        with self.assertRaises(TimeoutError): self.run_it(uncertain)
        self.run_it(); self.assertEqual(self.restarts,1)
    def test_uncertain_unhealthy_never_repeats(self):
        def failed(**kw):
            self.restarts += 1; raise TimeoutError()
        with self.assertRaises(TimeoutError): self.run_it(failed)
        with self.assertRaisesRegex(ValueError,'NO_REPEAT'): self.run_it()
        self.assertEqual(self.restarts,1)
    def test_changed_account_not_reported_success(self):
        def changed(**kw):
            self.restart(**kw); self.account['cash']='1'
        with self.assertRaisesRegex(ValueError,'ACCOUNT_OR_LEDGER'): self.run_it(changed)
        self.assertFalse((self.root/'evidence/success.json').exists())
    def test_later_active_not_overwritten(self):
        def changed(**kw):
            self.restart(**kw); (self.root/'active.json').write_text('later')
        with self.assertRaisesRegex(ValueError,'ACTIVE_CHANGED'): self.run_it(changed)
        self.assertEqual((self.root/'active.json').read_text(),'later')
    def test_wrong_epoch_is_not_success(self):
        def wrong(**kw):
            self.restart(**kw); self.runtime['epoch']='wrong'
        with self.assertRaisesRegex(ValueError,'NOT_VERIFIED'): self.run_it(wrong)
    def test_wrong_publication_month_blocks_restart(self):
        p=self.root/'adoption/validated.json'; doc=json.loads(p.read_text()); doc['month']='2027-01'; p.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError,'PUBLICATION_CONFLICT'): self.run_it()
        self.assertEqual(self.restarts,0)
    def test_already_loaded_no_restart(self):
        self.ready(); self.run_it(); self.assertEqual(self.restarts,0)

if __name__ == '__main__': unittest.main()
