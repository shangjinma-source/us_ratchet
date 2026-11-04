from copy import deepcopy
from hashlib import sha256
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import json
import unittest
from core.strategy_account_ledger import canonical
from core.strategy_account_split_v1 import apply_event
import test_strategy_account_target_inputs as fixture
from backtest.return_priority_fresh_cash_quantity_search_v2 import search_fresh_cash_quantities

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

    def test_candidate_pool_split_runs_real_search_without_manufactured_returns(self):
        with TemporaryDirectory() as folder:
            args=fixture.setup(folder)
            state=args['state']
            for event in (
                dict(event_id='cancel-before-split',kind='CANCEL',order_id='buy'),
                dict(event_id='confirm-before-split',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'),
            ):
                state,_=apply_event(state,event,expected_revision=state['revision'])
            args['state']=state
            package=args['source_package']
            review=json.loads(package['files'][args['unit_review_path']])
            review['account_revision']=state['revision'];self.review(args,review)
            before=candidate.build_target_inputs(**args)['binding']
            action=dict(event_id='pool-split',kind='SPLIT_CONFIRMED',action_id='pool-action',security_id='B',ratio=8,
                effective_at='2026-11-02T14:30:00+00:00',broker_confirmed_at='2026-11-02T14:31:00+00:00',
                old_unit_id='old',new_unit_id='new',evidence_sha256='a'*64)
            for event in (action,dict(event_id='confirm-pool-split',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED')):
                state,_=apply_event(state,event,expected_revision=state['revision'])
            args['state']=state
            marks=json.loads(package['files'][args['marks_path']]);marks['B'].update(price='5/4',unit_id='new')
            package['files'][args['marks_path']]=canonical(marks)
            package['source_hashes'][args['marks_path']]=sha256(canonical(marks)).hexdigest()
            review.update(account_revision=state['revision'],marks_sha256=package['source_hashes'][args['marks_path']])
            review['securities']['B'].update(current_mark_sha256=sha256(canonical(marks['B'])).hexdigest(),
                current_unit_id='new',recorded_action_sha256=sha256(canonical(action)).hexdigest())
            self.review(args,review)
            saved=deepcopy(args)
            after=candidate.build_target_inputs(**args)['binding']
            self.assertEqual(before['strategy_equity'],after['strategy_equity'])
            for key in ('training_scenarios','scenario_dates','entered_cash','metadata'):
                self.assertEqual(before['search_arguments'][key],after['search_arguments'][key])
            old=search_fresh_cash_quantities(**before['search_arguments'])['selected']
            new=search_fresh_cash_quantities(**after['search_arguments'])['selected']
            # The old allocation remains feasible on the finer integer grid.
            # Any extra invested dollars must fit within one old share, not an 8x windfall.
            self.assertGreaterEqual(new['training_mean_net_log_wealth']+1e-12,old['training_mean_net_log_wealth'])
            self.assertLess(abs(Fraction(new['notional'])-Fraction(old['notional'])),10)
            for result in (old,new):
                self.assertEqual(sum(Fraction(result[key]) for key in ('notional','fees','residual_cash')),
                    Fraction(before['strategy_equity']))
            self.assertEqual(Fraction(new['notional']),Fraction(5,4)*new['quantities'].get('B',0))
            self.assertEqual(args,saved)
