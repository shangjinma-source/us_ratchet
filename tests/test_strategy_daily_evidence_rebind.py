from copy import deepcopy
from datetime import datetime,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_daily_evidence_rebind import rebind_reviewed_daily_evidence, SameSessionDailyEvidenceProducer
import test_strategy_daily_signal_verifier as fixtures


class RebindTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.SignalVerifierTests();fixture.setUp()
        args=fixture.args()
        self.clock=datetime.fromisoformat(args['now'])
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.accounts=StrategyAccountStore(Path(self.temp.name)/'account.sqlite3',clock=lambda:self.clock)
        self.accounts.initialize('fixture-only',operation_id='init')
        self.targets=StrategyMonthlyTargetStore(Path(self.temp.name)/'target.sqlite3')
        self.counter=0
        self.date=fixture.inputs['signal_date']
        self.target=self.publish({'A':21})
        self.receipt=deepcopy(fixture.receipt)
        self.receipt.update(target_id=self.target['target_id'],
            account_revision=self.accounts.read()['revision'],release_sha256=None,
            source_authenticated=False,coverage_complete=False)
        self.files=args['files']
        self.parent_bytes=canonical(self.receipt)
        self.parent_sha=sha256(self.parent_bytes).hexdigest()

    def publish(self,quantities):
        previous=self.targets.current()
        self.counter+=1
        decision_payload=dict(target_quantities=quantities,input_binding=dict(
            training_cutoff_date=self.date,historical_search_arguments=dict(decision_date=self.date),
            search_arguments=dict(decision_date=self.clock.date().isoformat()),
            valuation_at=self.clock.isoformat(),valuation_date=self.clock.date().isoformat()))
        decision_payload['input_id']=sha256(canonical(decision_payload['input_binding'])).hexdigest()
        decision=dict(payload=decision_payload,decision_id=sha256(canonical(decision_payload)).hexdigest())
        return self.targets.append(dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',
            account_id='fixture-only',target_month=self.clock.strftime('%Y-%m'),
            created_at=self.clock.isoformat(),
            previous_target_id=previous['target_id'] if previous else None,
            request=dict(event_id=str(self.counter)),decision=decision,target_quantities=quantities))

    def event(self,kind,**fields):
        self.counter+=1
        self.accounts.append(dict(event_id=str(self.counter),kind=kind,**fields),
                             expected_revision=self.accounts.read()['revision'])

    def run_rebind(self,**overrides):
        args=dict(receipt_bytes=self.parent_bytes,trusted_receipt_sha256=self.parent_sha,
            files=self.files,state=self.accounts.read(),target=self.targets.current(),
            now=self.clock.isoformat())
        args.update(overrides)
        return rebind_reviewed_daily_evidence(**args)

    def test_cash_and_fill_revision_rebind_preserves_history_and_receipt_time(self):
        self.event('CASH_CONFIRM',amount='2000',cash_basis='TOTAL_UNINVESTED')
        first=self.run_rebind()
        self.event('DIRECT_FILL',security_id='A',side='BUY',quantity=3,
                   price='100',fees='0',executed_at=self.clock.isoformat())
        self.event('CASH_CONFIRM',amount='1700',cash_basis='TOTAL_UNINVESTED')
        before=self.accounts.path.read_bytes()
        second=self.run_rebind()
        self.assertNotEqual(first['receipt']['account_revision'],second['receipt']['account_revision'])
        self.assertEqual(second['source_received_at'],self.receipt['source_received_at'])
        self.assertEqual(first['files'],second['files'])
        self.assertIsNone(second['release_sha256'])
        self.assertEqual(self.accounts.path.read_bytes(),before)

    def test_new_same_security_target_rebinds_quantity_not_price(self):
        self.publish({'A':10})
        result=self.run_rebind()
        import json
        normalized=json.loads(result['files'][result['receipt']['normalized_inputs_path']])
        original=json.loads(self.files[self.receipt['normalized_inputs_path']])
        self.assertEqual(normalized['base_target']['quantities'],{'A':10})
        self.assertEqual(normalized['histories'],original['histories'])
        self.assertEqual(result['receipt']['parent_review_sha256'],self.parent_sha)

    def test_expired_or_new_security_requires_evidence(self):
        expired=self.run_rebind(now=(self.clock+timedelta(days=1)).isoformat())
        self.assertEqual(expired['status'],'WAIT_NEW_SESSION_EVIDENCE')
        self.publish({'B':10})
        self.assertEqual(self.run_rebind()['status'],'WAIT_NEW_SECURITY_EVIDENCE')

    def test_parent_bytes_or_source_tampering_rejected(self):
        with self.assertRaises(ValueError):self.run_rebind(receipt_bytes=self.parent_bytes+b' ')
        files=deepcopy(self.files);files['normalized.json']=b'{}'
        with self.assertRaises(ValueError):self.run_rebind(files=files)

    def test_saved_server_producer_roundtrip_without_ledger_write(self):
        root=Path(self.temp.name)
        (root/'parent.json').write_bytes(self.parent_bytes)
        for name,raw in self.files.items():(root/name).write_bytes(raw)
        producer=SameSessionDailyEvidenceProducer(root=root,parent_receipt_path='parent.json',
            trusted_parent_sha256=self.parent_sha,source_paths={p:p for p in self.files})
        before=self.accounts.path.read_bytes()
        result=producer.prepare(self.accounts.read(),self.targets.current(),self.clock)
        self.assertEqual(result['status'],'REBOUND_EVIDENCE_READY_POLICY_UNCHANGED')
        self.assertEqual(self.accounts.path.read_bytes(),before)

    def test_rehashed_outer_target_cannot_hide_modified_input_binding(self):
        target=deepcopy(self.targets.current())
        decision=target['payload']['decision']
        decision['payload']['input_binding']['extra']='tampered'
        decision['decision_id']=sha256(canonical(decision['payload'])).hexdigest()
        target['target_id']=sha256(canonical(target['payload'])).hexdigest()
        with self.assertRaisesRegex(ValueError,'REBIND_TARGET_INPUT_MISMATCH'):
            self.run_rebind(target=target)

    def test_new_parent_and_normalized_files_count_against_final_budget(self):
        files=deepcopy(self.files)
        for index in range(2000-len(files)):
            files['padding/'+str(index)]=b'x'
        receipt=deepcopy(self.receipt)
        receipt['source_sha256']={p:sha256(raw).hexdigest() for p,raw in files.items()}
        encoded=canonical(receipt)
        with self.assertRaisesRegex(ValueError,'REBOUND_SOURCE_DOMAIN_OR_BUDGET'):
            self.run_rebind(files=files,receipt_bytes=encoded,
                            trusted_receipt_sha256=sha256(encoded).hexdigest())

    def test_parent_receipt_counts_against_final_byte_budget(self):
        files=deepcopy(self.files)
        files['padding']=b'x'*(32*1024*1024-sum(map(len,files.values())))
        receipt=deepcopy(self.receipt)
        receipt['source_sha256']={p:sha256(raw).hexdigest() for p,raw in files.items()}
        encoded=canonical(receipt)
        with self.assertRaisesRegex(ValueError,'REBOUND_SOURCE_DOMAIN_OR_BUDGET'):
            self.run_rebind(files=files,receipt_bytes=encoded,
                            trusted_receipt_sha256=sha256(encoded).hexdigest())


if __name__=='__main__':
    unittest.main()
