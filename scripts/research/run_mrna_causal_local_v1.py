"""Conditional MRNA supply-delay local replay; real risk, no future risk targets.

Source trigger and full explicit-repair chain remain external review obligations.
Only exact same-account monthly selections may be reused; otherwise fail closed.
"""
import json
from pathlib import Path
from fractions import Fraction
from hashlib import sha256
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backtest.historical_dividend_next_open_book_research import run_next_open_book
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from backtest.guidance_news_risk_research_v1 import GuidanceNewsRiskAdapter


def run(root):
    root=Path(root);out=root/'tmp/mrna_causal_local_20261027';out.mkdir(exist_ok=True)
    hashes={}
    def read(relative):
        p=root/relative;raw=p.read_bytes();hashes[relative]=sha256(raw).hexdigest();return json.loads(raw)
    case=read('tmp/local_news_cases_20261027/MRNA_Q3.json')
    book=read('tmp/recent_continuous_baseline_20261026_v7/book.json')
    inputs=read('tmp/recent_continuous_baseline_20261026_v7/execution_inputs.json')
    story=read('tmp/mrna_update_chain_20261027/stories/8894899454058333.json')
    stream=read('tmp/mrna_update_chain_20261027/reviewed_events.json')
    clock=read('tmp/news_session_clock_20261027/clock.json')
    session_closes={x['date']:x['close'] for x in clock['sessions']}
    for event in stream['events']:
        path=root/event['source_path']
        digest=sha256(path.read_bytes()).hexdigest()
        if digest not in event['source_hashes']:raise ValueError('EVENT_SOURCE_CHANGED')
        hashes[event['source_path']]=digest
    review=root/stream['events'][0]['review_reference']
    if sha256(review.read_bytes()).hexdigest()!=stream['review_sha256']:raise ValueError('EVENT_REVIEW_CHANGED')
    hashes[stream['events'][0]['review_reference']]=stream['review_sha256']
    published=story['qmcistory']['qmnews']['qmstory']['datetime']
    available=datetime.fromisoformat(published)
    if available.isoformat()!='2021-11-04T07:00:00-04:00':raise ValueError('EXPECTED_EVENT_TIME_CHANGED')
    if case['initialization_requires_entitlement_reconstruction']:raise ValueError('INITIAL_RIGHTS_UNSUPPORTED')
    days=case['session_dates'];initial,last=days[0],days[-1];sid=case['security_id']
    assembled=inputs['assembled'];frozen=case['corporate_action_inputs']
    def within(e):return initial<e.get('effective_date',e.get('date',''))<=last
    kwargs=dict(session_dates=days,ohlc=case['ohlc'],initial_cash=case['initial_baseline_ledger']['cash'],
        initial_shares=case['initial_baseline_ledger']['shares'],fee_bps='0',slippage_bps='5',
        events=[e for e in frozen['actions'] if within(e)],cash_stock_merger_events=[e for e in frozen['cash_stock_merger_events'] if within(e)],
        distribution_events=[e for e in frozen['distribution_events'] if within(e)],fractional_settlements=frozen['fractional_settlements'],
        distribution_fractional_cash_values=frozen['distribution_fractional_cash_values'],price_source_references=frozen['price_source_references'],
        account_model=assembled.get('account_model'),dividend_events=[e for e in case['dividend_events'] if initial<e['ex_date']<=last])
    # This local increment supports no action coordinate transitions; do not silently
    # skip adjustments needed by a wider or different case.
    if kwargs['events'] or kwargs['cash_stock_merger_events'] or kwargs['distribution_events']:
        raise ValueError('LOCAL_ACTION_COORDINATE_ADAPTER_REQUIRED')
    selections={a['decision_date']:a for a in book['selection_account_states']}
    monthly={p['decision_date']:p for p in assembled['monthly_inputs']}
    audits=dict(zip(assembled['session_dates'][:-1],book['provider_audit']))
    results={}
    for arm in ('NO_ACTION','CONDITIONAL_SUPPLY_DELAY_BLOCK_NEW_BUYS'):
        risk=MonthlyExitCoreResearchAdapter(actions=assembled['actions'])
        risk.state=deepcopy(case['initial_risk_state_before_close']);risk.last_day=risk.state['session_date']
        overlay=GuidanceNewsRiskAdapter(risk,events=stream['events'] if arm!='NO_ACTION' else [],session_closes=session_closes,action_policy='BLOCK_NEW_BUYS',release_policy='EXPLICIT_REPAIR')
        ceiling=deepcopy(case['initial_close_baseline_audit']['monthly_ceiling'])
        epoch=case['initial_close_baseline_audit']['target_decision_date'];trace=[];reuse=[]
        def provider(*,decision_date,active_date,state):
            nonlocal ceiling,epoch
            if state.get('pending_post_close_coordinates') or state.get('distribution_rights') or state.get('merger_entitlements') or Fraction(state.get('receivable','0')):
                raise ValueError('LOCAL_ENTITLEMENT_OR_ACTION_STATE_UNSUPPORTED')
            if decision_date in monthly:
                observed=dict(asof=decision_date,revision='synthetic-book:'+decision_date,cash=state['cash'],shares=state['shares'],reserved_cash='0')
                expected=selections[decision_date]['account_state']
                if observed!=expected:raise ValueError('BRANCH_ACCOUNT_DIFFERS_RECOMPUTE_REQUIRED')
                # Also bind the original selection inputs to the frozen plan.
                for key in ('valuation_quotes','search_arguments','source_hashes'):
                    if selections[decision_date][key]!=monthly[decision_date][key]:raise ValueError('SELECTION_PLAN_BINDING_CHANGED')
                ceiling=deepcopy(audits[decision_date]['monthly_ceiling']);epoch=decision_date
                reuse.append(dict(decision_date=decision_date,exact_account_state=observed,reason='EXACT_ACCOUNT_AND_SELECTION_INPUT_MATCH'))
            target,diagnostics=overlay.apply(day=decision_date,month=epoch,target=deepcopy(ceiling),
                    closes={s:case['close_prices'][s][decision_date] for s in ceiling},shares=state['shares'])
            active=sid in diagnostics['guidance_news']['blocked_security_ids']
            orders=[]
            for security in sorted(set(state['shares'])|set(target)):
                delta=target.get(security,0)-state['shares'].get(security,0)
                if delta:orders.append(dict(id='causal:'+decision_date+':'+security,security_id=security,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),decision_date=decision_date,active_date=active_date,decision_mark=case['close_prices'][security][decision_date]))
            trace.append(dict(decision_date=decision_date,active_date=active_date,account_state=deepcopy(state),monthly_ceiling=deepcopy(ceiling),
                risk=diagnostics,news_active=active,news_availability=published,event_review='CONDITIONAL_SOURCE_BOUND_RELEASE_REVIEW_NOT_UNIVERSAL_COVERAGE',effective_target=target,orders=orders))
            return dict(status='READY',orders=orders)
        replay=run_next_open_book(**kwargs,order_provider=provider)
        if replay['status']!='COMPLETE':raise ValueError(('INCOMPLETE',arm,replay['reason']))
        if arm=='NO_ACTION':
            for a,b in zip(replay['daily_ledger'],case['baseline_comparison_ledger']):
                for key in ('date','cash','shares','equity','dividend_receivable'):
                    if a.get(key,'0')!=b.get(key,'0'):raise ValueError(('BASELINE_NOT_EXACT',a['date'],key))
            if len(replay['daily_ledger'])!=20:raise ValueError('TWENTY_SESSIONS_REQUIRED')
        results[arm]=dict(book=replay,decision_trace=trace,exact_selection_reuse=reuse)
        (out/(arm+'.json')).write_text(json.dumps(results[arm],indent=2),encoding='utf-8')
    base=results['NO_ACTION']['book'];branch=results['CONDITIONAL_SUPPLY_DELAY_BLOCK_NEW_BUYS']['book']
    differences=[dict(date=a['date'],baseline_equity=a['equity'],conditional_equity=b['equity'],difference=str(Fraction(b['equity'])-Fraction(a['equity'])))
        for a,b in zip(base['daily_ledger'],branch['daily_ledger']) if a['cash']!=b['cash'] or a['shares']!=b['shares']]
    for relative in ('backtest/historical_dividend_next_open_book_research.py',
                     'backtest/monthly_exit_core_research_adapter.py', 'core/monthly_peak_exit.py',
                     'backtest/guidance_news_risk_research_v1.py'):
        hashes[relative]=sha256((root/relative).read_bytes()).hexdigest()
    hashes[str(Path(__file__).relative_to(root))]=sha256(Path(__file__).read_bytes()).hexdigest()
    summary=dict(status='CONDITIONAL_CAUSAL_LOCAL_REPLAY_COMPLETE',sessions=20,baseline_daily_exact=True,
        source_hashes=hashes,availability=published,first_different_account_date=differences[0]['date'] if differences else None,
        terminal_equity_delta=str(Fraction(branch['daily_ledger'][-1]['equity'])-Fraction(base['daily_ledger'][-1]['equity'])),
        differences=differences,selection_reuse=results['CONDITIONAL_SUPPLY_DELAY_BLOCK_NEW_BUYS']['exact_selection_reuse'],
        limitations=['Conditional rule consumes 14 source-bound reviewed releases; absence of repair outside that collected corpus is not proven.',
            'Collected issuer Business Wire release review covers November 4 through December 3; other communications and immutable historical versions remain outside verified scope.',
            'Initialized Nov4 close before first close-rule execution, although announcement was public that morning.',
            'Real original risk advances daily; future effective-risk targets never used as decisions.',
            'No optimization: monthly ceiling reused only after exact branch account and original input equality.',
            'Twenty-day local evidence only; no annualization, deployment or universal effectiveness claim.'])
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    root=Path(__file__).resolve().parents[2]
    result=run(root);print(json.dumps({k:result[k] for k in ('status','first_different_account_date','terminal_equity_delta')}))
