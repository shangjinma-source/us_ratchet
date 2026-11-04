from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import json
import unittest
from core.strategy_account_ledger import canonical
from core.strategy_account_split_v1 import apply_event
import test_strategy_account_target_inputs as fixture

spec=importlib.util.spec_from_file_location('split_target_candidate',
    Path(__file__).resolve().parents[1]/'docs/candidates/strategy_account_split_target_inputs.py')
candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)


class SplitTargetInputsTests(unittest.TestCase):
    def case(self, folder):
        args=fixture.setup(folder)
        before=fixture.build_target_inputs(**args)
        action=dict(event_id='split',kind='SPLIT_CONFIRMED',action_id='action',security_id='A',ratio=8,
            effective_at='2026-11-02T14:30:00+00:00',broker_confirmed_at='2026-11-02T14:31:00+00:00',
            old_unit_id='old',new_unit_id='new',evidence_sha256='a'*64)
        state,_=apply_event(args['state'],action,expected_revision=args['state']['revision'])
        state,_=apply_event(state,dict(event_id='cash-after',kind='CASH_CONFIRM',amount='80',
            cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=state['revision'])
        args['state']=state;package=args['source_package']
        marks=json.loads(package['files'][args['marks_path']]);marks['A'].update(price='5/2',unit_id='new')
        package['files'][args['marks_path']]=canonical(marks)
        package['source_hashes'][args['marks_path']]=sha256(canonical(marks)).hexdigest()
        review=json.loads(package['files'][args['unit_review_path']])
        review.update(account_revision=state['revision'],marks_sha256=package['source_hashes'][args['marks_path']])
        review['securities']['A'].update(current_mark_sha256=sha256(canonical(marks['A'])).hexdigest(),
            current_unit_id='new',recorded_action_sha256=sha256(canonical(action)).hexdigest())
        self.review(args,review)
        return args,before

    def review(self,args,value):
        package=args['source_package'];path=args['unit_review_path']
        package['files'][path]=canonical(value);package['source_hashes'][path]=sha256(canonical(value)).hexdigest()

    def test_split_held_capital_preserves_equity_pending_cash_and_training(self):
        with TemporaryDirectory() as folder:
            args,before=self.case(folder);saved=deepcopy(args)
            result=candidate.build_target_inputs(**args)
            binding=result['binding'];original=before['binding']
            self.assertEqual(binding['strategy_shares']['A'],16)
            for key in ('strategy_equity','total_uninvested_cash','holding_market_values','search_arguments'):
                self.assertEqual(binding[key],original[key])
            self.assertEqual(binding['execution_context']['reserved_cash'],'20')
            self.assertEqual(binding['execution_context']['available_cash'],'80')
            self.assertTrue(result['execution_blocked']);self.assertEqual(result['core_calls'],0)
            self.assertEqual(args,saved)

    def test_rehashed_review_cannot_claim_wrong_recorded_action_or_unit(self):
        for field,value in [('recorded_action_sha256','b'*64),('current_unit_id','old')]:
            with self.subTest(field=field),TemporaryDirectory() as folder:
                args,_=self.case(folder)
                review=json.loads(args['source_package']['files'][args['unit_review_path']])
                review['securities']['A'][field]=value;self.review(args,review)
                with self.assertRaisesRegex(ValueError,'SPLIT_TARGET_CURRENT_UNIT_NOT_BOUND'):
                    candidate.build_target_inputs(**args)
