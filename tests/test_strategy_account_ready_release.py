from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import unittest
from core.strategy_account_ledger import canonical
from scripts.review_prepare_real_monthly_release import run
from data.strategy_account_ready_release import validate_ready_release
import test_review_prepare_real_monthly_release as fixture


class ReadyReleaseTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ReviewPrepareTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root
        self.ready=run(**self.f.arguments)
        self.path='reviewed-package/ready.json'
        self.digest=sha256((self.root/self.path).read_bytes()).hexdigest()

    def validate(self,**changes):
        args=dict(root=self.root,receipt_path=self.path,receipt_sha256=self.digest,
            account_state=self.f.store.read(),clock=lambda:self.f.now)
        args.update(changes)
        return validate_ready_release(**args)

    def test_real_pipeline_readback_no_account_write_and_not_quote_expiry(self):
        before=self.f.store.path.read_bytes()
        result=self.validate(clock=lambda:self.f.now+timedelta(hours=3))
        self.assertEqual(result['configuration']['target_month'],'2026-12')
        self.assertEqual(before,self.f.store.path.read_bytes())
        self.assertFalse((self.root/'data/strategy_account/monthly_targets.sqlite3').exists())

    def test_wrong_hash_revision_future_and_month_refused(self):
        with self.assertRaisesRegex(ValueError,'READY_SOURCE_CHANGED'):
            self.validate(receipt_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'READY_CURRENT_MONTH_REQUIRED'):
            self.validate(clock=lambda:self.f.now+timedelta(days=32))
        with self.assertRaisesRegex(ValueError,'READY_REVIEW_TIME_INVALID'):
            self.validate(clock=lambda:self.f.now-timedelta(seconds=1))
        self.f.store.append(dict(event_id='cash',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'),
            expected_revision=self.f.store.read()['revision'])
        with self.assertRaisesRegex(ValueError,'READY_ACCOUNT_REVISION_CHANGED'):self.validate()

    def test_raw_action_tamper_refused(self):
        directory=(self.root/self.ready['files']['complete']['path']).parent
        path=next((directory/'actions').glob('*.raw'))
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'READY_SOURCE_CHANGED'):self.validate()

    def test_self_consistent_review_forgery_does_not_pass_replay(self):
        review_path=self.root/self.ready['files']['unit_review']['path']
        import json
        review=json.loads(review_path.read_bytes())
        review['historical_search_arguments_sha256']='0'*64
        review_raw=canonical(review);review_path.write_bytes(review_raw)
        complete_path=self.root/self.ready['files']['complete']['path']
        complete=json.loads(complete_path.read_bytes())
        complete['source_hashes'][complete['documents']['unit_review']]=sha256(review_raw).hexdigest()
        complete_path.write_bytes(canonical(complete))
        for label in ('unit_review','complete'):
            self.ready['files'][label]['sha256']=sha256((self.root/self.ready['files'][label]['path']).read_bytes()).hexdigest()
        (self.root/self.path).write_bytes(canonical(self.ready))
        self.digest=sha256((self.root/self.path).read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'READY_REVIEW_REPLAY_MISMATCH'):self.validate()


if __name__=='__main__':unittest.main()
