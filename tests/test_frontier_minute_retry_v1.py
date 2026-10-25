"""Exercise one recapture through the real composition with controlled clock."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from data.saved_frontier_daily_composition_v1 import SavedFrontierDailyComposition
from data.strategy_recent_minute_retry_v1 import RecentClosedMinuteUnavailable


class RetryTests(unittest.TestCase):
    def run_case(self, *, expires=False, twice=False):
        with TemporaryDirectory() as folder:
            now = [datetime(2026,10,23,15,0,tzinfo=timezone.utc)]
            elapsed = [0]
            sleeps = []
            state = dict(account_id='a', revision='r', available_cash='10')
            target = dict(target_id='t', payload=dict(account_id='a', target_month='2026-10'))
            proposal = dict(proposal_id='p', payload=dict(fee_bps='1', proposed_target_quantities={'B':1}))
            signal = dict(proposal_id='p', policy_id='new', evidence_id='e', evidence_archive={'id':'e'},
                effective_target_quantities={'B':1,'OLD':0}, valid_from=now[0].isoformat(),
                valid_until=(now[0]+timedelta(seconds=1 if expires else 60)).isoformat())
            monthly = SimpleNamespace(snapshot_operation=nullcontext, validate_current_target_pins=lambda:None,
                accounts=SimpleNamespace(read=lambda:deepcopy(state)),current=lambda:deepcopy(target))
            class Provider:
                output = Path(folder)
                def execution(self):pass
            def sleep(seconds):
                sleeps.append(seconds);elapsed[0]+=seconds;now[0]+=timedelta(seconds=seconds)
            service = SavedFrontierDailyComposition(monthly_service=monthly,
                monthly_view=SimpleNamespace(require_proposal=lambda **kwargs:deepcopy(proposal)),
                evidence_reader=lambda *args,**kwargs:dict(status='DAILY_SIGNAL_READY',signal=deepcopy(signal),
                    evidence_archive=signal['evidence_archive']), execution_provider=Provider().execution,
                clock=lambda:now[0],policy_execution_enabled=True,policy_id='new',fee_bps='1',
                sleep=sleep,monotonic=lambda:elapsed[0])
            transient=RecentClosedMinuteUnavailable(dict(account_revision='r'))
            attempts=[transient,transient if twice else dict(status='CONDITIONAL_PREVIEW_READY',
                new_orders=[dict(security_id='B')],reference_quotes={})]
            bridges=[]
            def bridge(**kwargs):
                self.assertEqual(kwargs['base_target'],target)
                bridges.append(kwargs)
                return SimpleNamespace(last_binding={'base_target_id':'t'})
            with patch('data.saved_frontier_daily_composition_v1.DailyExecutionBridge',side_effect=bridge), \
                 patch('data.saved_frontier_daily_composition_v1.SavedFrontierPreviewService.preview',side_effect=attempts) as preview, \
                 patch('data.saved_frontier_daily_composition_v1.preview_buy_data_wait_mixed',
                       return_value=dict(status='WAIT_EXECUTION_ELIGIBILITY',new_orders=[])) as fallback:
                if expires:
                    with self.assertRaisesRegex(ValueError,'DAILY_SIGNAL_EXPIRED_BEFORE_RECAPTURE'):
                        service.preview(expected_revision='r',target_id='t',expected_proposal_id='p')
                    self.assertEqual(preview.call_count,1)
                    self.assertEqual(fallback.call_count,0)
                else:
                    result=service.preview(expected_revision='r',target_id='t',expected_proposal_id='p')
                    self.assertEqual(preview.call_count,2)
                    self.assertEqual(fallback.call_count,int(twice))
                    self.assertEqual(result['proposal_id'],'p')
                    self.assertEqual(result['policy_id'],'new')
                    self.assertEqual(result['minute_recapture']['attempt'],1)
                    if not twice:self.assertEqual(result['new_orders'][0]['proposal_id'],'p')
                self.assertEqual(sleeps,[2])

    def test_retry_succeeds_with_same_proposal(self):self.run_case()
    def test_expiry_during_wait_prevents_second_capture(self):self.run_case(expires=True)
    def test_second_typed_failure_does_not_retry_again(self):self.run_case(twice=True)

if __name__=='__main__':unittest.main()
