from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import test_strategy_account_unit_review as fixture
from core.strategy_account_ledger import canonical
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data.strategy_recorded_split_review_v1 import review_recorded_splits as old
from docs.candidates.split_three_clock_review_20261105 import review_recorded_splits as new


class TimingTests(unittest.TestCase):
    def case(self,folder):
        quote='2026-10-16T13:30:00+00:00';epoch=int(datetime.fromisoformat(quote).timestamp())
        args=fixture.fixture(events={'splits':{str(epoch):dict(date=epoch,numerator=8,denominator=1,splitRatio='8:1')}},held=True)
        store=SplitStrategyAccountStore(Path(folder)/'account.sqlite',clock=lambda:fixture.NOW)
        state=store.initialize(args['state']['account_id'],operation_id='init')
        for row in args['state']['events']:
            store.append(row['payload'],expected_revision=state['revision']);state=store.read()
        action=dict(event_id='split',kind='SPLIT_CONFIRMED',action_id='action',security_id='S',ratio=8,
                    effective_at='2026-10-15T21:00:00+00:00',broker_confirmed_at='2026-10-16T13:31:00+00:00',
                    old_unit_id='old',new_unit_id='new',evidence_sha256='a'*64)
        store.append(action,expected_revision=state['revision']);args['state']=store.read()
        proof=dict(schema='SPLIT_THREE_CLOCK_CONTENT_V1',action_id='action',recorded_action_sha256=sha256(canonical(action)).hexdigest(),
                   distribution_at=action['effective_at'],quote_unit_effective_at=quote,broker_tradable_at=quote,
                   source_references=[next(iter(args['action_package']['source_hashes']))])
        return {k:args[k] for k in ('state','securities','action_package','now')},proof,store

    def test_persisted_prior_evening_distribution_next_day_quote(self):
        with TemporaryDirectory() as folder:
            args,proof,store=self.case(folder);before=store.read()
            with self.assertRaisesRegex(ValueError,'UNMATCHED_ACTION'):old(**args)
            result=new(**args,timing_reviews=[proof])
            self.assertEqual(len(result['matches']),1)
            self.assertEqual(store.read(),before)
            self.assertEqual(before['shares']['S'],16)
            for key in ('source_authenticated','broker_evidence_authenticated','executable','account_mutated'):
                self.assertFalse(result[key])

    def test_missing_future_and_unbound_timing_rejected(self):
        with TemporaryDirectory() as folder:
            args,proof,_=self.case(folder)
            with self.assertRaisesRegex(ValueError,'UNMATCHED_ACTION'):new(**args)
            for bad in (dict(proof,recorded_action_sha256='b'*64),dict(proof,quote_unit_effective_at='2026-10-17T13:30:00Z'),dict(proof,source_references=[])):
                with self.assertRaises(ValueError):new(**args,timing_reviews=[bad])
            changed=deepcopy(proof);changed['distribution_at']='2026-10-15T20:00:00Z'
            with self.assertRaisesRegex(ValueError,'EFFECTIVE_NOT_DISTRIBUTION'):new(**args,timing_reviews=[changed])


if __name__=='__main__':unittest.main()
