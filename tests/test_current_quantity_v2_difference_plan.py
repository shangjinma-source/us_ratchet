import unittest,json
from copy import deepcopy
from hashlib import sha256
from data.current_quantity_v2_difference_plan import build_account_difference_plan
from data.current_research_capital_decision_v2 import VERSION


def fixture():
    pins={'source':'a'*64};shares={'X':2};cash='0'
    b=dict(schema='CAPITAL_DECISION_MECHANIC_V2',selection_method=VERSION,decision_date='2026-10-13',
        state_revision='r1',available_cash=cash,shares=shares,investable_equity='100',source_hashes=pins,
        valuation_quotes={'X':{'price':'50','as_of':'2026-10-13','price_basis':'fixture','source_references':['source']}},search_arguments=dict(decision_date='2026-10-13',entered_cash='100',
        fee_bps='0',prices={'A':'1'},metadata={'A':{'ticker':'AAA','issuer_id':'ia'}}))
    identifier=sha256(json.dumps(b,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    selected=dict(quantities={'A':50},actual_weights={'A':'1/2'},notional='50',fees='0',residual_cash='50',actual_k=1)
    d=dict(method=VERSION,binding=b,decision_id=identifier,research_id=identifier[:24],target_quantities={'A':50},
        available_cash=cash,investable_equity='100',holding_market_values={'X':'100'},decision_date='2026-10-13',
        state_revision='r1',research_only=True,execution_blocked=True,
        search_result=dict(method_version=VERSION,status='BUDGET_STOPPED',selected=selected,entered_cash='100',decision_date='2026-10-13'))
    state=dict(account_id='synthetic-account',revision='r1',cash=cash,shares=shares,observed_at='2026-10-15T11:00:00-04:00',
        open_orders=[],reserved_cash='0',reserved_shares={},pending_rights=[])
    refs={};units={};now='2026-10-15T12:00:30-04:00'
    for sid,ticker,price in [('A','AAA','1'),('X','XXX','50.001')]:
        refs[sid]=dict(security_id=sid,ticker=ticker,currency='USD',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
            captured_at=now,checked_at=now,last_at='2026-10-15T12:00:25-04:00',minute_start='2026-10-15T11:59:00-04:00',
            minute_end='2026-10-15T12:00:00-04:00',valid_until='2026-10-15T12:02:00-04:00',
            session_open='2026-10-15T09:30:00-04:00',session_close='2026-10-15T16:00:00-04:00',
            session='2026-10-15',last_price=price,minute_low='1',source_hashes=pins)
        units[sid]=dict(security_id=sid,ticker=ticker,price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',capital_decision_id=identifier,status='NO_UNPROCESSED_ACTIONS',
            reference_source_hashes=pins,source_references=['source'],valuation_source_references=['source'],covered_from_date='2026-10-13',
            covered_through=now,reviewed_at=now)
    return dict(capital_decision=d,account_state=state,securities={'A':{'ticker':'AAA','issuer_id':'ia'},'X':{'ticker':'XXX','issuer_id':'ix'}},
        execution_references=refs,unit_continuity=units,source_hashes=pins,now=now,target_scope='ACCOUNT_EQUITY_TARGET',
        target_mandate=dict(account_id='synthetic-account',capital_decision_id=identifier,target_month='2026-10',active_date='2026-10-14',source_references=['source']))


class DifferenceTests(unittest.TestCase):
    def rebind(self,a):
        d=a['capital_decision'];b=d['binding']
        identifier=sha256(json.dumps(b,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        d['decision_id']=identifier;d['research_id']=identifier[:24]
        a['target_mandate']['capital_decision_id']=identifier
        for unit in a['unit_continuity'].values():unit['capital_decision_id']=identifier

    def test_sell_does_not_fund_buy_or_use_buycap(self):
        a=fixture();before=deepcopy(a);r=build_account_difference_plan(**a)
        self.assertEqual(r['status'],'READY');self.assertEqual(r['orders'],[dict(security_id='X',side='SELL',quantity=2,limit_price='5001/100')])
        self.assertEqual(r['reserved_buy_cash'],'0');self.assertEqual(r['wait_cash'][0]['remaining_deficit'],50)
        self.assertEqual(a,before)

    def test_cash_only_or_revision_or_open_order_reject(self):
        for change in [lambda a:a.update(target_scope='CASH_ONLY'),lambda a:a['account_state'].update(revision='r2'),
                       lambda a:a['account_state'].update(open_orders=[{'pending':True}]),
                       lambda a:a['account_state'].update(cash='100'),lambda a:a['account_state'].update(shares={})]:
            a=fixture();change(a);self.assertEqual(build_account_difference_plan(**a)['status'],'BLOCKED')

    def test_stale_units_missing_marks_tamper_and_month_reject(self):
        for change in [lambda a:a.update(now='2026-10-15T12:03:00-04:00'),lambda a:a['unit_continuity'].pop('X'),
                       lambda a:a['execution_references'].pop('X'),lambda a:a['capital_decision']['target_quantities'].update(A=51),
                       lambda a:a.update(now='2026-11-02T12:00:00-05:00')]:
            a=fixture();change(a);self.assertEqual(build_account_difference_plan(**a)['status'],'BLOCKED')

    def test_partial_cash_buys_do_not_count_sell_proceeds(self):
        a=fixture();d=a['capital_decision'];b=d['binding']
        a['account_state']['cash']='20';b['available_cash']='20';d['available_cash']='20'
        b['valuation_quotes']['X']['price']='40';d['holding_market_values']['X']='80'
        self.rebind(a)
        r=build_account_difference_plan(**a)
        self.assertEqual(r['status'],'READY',r)
        self.assertEqual(r['reserved_buy_cash'],'20');self.assertEqual(r['remaining_cash'],'0')
        self.assertEqual(next(o for o in r['orders'] if o['side']=='BUY')['quantity'],20)
        self.assertEqual(r['wait_cash'][0]['remaining_deficit'],30)
        self.assertEqual(r['unfilled_sell_proceeds'],'0')

    def test_prior_month_decision_active_this_month_and_future_rejected(self):
        a=fixture();d=a['capital_decision'];b=d['binding']
        for obj in (d,b,b['search_arguments'],d['search_result']):obj['decision_date']='2026-09-30'
        a['target_mandate']['active_date']='2026-10-01'
        for unit in a['unit_continuity'].values():unit['covered_from_date']='2026-09-30'
        self.rebind(a)
        self.assertEqual(build_account_difference_plan(**a)['status'],'READY')
        for obj in (d,b,b['search_arguments'],d['search_result']):obj['decision_date']='2026-10-30'
        self.rebind(a)
        self.assertEqual(build_account_difference_plan(**a)['reason'],'FUTURE_DECISION_DATE')

    def test_datetime_now_not_serializable_input_is_explicitly_rejected(self):
        from datetime import datetime
        a=fixture();a['now']=datetime.fromisoformat(a['now'])
        self.assertEqual(build_account_difference_plan(**a)['reason'],'ISO_NOW_REQUIRED')

    def test_malformed_dates_cannot_pass_lexical_comparison(self):
        for key in ('active_date', 'covered_from_date'):
            a=fixture()
            if key=='active_date': a['target_mandate'][key]='2026-10-00'
            else: a['unit_continuity']['A'][key]='2026-00-01'
            self.assertEqual(build_account_difference_plan(**a)['status'],'BLOCKED')

    def test_same_balances_do_not_authorize_a_different_account(self):
        a=fixture();a['account_state']['account_id']='another-account'
        self.assertEqual(build_account_difference_plan(**a)['reason'],'ACCOUNT_ID_MISMATCH')

    def test_adapter_quote_without_ticker_uses_bound_valuation_evidence(self):
        a=fixture()
        self.assertNotIn('ticker',a['capital_decision']['binding']['valuation_quotes']['X'])
        self.assertEqual(build_account_difference_plan(**a)['status'],'READY')
        a['unit_continuity']['X']['valuation_source_references']=['different-source']
        self.assertEqual(build_account_difference_plan(**a)['reason'],'VALUATION_IDENTITY_SOURCE_MISMATCH')

    def test_real_capital_adapter_output_reaches_difference_plan(self):
        # Tiny synthetic optimization, never a saved economic study or account.
        from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account, REQUIRED_PINS
        a=fixture();day='2026-10-13'
        pins={p:'a'*64 for p in (*REQUIRED_PINS,'source','backtest/return_priority_fresh_cash_quantity_search.py')}
        d=decide_quantity_v2_for_account(decision_date=day,
            account_state=dict(asof=day,revision='r1',cash='0',shares={'X':2},reserved_cash='0'),
            valuation_quotes=[dict(security_id=s,as_of=day,price=p,price_basis='SYNTHETIC',source_references=['source']) for s,p in [('A','1'),('X','50')]],
            source_hashes=pins,search_arguments=dict(decision_date=day,quote_as_of=day,price_basis='SYNTHETIC',
                prices={'A':'1'},metadata={'A':a['securities']['A']},entered_cash='100',fee_bps='0',minimum_cash_buffer='0',
                training_scenarios=[{'A':'2'},{'A':'1/2'}],scenario_dates=['2026-09-30',day],
                max_objective_evaluations=128,fixed_seed='synthetic'))
        a['capital_decision']=d;a['source_hashes']=pins
        a['target_mandate']['capital_decision_id']=d['decision_id']
        for unit in a['unit_continuity'].values():unit['capital_decision_id']=d['decision_id']
        result=build_account_difference_plan(**a)
        self.assertEqual(result['status'],'READY',result)
        self.assertEqual([(o['side'],o['security_id'],o['quantity']) for o in result['orders']],[('SELL','X',2)])
        self.assertEqual(result['reserved_buy_cash'],'0')

    def test_review_can_precede_request_but_must_cover_quote_capture(self):
        a=fixture();a['now']='2026-10-15T12:00:32-04:00'
        for ref in a['execution_references'].values():ref['checked_at']=a['now']
        for unit in a['unit_continuity'].values():unit['reviewed_at']='2026-10-15T12:00:31-04:00'
        self.assertEqual(build_account_difference_plan(**a)['status'],'READY')
        a['unit_continuity']['X']['covered_through']='2026-10-15T12:00:29-04:00'
        self.assertEqual(build_account_difference_plan(**a)['reason'],'UNIT_CONTINUITY_REQUIRED')


if __name__=='__main__':unittest.main()
