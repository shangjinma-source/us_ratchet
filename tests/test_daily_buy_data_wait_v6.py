from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest
import test_daily_composition_v3 as fixtures
from data.strategy_daily_composition_v6 import DailyCompositionV6


class BuyDataFailureTests(unittest.TestCase):
    def scenario(self, reason, sell_failure=None):
        with TemporaryDirectory() as directory:
            case=fixtures.CompositionTests().setup_case(directory,'A')
            case.store.append(dict(event_id='cash-fallback-v6',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'),expected_revision=case.state['revision'])
            state=case.store.read();before=case.store.path.read_bytes();target=deepcopy(case.target)
            original=case.provider.limits;calls=[]
            def limits(**kwargs):
                calls.append(deepcopy(kwargs['target_quantities']))
                if kwargs['target_quantities'].get('B',0)>0:raise ValueError(reason)
                if sell_failure:raise ValueError(sell_failure)
                return original(**kwargs)
            case.provider.limits=limits
            service=DailyCompositionV6(monthly_service=case.monthly,evidence_reader=case.reader,
                execution_provider=case.provider.execution,clock=lambda:case.clock[0],
                policy_execution_enabled=True,policy_id=fixtures.POLICY,fee_bps='10')
            try:
                result=service.preview(expected_revision=state['revision'],target_id=target['target_id'])
                return result,calls
            finally:
                self.assertEqual(case.store.path.read_bytes(),before)
                self.assertEqual(case.target,target)

    def test_minute_failures_revalidate_sells_only(self):
        for reason in ['NONCONTIGUOUS_OR_FUTURE_MINUTE','INCOMPLETE_SESSION_MINUTES',
                       'PARTIAL_NULL_MINUTE','ZERO_VOLUME_MINUTE_UNAVAILABLE',
                       'HALT_ACTIVE_OR_RESUME_UNCONFIRMED','HALT_EXECUTION_EVIDENCE_REQUIRED']:
            with self.subTest(reason=reason):
                result,calls=self.scenario(reason)
                self.assertEqual(result['status'],'READY')
                self.assertEqual([(x['security_id'],x['side']) for x in result['new_orders']],[('A','SELL')])
                self.assertEqual(result['effective_target_quantities']['B'],10)
                self.assertEqual(result['waiting_data'][0]['data_failure'],reason)
                self.assertEqual(len(calls),2)

    def test_unrelated_notice_failure_not_reclassified(self):
        with self.assertRaisesRegex(ValueError,'KNOWN_NOTICE_REQUIRES_REVIEW'):
            self.scenario('KNOWN_NOTICE_REQUIRES_REVIEW')

    def test_failing_sell_recheck_returns_no_partial_success(self):
        with self.assertRaisesRegex(ValueError,'SELL_MARK_INVALID'):
            self.scenario('PARTIAL_NULL_MINUTE','SELL_MARK_INVALID')
