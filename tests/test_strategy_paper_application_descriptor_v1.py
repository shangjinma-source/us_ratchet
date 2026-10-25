from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_paper_application_descriptor_v1 import (
    SCOPE,SCHEMA,LEDGER_SCHEMA,plan_future_start,classify_window,validate_descriptor)


class DescriptorTests(unittest.TestCase):
    def setUp(self):
        self.calendar=canonical(dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[
            dict(date='2026-10-30',open='2026-10-30T13:30:00+00:00',close='2026-10-30T20:00:00+00:00'),
            dict(date='2026-11-02',open='2026-11-02T14:30:00+00:00',close='2026-11-02T21:00:00+00:00'),
            dict(date='2026-11-27',open='2026-11-27T14:30:00+00:00',close='2026-11-27T18:00:00+00:00')]))
        self.ch=sha256(self.calendar).hexdigest()
        self.plan=plan_future_start(calendar_bytes=self.calendar,calendar_sha256=self.ch,
            now='2026-10-30T13:58:00+00:00',terminal_date='2026-11-27')
        path='data/strategy_paper_application_descriptor_v1.py'
        self.codes={path:(Path(__file__).resolve().parents[1]/path).read_bytes()}
        self.sources={'fixture/conditional-review.json':canonical(dict(fixture_only=True))}
        root='data/current_strategy_paper/independent-20000'
        self.app=dict(schema=SCHEMA,scope=SCOPE,account_id='paper-current:independent-20000',
            simulation_id='paper-study:independent-20000',
            genesis=dict(currency='USD',cash='20000',shares={},orders={},external_cash_events_allowed=False),
            ledger_schema=LEDGER_SCHEMA,activation=False,calendar_sha256=self.ch,plan=self.plan,
            storage=dict(ledger=root+'/book.sqlite3',targets=root+'/targets.sqlite3',caps=root+'/caps.sqlite3',
                         evidence=root+'/evidence',registration=root+'/registration.json'),
            code_sha256={k:sha256(v).hexdigest() for k,v in self.codes.items()},
            source_sha256={k:sha256(v).hexdigest() for k,v in self.sources.items()},
            source_admission=dict(scope='PAPER_CURRENT_STRATEGY_SOURCE_REVIEW_V1',source_authenticated=False,
                                  coverage_complete=False,missing_evidence='WAIT_NO_ORDERS'),
            policy=dict(selector_profile=PROFILE_ID,continuous_iterations=32,
                daily_rule='SMA20_STRICT_ABOVE_FULL_ELSE_FLOOR_MONTHLY_HALF',
                entry_rule='CURRENT_HALT_AWARE_PULLBACK_AND_SELL_V1',fill_model='STRICT_CROSS_FULL_FILL_AT_LIMIT',
                fee_bps='1',unfilled_sale_proceeds_available=False,
                terminal_settlement='AT_OR_AFTER_FINAL_CLOSE_NO_NEW_ORDERS_RECOVERY_REMAINS_AVAILABLE'))

    def validate(self,now='2026-10-30T13:59:00+00:00',scope=SCOPE):
        raw=canonical(self.app);digest=sha256(raw).hexdigest()
        approval=canonical(dict(schema='PAPER_APPLICATION_REVIEW_V1',scope=scope,descriptor_sha256=digest,
            approved=True,reviewed_at='2026-10-30T13:58:30+00:00',
            review_role='IMPLEMENTATION_REVIEW_OF_USER_AUTHORIZED_PAPER_SCOPE',
            authorization_basis='ISOLATED TEST REVIEW; not production authorization'))
        return validate_descriptor(descriptor_bytes=raw,trusted_descriptor_sha256=digest,
            approval_bytes=approval,trusted_approval_sha256=sha256(approval).hexdigest(),
            calendar_bytes=self.calendar,code_bytes=self.codes,source_bytes=self.sources,now=now)

    def test_reviewed_candidate_never_initializes_or_accepts(self):
        result=self.validate()
        self.assertTrue(result['future_start_still_available'])
        self.assertFalse(result['registration_allowed'])
        for field in ('orders_allowed','book_creation_allowed','real_account_writes','task_activation_allowed'):
            self.assertFalse(result[field])
        self.assertEqual(result['phase']['status'],'WAIT_REGISTERED_START')

    def test_exact_window_missed_start_and_no_backfill(self):
        self.assertEqual(self.validate('2026-10-30T14:00:00+00:00')['phase']['status'],'FIRST_DECISION_WINDOW')
        self.assertFalse(self.validate('2026-10-30T14:00:00+00:00')['registration_allowed'])
        missed=self.validate('2026-11-02T15:00:00+00:00')
        self.assertEqual(missed['phase']['status'],'MISSED_REGISTERED_START')
        self.assertFalse(missed['future_start_still_available'])
        next_plan=plan_future_start(calendar_bytes=self.calendar,calendar_sha256=self.ch,
            now='2026-10-30T14:00:00+00:00',terminal_date='2026-11-27')
        self.assertEqual(next_plan['first_session']['decision_at'],'2026-11-02T15:00:00+00:00')

    def test_half_day_terminal_recovery_still_reachable(self):
        for now in ('2026-11-27T18:00:00+00:00','2026-11-30T22:00:00+00:00'):
            result=classify_window(plan=self.plan,calendar_bytes=self.calendar,now=now,initialized=True)
            self.assertEqual(result['status'],'TERMINAL_SETTLEMENT_ONLY');self.assertFalse(result['orders_allowed'])
        self.assertEqual(classify_window(plan=self.plan,calendar_bytes=self.calendar,
            now='2026-11-02T15:01:00+00:00',initialized=True)['status'],'NO_NEW_DECISION')

    def test_web_fixture_selection_authority_and_real_storage_rejected(self):
        for scope in ('WEB_MANUAL_ADVICE_RULE_ONLY','ISOLATED_CURRENT_STRATEGY_PAPER_FIXTURE_ONLY',
                      'ISOLATED_CURRENT_STRATEGY_PAPER_SELECTION_ONLY'):
            with self.assertRaisesRegex(ValueError,'INDEPENDENT_APPROVAL'):self.validate(scope=scope)
        self.app['storage']['caps']='data/strategy_account/caps.sqlite3'
        with self.assertRaisesRegex(ValueError,'STORAGE_NAMESPACE'):self.validate()
        self.setUp();self.app['ledger_schema']='CURRENT_STRATEGY_PAPER_FIXTURE_BOOK_V1'
        with self.assertRaisesRegex(ValueError,'PROSPECTIVE_SCOPE'):self.validate()

    def test_binding_tamper_and_clock_rollback(self):
        self.sources['fixture/conditional-review.json']=b'{}'
        with self.assertRaisesRegex(ValueError,'CLOSURE_CHANGED'):self.validate()
        self.setUp();self.app['plan']['first_session']['decision_at']='2026-10-30T14:00:30+00:00'
        with self.assertRaisesRegex(ValueError,'PLAN_BINDING'):self.validate()
        self.setUp()
        with self.assertRaisesRegex(ValueError,'CLOCK_ROLLBACK'):
            classify_window(plan=self.plan,calendar_bytes=self.calendar,now='2026-10-30T13:57:00+00:00')

    def test_rehashed_fake_executing_code_and_changed_genesis_rejected(self):
        name=next(iter(self.codes));self.codes[name]=b'fake implementation'
        self.app['code_sha256'][name]=sha256(self.codes[name]).hexdigest()
        with self.assertRaisesRegex(ValueError,'EXECUTING_CODE_CHANGED'):self.validate()
        self.setUp();self.app['genesis']['cash']='25000'
        with self.assertRaisesRegex(ValueError,'ZERO_HISTORY_GENESIS'):self.validate()


if __name__=='__main__':unittest.main()
