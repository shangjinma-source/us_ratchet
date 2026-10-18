"""Candidate/control separation; no accounting engine is invoked."""
import unittest
from test_ndx_conditional_single_window_account_arguments_research import fixture
from backtest import ndx_conditional_single_window_account_arguments_research as m


class IndependentAccountArgumentsReview(unittest.TestCase):
    def test_zero_weight_is_not_a_held_security(self):
        args=fixture(4);targets=args['schedule'][0]['targets'];sids=list(targets)
        targets[sids[0]]['target_weight']=0.
        for sid in sids[1:]:targets[sid]['target_weight']=1./3
        with self.assertRaises(ValueError):m.assemble_account_arguments(**args)

    def test_shared_channel_cannot_have_conflicting_control_identity(self):
        for field in ('security_id','issuer_id','risk_chain'):
            args=fixture();row=next(r for r in args['inputs']['incumbent_original_securities'] if r['ticker']=='GOOG')
            row[field]='fabricated'
            with self.subTest(field=field),self.assertRaises(ValueError):m.assemble_account_arguments(**args)

    def test_candidate_weights_and_exact_control_remain_separate(self):
        args=fixture(4);targets=args['schedule'][0]['targets'];sid=next(iter(targets));targets[sid]['target_weight']+=1e-13
        value=m.assemble_account_arguments(**args)
        self.assertEqual(value['candidate']['original_schedule'],args['schedule'])
        self.assertEqual(value['candidate']['arguments']['schedule'][0]['targets'][sid]['target_weight'],targets[sid]['target_weight'])
        expected={r['security_id']:r['target_weight'] for r in args['inputs']['incumbent_original_securities']}
        self.assertEqual({s:r['target_weight'] for s,r in value['incumbent']['arguments']['schedule'][0]['targets'].items()},expected)
        self.assertFalse(value['incumbent']['risk_is_order_gate'])
        self.assertFalse(value['candidate']['original_weights_normalized_by_assembler'])
        self.assertEqual(str(value['candidate']['arguments']['opens'].index[0].date()),'2026-03-18')
        self.assertEqual(value['candidate']['arguments']['schedule'][0]['execution_date'],'2026-03-19')


if __name__=='__main__':unittest.main()
