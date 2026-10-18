import unittest
from test_ndx_historical_cross_k_account_independent_research import fixture
from backtest import ndx_historical_cross_k_account_independent_research as m


class AccountReaderReview(unittest.TestCase):
    def test_control_issuer_duplication_cannot_be_coherently_relabelled(self):
        args=fixture();rows=args['inputs']['incumbent_original_securities']
        rows[0]['issuer_id']=rows[1]['issuer_id']
        args['control_execution']['decisions'][0]['targets'][rows[0]['security_id']]['issuer_id']=rows[0]['issuer_id']
        with self.assertRaises(ValueError):m.audit_candidate(**args)

    def test_joint_raw_cash_edit_and_known_forward_action_are_rejected(self):
        for defect in ('cash','event'):
            args=fixture()
            if defect=='cash':
                for key in ('raw_execution','execution'):
                    args[key]['daily'][2]['cash_usd']+=1
                    args[key]['daily'][2]['total_value_usd']+=1
            else:
                ticker=next(iter(args['inputs']['prices']['submitted_full_split_events']))
                args['inputs']['prices']['submitted_full_split_events'][ticker].append({'session':'2026-03-19','new_shares':2,'old_shares':1})
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.audit_candidate(**args)


if __name__=='__main__':unittest.main()
