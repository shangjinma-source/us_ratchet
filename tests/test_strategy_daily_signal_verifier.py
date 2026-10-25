import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256

from core.strategy_account_ledger import create_account
from data.strategy_daily_signal_verifier import verify_daily_signal_bundle, ROOT, CODE_PATHS, POLICY
from test_current_quantity_v2_risk_overlays import fixture


def raw(value):
    return json.dumps(value, sort_keys=True).encode()


class SignalVerifierTests(unittest.TestCase):
    def setUp(self):
        self.inputs = fixture({'A': [100] * 20}, quantities={'A': 21})
        self.inputs['observed_at']=self.inputs['signal_date']+'T16:00:00-05:00'
        day = datetime.fromisoformat(self.inputs['signal_date']) + timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        date = day.date().isoformat()
        self.start = date+'T09:30:00-05:00'
        self.end = date+'T16:00:00-05:00'
        self.calendar = dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',
            sessions=[dict(date=d,open=d+'T09:30:00-05:00',close=d+'T16:00:00-05:00')
                      for d in self.inputs['session_dates']]+[dict(date=date,open=self.start,close=self.end)])
        self.calendar_bytes = raw(self.calendar)
        self.state = create_account('fixture-only')
        self.target = dict(target_id='fixture-target', payload=dict(
            account_id='fixture-only', target_month=date[:7], target_quantities={'A': 21}))
        self.release = dict(schema='SERVER_DAILY_POLICY_RELEASE_V1', approved=True,
            policy_id=POLICY, approved_at='2026-01-01T00:00:00+00:00',
            calendar_sha256=sha256(self.calendar_bytes).hexdigest(),
            fixture_only=True, code_sha256={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in CODE_PATHS})
        self.files = {'normalized.json':raw(self.inputs), 'raw-history.json':raw({'fixture':'not market evidence'})}
        self.receipt = dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',
            release_sha256=sha256(raw(self.release)).hexdigest(), account_id=self.state['account_id'],
            account_revision=self.state['revision'], target_id=self.target['target_id'],
            normalized_inputs_path='normalized.json', normalization_reviewed=True,
            unresolved_units=[], pending_rights=[], raw_source_paths=['raw-history.json'],
            available_at=self.inputs['observed_at'], valid_from=self.start, valid_until=self.end,
            market_asof=self.inputs['observed_at'],source_received_at=self.inputs['observed_at'],
            research_observed_at_semantics='MARKET_ASOF_NOT_RECEIPT',
            execution_session=dict(date=date, open=self.start, close=self.end))

    def args(self):
        self.receipt['source_sha256'] = {p:sha256(b).hexdigest() for p,b in self.files.items()}
        return dict(state=self.state, target=self.target, now=self.start,
            release_bytes=raw(self.release), trusted_release_sha256=sha256(raw(self.release)).hexdigest(),
            receipt_bytes=raw(self.receipt), trusted_receipt_sha256=sha256(raw(self.receipt)).hexdigest(),
            files=deepcopy(self.files),calendar_bytes=self.calendar_bytes)

    def test_no_release_never_enables_half(self):
        result=verify_daily_signal_bundle(state=self.state,target=self.target,now=self.start)
        self.assertEqual(result, dict(status='WAIT_POLICY_RELEASE',signal=None))

    def test_explicit_test_release_computes_from_reviewed_inputs(self):
        result=verify_daily_signal_bundle(**self.args())
        self.assertEqual(result['signal']['effective_target_quantities'], {'A':10})
        self.assertFalse(result['production_enabled'])

    def test_source_release_and_receipt_tampering_rejected(self):
        for key in ('release_bytes','receipt_bytes'):
            args=self.args();args[key]+=b' '
            with self.assertRaises(ValueError):verify_daily_signal_bundle(**args)
        args=self.args();args['files']['raw-history.json']+=b' '
        with self.assertRaises(ValueError):verify_daily_signal_bundle(**args)

    def test_review_cannot_override_future_unknown_units_or_monthly_quantity(self):
        for field in ('future','units','quantity'):
            inputs=deepcopy(self.inputs)
            if field=='future':inputs['histories']['A']['closes'][-1]['completed_at']='2099-01-01T16:00:00-05:00'
            if field=='units':inputs['histories']['A']['units']['basis_id']='unknown'
            if field=='quantity':inputs['base_target']['quantities']['A']=22
            self.files['normalized.json']=raw(inputs)
            with self.assertRaises(ValueError):verify_daily_signal_bundle(**self.args())

    def test_account_binding_and_stale_validity(self):
        args=self.args();args['state']=create_account('other')
        with self.assertRaises(ValueError):verify_daily_signal_bundle(**args)
        args=self.args();args['now']=self.end
        self.assertEqual(verify_daily_signal_bundle(**args)['status'],'WAIT_FRESH_SIGNAL')

    def test_omitted_recent_session_rejected_even_with_resealed_receipt(self):
        inputs=deepcopy(self.inputs)
        removed=inputs['session_dates'].pop(-2)
        del inputs['session_close_times']['closes'][removed]
        inputs['histories']['A']['closes']=[r for r in inputs['histories']['A']['closes'] if r['date']!=removed]
        self.files['normalized.json']=raw(inputs)
        with self.assertRaisesRegex(ValueError,'FIXED_CALENDAR_PREFIX_REQUIRED'):
            verify_daily_signal_bundle(**self.args())

    def test_skipping_next_session_or_faking_holiday_rejected(self):
        nextday=(datetime.fromisoformat(self.start)+timedelta(days=1)).date().isoformat()
        self.receipt['valid_from']=nextday+'T09:30:00-05:00'
        self.receipt['valid_until']=nextday+'T16:00:00-05:00'
        self.receipt['execution_session']=dict(date=nextday,open=self.receipt['valid_from'],close=self.receipt['valid_until'])
        args=self.args();args['now']=self.receipt['valid_from']
        with self.assertRaisesRegex(ValueError,'NEXT_FIXED_SESSION_REQUIRED'):
            verify_daily_signal_bundle(**args)
        forged=deepcopy(self.calendar);forged['sessions'].pop(-2)
        args=self.args();args['calendar_bytes']=raw(forged)
        with self.assertRaisesRegex(ValueError,'FIXED_CALENDAR_HASH_MISMATCH'):
            verify_daily_signal_bundle(**args)

    def test_false_close_time_in_reviewed_input_rejected(self):
        inputs=deepcopy(self.inputs)
        inputs['session_close_times']['closes'][inputs['signal_date']]=inputs['signal_date']+'T13:00:00-05:00'
        self.files['normalized.json']=raw(inputs)
        with self.assertRaisesRegex(ValueError,'FIXED_CALENDAR_CLOSES_REQUIRED'):
            verify_daily_signal_bundle(**self.args())

    def test_next_day_receipt_is_not_backdated_to_market_asof(self):
        self.receipt['source_received_at']=self.start[:10]+'T08:00:00-05:00'
        self.receipt['available_at']=self.start[:10]+'T08:01:00-05:00'
        result=verify_daily_signal_bundle(**self.args())
        self.assertEqual(result['signal']['observed_at'],self.receipt['source_received_at'])
        self.assertNotEqual(result['signal']['observed_at'],result['market_asof'])
        self.receipt['source_received_at']='2025-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):verify_daily_signal_bundle(**self.args())

    def test_intraday_available_starts_then_not_at_open(self):
        self.receipt['source_received_at']=self.start[:10]+'T10:00:00-05:00'
        self.receipt['available_at']=self.start[:10]+'T10:01:00-05:00'
        self.receipt['valid_from']=self.receipt['available_at']
        args=self.args();args['now']=self.receipt['available_at']
        self.assertEqual(verify_daily_signal_bundle(**args)['status'],'DAILY_SIGNAL_READY')
        args['now']=self.start
        self.assertEqual(verify_daily_signal_bundle(**args)['status'],'WAIT_FRESH_SIGNAL')
        self.receipt['available_at']=self.start[:10]+'T17:00:00-05:00'
        self.receipt['valid_from']=self.receipt['available_at']
        with self.assertRaises(ValueError):verify_daily_signal_bundle(**self.args())


if __name__ == '__main__':
    unittest.main()
