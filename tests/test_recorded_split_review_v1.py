from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import unittest
from core.strategy_account_ledger import canonical
from core.strategy_account_split_v1 import apply_event
from data.strategy_recorded_split_review_v1 import review_recorded_splits
from test_strategy_account_unit_review import fixture, NOW


class RecordedSplitTests(unittest.TestCase):
    def case(self):
        timestamp = int(datetime.fromisoformat('2026-10-16T13:30:00+00:00').timestamp())
        args = fixture(events={'splits': {str(timestamp): dict(date=timestamp, numerator=8,
                       denominator=1, splitRatio='8:1')}}, held=True)
        state = args['state']
        action = dict(event_id='split', kind='SPLIT_CONFIRMED', action_id='action',
            security_id='S', ratio=8, effective_at='2026-10-16T13:30:00Z',
            broker_confirmed_at='2026-10-16T13:31:00Z', old_unit_id='old',
            new_unit_id='new', evidence_sha256='a'*64)
        state, _ = apply_event(state, action, expected_revision=state['revision'])
        return dict(state=state, securities=args['securities'], action_package=args['action_package'], now=NOW.isoformat())

    def change_source(self, args, change):
        package=args['action_package'];receipt_path=package['documents']['action_receipts']['S']
        receipt=json.loads(package['files'][receipt_path]);raw_path=receipt['raw_path']
        chart=json.loads(package['files'][raw_path]);change(chart['chart']['result'][0])
        raw=canonical(chart);receipt['raw_sha256']=sha256(raw).hexdigest()
        package['files'][raw_path]=raw;package['files'][receipt_path]=canonical(receipt)
        for path in (raw_path,receipt_path):package['source_hashes'][path]=sha256(package['files'][path]).hexdigest()

    def test_matching_capture_does_not_claim_source_or_broker_authority(self):
        args=self.case();before=deepcopy(args)
        result=review_recorded_splits(**args)
        self.assertEqual(len(result['matches']),1)
        for flag in ('source_authenticated','broker_evidence_authenticated','coverage_complete','executable'):
            self.assertFalse(result[flag])
        self.assertEqual(args,before)

    def test_wrong_ratio_missing_event_and_wrong_security_rejected_even_rehashed(self):
        for mutation,reason in [
            (lambda e: next(iter(e['events']['splits'].values())).update(numerator=4,splitRatio='4:1'),'UNMATCHED_ACTION'),
            (lambda e: e.update(events={}), 'RECORDED_ACTION_MISSING'),
            (lambda e: e['meta'].update(symbol='OTHER'), 'IDENTITY'),
            (lambda e: e['events'].update(dividends={'x':{'amount':1}}),'OTHER_RIGHTS')]:
            args=self.case();self.change_source(args,mutation)
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):review_recorded_splits(**args)

    def test_different_day_and_raw_tampering_rejected(self):
        args=self.case()
        def move(entry):
            event=next(iter(entry['events']['splits'].values()));event['date']-=86400
            entry['events']['splits']={str(event['date']):event}
        self.change_source(args,move)
        with self.assertRaisesRegex(ValueError,'UNMATCHED_ACTION'):review_recorded_splits(**args)
        args=self.case();package=args['action_package'];path=next(iter(package['files']))
        package['files'][path]+=b' '
        with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):review_recorded_splits(**args)

    def test_unrecorded_provider_split_rejected(self):
        args=self.case();args['state']=fixture(held=True)['state']
        with self.assertRaisesRegex(ValueError,'UNMATCHED_ACTION'):review_recorded_splits(**args)
