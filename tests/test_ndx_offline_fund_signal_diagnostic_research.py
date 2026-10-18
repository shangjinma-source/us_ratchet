import copy
import unittest
from decimal import Decimal, Inexact, localcontext

from backtest import ndx_offline_fund_signal_diagnostic_research as m


class DiagnosticTests(unittest.TestCase):
    def fixture(self):
        return dict(execution_items=[dict(ticker='MSFT',side='BUY',source='tactical_limit',action='BUY_NOW',amount=118,limit=498.43,share_plan_eligible=True)],
            gap_rows=[dict(ticker='MSFT',gap_amount=2000,position_kind='pending_entry')],
            research_cash_usd=1000,policy=dict(allow_fractional=False,lot_size=1,fee_bps=10,min_fee=1))

    def test_cash_does_not_expand_signal_and_input_not_mutated(self):
        args=self.fixture(); original=copy.deepcopy(args)
        row=m.diagnose(**args)['rows'][0]
        self.assertIn('STRATEGY_BUDGET_BELOW_ONE_UNIT',row['blocking_codes'])
        self.assertEqual(row['strategy_budget'],118)
        self.assertEqual(args,original)
        args['research_cash_usd']=10000
        self.assertIs(m.diagnose(**args)['rows'][0]['first_unit_affordable'],False)

    def test_gap_and_fee_gates_separate_minimum_once_per_unit(self):
        args=self.fixture();args['execution_items'][0].update(amount=1000,limit=100)
        args['policy'].update(lot_size=2,min_fee=5)
        args['gap_rows'][0]['gap_amount']=150
        args['research_cash_usd']=200
        row=m.diagnose(**args)['rows'][0]
        self.assertEqual(row['one_unit_fee_usd'],'5')
        self.assertEqual(row['one_unit_cash_required_usd'],'205')
        self.assertIn('REAL_GAP_BELOW_ONE_UNIT',row['blocking_codes'])
        self.assertIn('RESEARCH_CASH_INSUFFICIENT_INCLUDING_FEE',row['blocking_codes'])
        args['gap_rows'][0]['gap_amount']=500;args['research_cash_usd']=205
        self.assertIs(m.diagnose(**args)['rows'][0]['first_unit_affordable'],True)

    def test_closed_deep_and_wait_keep_observation(self):
        args=self.fixture();args['gap_rows'][0]['position_kind']='reported_closed'
        args['execution_items'][0].update(source='ratchet_next',action='WAIT',amount=0)
        row=m.diagnose(**args)['rows'][0]
        self.assertEqual(row['observation_limit'],498.43)
        for code in ['REPORTED_CLOSED_EXCLUDED','DEEP_RATCHET_EXCLUDED','ACTION_NOT_BUY_OR_LIMIT']:
            self.assertIn(code,row['blocking_codes'])
        self.assertIsNone(row['allocated_shares'])

    def test_missing_fields_and_ambiguous_gaps_are_unknown(self):
        args=self.fixture();args['execution_items'][0]['amount']=1000
        del args['policy']['fee_bps'];del args['execution_items'][0]['share_plan_eligible']
        row=m.diagnose(**args)['rows'][0]
        self.assertEqual(row['status'],'UNKNOWN');self.assertIsNone(row['first_unit_affordable'])
        self.assertIn('RESEARCH_CASH_OR_FEE_UNKNOWN',row['unknown_codes'])
        args['gap_rows'].append(copy.deepcopy(args['gap_rows'][0]))
        self.assertIn('GAP_ROW_AMBIGUOUS',m.diagnose(**args)['rows'][0]['unknown_codes'])
        for v in [False,'NaN','Infinity',-1]:self.assertIsNone(m.decimal_or_none(v))

    def test_limit_precedence_and_fractional_not_claimed(self):
        args=self.fixture();args['execution_items'][0].update(amount=1000,limit=0,live_price=10)
        row=m.diagnose(**args)['rows'][0]
        self.assertIsNone(row['selected_price_usd'])
        args['execution_items'][0]['limit']=None;args['policy']['allow_fractional']=True
        row=m.diagnose(**args)['rows'][0]
        self.assertIn('FRACTIONAL_POLICY_NOT_MODELLED',row['unknown_codes'])
        self.assertFalse(row['order_authorized'])

    def test_non_integer_whole_share_unit_is_blocked(self):
        args=self.fixture();args['execution_items'][0].update(amount=1000,limit=100)
        for lot in ['0.5','1.5']:
            args['policy']['lot_size']=lot
            row=m.diagnose(**args)['rows'][0]
            self.assertIn('NON_INTEGER_LOT_IN_WHOLE_SHARE_MODE',row['blocking_codes'])
            self.assertIs(row['first_unit_affordable'],False)

    def test_unknown_position_and_whitespace_ticker_do_not_pass(self):
        args=self.fixture();args['execution_items'][0]['amount']=1000
        args['gap_rows'][0]['position_kind']='imaginary'
        row=m.diagnose(**args)['rows'][0]
        self.assertIn('POSITION_KIND_UNKNOWN',row['unknown_codes'])
        self.assertIsNone(row['first_unit_affordable'])
        args['gap_rows'][0]['position_kind']='real_position'
        for ticker in ['', ' ', ' MSFT', 'MSFT ', 'MS FT', '\t']:
            args['execution_items'][0]['ticker']=ticker
            args['gap_rows'][0]['ticker']=ticker
            row=m.diagnose(**args)['rows'][0]
            self.assertIn('TICKER_UNKNOWN',row['unknown_codes'])
            self.assertIsNone(row['first_unit_affordable'])

    def test_decimal_context_does_not_change_borderline_budget(self):
        args=self.fixture();args['execution_items'][0].update(amount='100.00',limit='100.011')
        expected=m.diagnose(**args)
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True
            actual=m.diagnose(**args)
            self.assertEqual(context.prec,2)
            self.assertTrue(context.traps[Inexact])
        self.assertEqual(actual,expected)
        self.assertIn('STRATEGY_BUDGET_BELOW_ONE_UNIT',actual['rows'][0]['blocking_codes'])

    def test_wide_decimal_span_exact_and_extreme_exponents_rejected(self):
        args=self.fixture();args['execution_items'][0].update(amount='1e100',limit='1e-100')
        args['policy'].update(fee_bps='1e-100',min_fee=0)
        row=m.diagnose(**args)['rows'][0]
        self.assertEqual(Decimal(row['one_unit_fee_usd']),Decimal('1e-204'))
        with localcontext() as context:
            context.prec=300
            self.assertEqual(Decimal(row['one_unit_cash_required_usd']),Decimal('1e-100')+Decimal('1e-204'))
        for price in ['1e999999999','1e-999999999','0e-999999999']:
            args['execution_items'][0]['limit']=price
            with self.assertRaisesRegex(ValueError,'Numeric range'):
                m.diagnose(**args)


if __name__=='__main__':unittest.main()
