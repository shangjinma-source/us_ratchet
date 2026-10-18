import copy,json,unittest
from pathlib import Path
from decimal import Decimal
from backtest import ndx_fixed_control_accounting_independent_audit_research as m

CONTRACT=dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)


def snapshot(shares,marks,chains):
    positive={s:q for s,q in shares.items() if q};checks=m.risk.risk_checks(positive,{s:Decimal(str(marks[s])) for s in positive},chains,CONTRACT)
    value=dict(checks=checks,all_passed=all(checks.values()))
    if positive:
        total=sum(q*marks[s] for s,q in positive.items());weights={s:q*marks[s]/total for s,q in positive.items()};ordered=sorted(weights.values(),reverse=True)
        value.update(actual_weights=weights,top1_weight=ordered[0],minimum_single_weight=ordered[-1],top3_weight=sum(ordered[:3]),effective_n=1/sum(w*w for w in ordered),risk_chain_top1_weight=1.)
    value.update(target_slot_count=len(shares),positive_holding_count=len(positive),zero_share_security_ids=sorted(s for s,q in shares.items() if not q),financial_allocation_checks={'NONNEGATIVE_WHOLE_SHARES':True},risk_is_order_gate=False)
    return value


def fixture(rejected=False):
    inputs=json.loads(Path('data/cache/research/latest_twenty_historical_inputs_20260919_v1/inputs.json').read_bytes());calendar=inputs['prices']['calendar'][126:]
    ids=['s'+str(i) for i in range(8)];chains={s:'same_chain' for s in ids};targets={s:dict(ticker=s.upper(),issuer_id='issuer'+s,target_weight=.125) for s in ids}
    close={s:1e9 if s=='s7' else 100. for s in ids};opened={s:close[s]*(10 if rejected else 1) for s in ids}
    prices={d:{s:dict(ticker=s.upper(),open=opened[s],close=close[s]) for s in ids} for d in calendar}
    wanted={s:0 if s=='s7' else 31 for s in ids};fees=sum(q*opened[s]*.001 for s,q in wanted.items());after=25000-sum(q*opened[s] for s,q in wanted.items())-fees
    decision=dict(decision_date=calendar[0],execution_date=calendar[1],targets=targets,target_k=8,status='FROZEN',shares_before={},desired_shares=wanted,delta=wanted.copy(),risk_chains=chains,risk_chain_observation_dates={s:calendar[0] for s in ids},cash_before_usd=25000.,projected_cash_usd=3278.3,projected_fees_usd=21.7,prices=close,decision_risk=snapshot(wanted,close,chains))
    held={} if rejected else wanted.copy();cash=25000. if rejected else after
    fill=dict(session=calendar[1],decision_date=calendar[0],shares_before={},desired_shares=wanted,frozen_delta=wanted.copy(),status='REJECTED' if rejected else 'FILLED',failure_reasons=['CASH_BUFFER'] if rejected else [],cash_before_usd=25000.,projected_cash_usd=after,projected_fees_usd=fees,prices=opened,risk=snapshot(wanted,opened,chains),shares_after=held,cash_after_usd=cash)
    if not rejected:fill['accounting_error_usd']=0.
    daily=[]
    for i,d in enumerate(calendar):
        shares=held.copy() if i else {};balance=cash if i else 25000.;marks={s:close[s] for s in shares}
        daily.append(dict(session=d,shares=shares,tickers={s:s.upper() for s in shares},risk_chains={s:chains[s] for s in shares},risk_chain_observation_dates={s:calendar[0] for s in shares},prices=marks,risk=snapshot(shares,marks,chains),cash_usd=balance,total_value_usd=balance+sum(q*close[s] for s,q in shares.items())))
    trades=[] if rejected else [dict(session=calendar[1],security_id=s,ticker=s.upper(),share_delta=q,price_usd=opened[s],transaction_cost_usd=q*opened[s]*.001) for s,q in wanted.items() if q]
    terminal=daily[-1]['total_value_usd']
    execution=dict(schema='ndx_dynamic_frozen_incumbent_control_v1',risk_is_order_gate=False,original_target_weights_modified=False,zero_share_target_slots_allowed=True,candidate_eligibility_claimed=False,corporate_actions=[],identity_events=[],dividend_modelled=False,execution_policy='DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET',decisions=[decision],executions=[fill],daily=daily,trades=trades,summary=dict(session_count=127,all_cash_session_count=127 if rejected else 1,k_path=[8],terminal_value_usd=terminal,path_return_net=terminal/25000-1,path_max_drawdown=1-terminal/25000))
    return dict(execution=execution,calendar=calendar,schedule=[{k:decision[k] for k in ('decision_date','execution_date','targets')}],prices=prices,risk_chains_by_decision={calendar[0]:chains},contract=CONTRACT)


class FixedControlTests(unittest.TestCase):
    def test_zero_slot_and_failed_risk_still_fills_financial_control(self):
        args=fixture();self.assertFalse(args['execution']['decisions'][0]['decision_risk']['all_passed'])
        report=m.audit(**args);self.assertTrue(report['filled']);self.assertEqual(report['zero_share_security_ids'],['s7']);self.assertEqual(report['trade_count'],7)
        self.assertEqual(report['positive_final_holdings'],7)

    def test_gap_rejection_preserves_cash_and_no_trades(self):
        report=m.audit(**fixture(True));self.assertTrue(report['rejected']);self.assertEqual(report['trade_count'],0);self.assertEqual(Decimal(report['terminal_value_usd']),25000)

    def test_fee_clock_and_zero_slot_mutations_rejected(self):
        for defect in ('fee','clock','zero','fake_risk','zero_trade'):
            args=fixture();value=args['execution']
            if defect=='fee':value['executions'][0]['projected_fees_usd']+=1
            elif defect=='clock':value['executions'][0]['session']=args['calendar'][2]
            elif defect=='zero':value['daily'][2]['shares'].pop('s7')
            elif defect=='fake_risk':value['executions'][0]['risk']['all_passed']=True
            else:value['trades'].append(dict(value['trades'][0],security_id='s7',share_delta=0))
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.audit(**args)


if __name__=='__main__':unittest.main()
