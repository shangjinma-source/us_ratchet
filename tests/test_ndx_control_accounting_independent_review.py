import copy
import unittest
from test_ndx_fixed_control_accounting_independent_audit_research import fixture, snapshot
from backtest import ndx_fixed_control_accounting_independent_audit_research as m


def fee_boundary():
    args = fixture()
    account = args['execution']
    ids = sorted(args['schedule'][0]['targets'])
    marks = {sid: 12.5 for sid in ids}
    # 249 shares each exhaust the 24900 investable amount before fees.
    # Tie-breaking reduces the greatest SID twice, leaving cash 100.125.
    wanted = {sid: 249 for sid in ids}
    wanted[ids[-1]] = 247
    fee, cash = 24.875, 100.125
    chains = args['risk_chains_by_decision'][args['calendar'][0]]
    for row in args['prices'].values():
        for value in row.values():
            value.update(open=12.5, close=12.5)
    decision, fill = account['decisions'][0], account['executions'][0]
    decision.update(desired_shares=wanted.copy(), delta=wanted.copy(), prices=marks.copy(),
                    projected_cash_usd=cash, projected_fees_usd=fee,
                    decision_risk=snapshot(wanted, marks, chains))
    fill.update(desired_shares=wanted.copy(), frozen_delta=wanted.copy(), prices=marks.copy(),
                projected_cash_usd=cash, projected_fees_usd=fee, cash_after_usd=cash,
                shares_after=wanted.copy(), risk=snapshot(wanted, marks, chains))
    for row in account['daily'][1:]:
        row.update(shares=wanted.copy(), prices=marks.copy(), cash_usd=cash,
                   total_value_usd=24975.125, risk=snapshot(wanted, marks, chains))
    account['trades'] = [dict(session=args['calendar'][1], security_id=sid, ticker=sid.upper(),
                             share_delta=q, price_usd=12.5, transaction_cost_usd=q*.0125)
                         for sid, q in wanted.items()]
    account['summary'].update(terminal_value_usd=24975.125, path_return_net=-.000995,
                              path_max_drawdown=.000995)
    return args


class ControlIndependentReview(unittest.TestCase):
    def test_fee_buffer_reduces_shares_without_risk_projection(self):
        args = fee_boundary()
        report = m.audit(**args)
        self.assertTrue(report['filled'])
        self.assertFalse(args['execution']['executions'][0]['risk']['all_passed'])
        self.assertEqual(report['fees_usd'], '24.8750')
        self.assertEqual(report['positive_final_holdings'], 8)

    def test_risk_rejection_partial_fill_and_boolean_zero_rejected(self):
        for defect in ('risk_gate', 'partial', 'bool_zero'):
            args = fixture(defect == 'partial')
            if defect == 'risk_gate':
                args['execution']['executions'][0].update(status='REJECTED', failure_reasons=['RISK_CHAIN_TOP1'])
            elif defect == 'partial':
                args['execution']['executions'][0]['shares_after'] = {'s0': 1}
            else:
                args['execution']['daily'][1]['shares']['s7'] = False
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                m.audit(**args)


if __name__ == '__main__':
    unittest.main()
