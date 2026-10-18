"""Synthetic risk records and metric checks; no real candidate accounting."""
from decimal import localcontext,Inexact,Rounded,ROUND_UP
import unittest
from unittest.mock import patch
from scripts import ndx_legacy_six_period_account_comparison_20260923 as m
import test_ndx_drawdown_six_period_account_comparison_20260923 as history


class IndependentReview(unittest.TestCase):
    def test_no_plan_not_rejection_and_rejected_basket_has_no_legs(self):
        for attack in ('no_plan_reject','no_plan_trade','rejected_trade','cash','duplicate'):
            schedule,identity,execution=history.history_fixture()
            _,report=m.independent_risk_history(schedule,identity,execution)
            self.assertEqual((report['execution_count'],report['no_plan_count'],report['rejected_execution_count']),(4,2,3))
            if attack=='no_plan_reject':execution['decisions'][2]['status']='REJECTED'
            if attack=='no_plan_trade':execution['trades'].append(dict(session=m.CLOCK[2][1]))
            if attack=='rejected_trade':execution['trades'].append(dict(session=m.CLOCK[1][1]))
            if attack=='cash':execution['executions'][-1]['cash_after_usd']=101
            if attack=='duplicate':execution['executions'].append(execution['executions'][-1])
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.independent_risk_history(schedule,identity,execution)

    def test_old_held_security_survives_more_than_one_prior_target(self):
        schedule,identity,execution=history.history_fixture()
        _,report=m.independent_risk_history(schedule,identity,execution)
        self.assertEqual(report['cutoff_evidence'][m.CLOCK[-1][0]]['observation_dates']['S0'],m.CLOCK[0][0])
        execution['daily'][-1]['risk_chain_observation_dates']['S0']=m.CLOCK[-1][0]
        with self.assertRaises(ValueError):m.independent_risk_history(schedule,identity,execution)

    def test_future_risk_reclassification_not_backfilled(self):
        schedule,identity,execution=history.history_fixture();day=m.CLOCK[-1][0]
        identity['saved_lane_choices'][-1]['saved_candidate']['selected']['S1']['risk_chain']='changed'
        identity['selected_risk_chains_by_decision'][day]['S1']='changed'
        schedule['risk_chains_by_decision'][day]['S1']='changed';execution['decisions'][-1]['risk_chains']['S1']='changed'
        m.independent_risk_history(schedule,identity,execution)
        execution['decisions'][1]['risk_chains']['S1']='changed'
        with self.assertRaises(ValueError):m.independent_risk_history(schedule,identity,execution)

    def test_current_source_guard_cannot_use_archive_replacement(self):
        with patch.object(m.archive,'strict',side_effect=ValueError('drift')) as strict,patch.object(m.archive,'verify_expected_sources') as fallback:
            with self.assertRaises(ValueError):m.current_source_guard()
            fallback.assert_not_called()
        sources=strict.call_args.args[0]
        self.assertEqual(sources[str(m.PRODUCER)],m.PRODUCER_SHA)
        self.assertEqual(sources[str(m.SOURCE)],m.LOADED[str(m.SOURCE)])

    def test_hard_candidate_refusal_before_io_and_decimal_environment(self):
        with patch.object(m.archive,'strict') as strict,patch.object(m.Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.build('unused','0'*64,m.PRODUCER_SHA)
            strict.assert_not_called();read.assert_not_called()
        values=['100.123']*106+['112.345'];expected=m.metrics(values)
        with localcontext() as context:
            context.prec=2;context.rounding=ROUND_UP;context.traps[Inexact]=True;context.traps[Rounded]=True
            self.assertEqual(m.metrics(values),expected)
        self.assertEqual(expected['return_interval_count'],106)


if __name__=='__main__':unittest.main()
