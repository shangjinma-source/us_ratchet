from copy import deepcopy
from fractions import Fraction
from scripts.research.run_news_preopen_execution_probe_v1 import eligible,replay
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


def fixture():
    sid='research:security:mrna'; days=['2021-07-14','2021-07-15','2021-07-16','2021-07-19','2021-07-20']
    risk=MonthlyExitCoreResearchAdapter()
    risk.apply(day='2021-06-30',month='2021-06-30',target={sid:4},closes={sid:'100'})
    _,diag=risk.apply(day=days[0],month='2021-06-30',target={sid:4},closes={sid:'100'})
    audit={'risk_overlay':deepcopy(diag),'monthly_ceiling':{sid:4},'target_decision_date':'2021-06-30'}
    prices={d:'100' for d in days}
    inputs={'assembled':{'session_dates':days,'monthly_inputs':[],'close_prices':{sid:prices}},'ohlc':{sid:{d:{'open':'120','high':'120','low':'100','close':'100'} for d in days}}}
    book={'provider_audit':[audit]*4,'daily_ledger':[{'date':'2021-07-15','shares':{sid:4},'cash':'500'}]}
    return inputs,book


def test_publication_plus_latency_must_precede_open():
    assert eligible('2021-07-15T19:01:00-04:00','2021-07-16T09:30:00-04:00')
    assert not eligible('2021-07-16T09:28:00-04:00','2021-07-16T09:30:00-04:00')
    assert not eligible('2021-07-16T10:00:00-04:00','2021-07-16T09:30:00-04:00')


def test_after_close_news_executes_next_open_not_next_close():
    i,b=fixture(); result=replay(i,b,'EXIT'); rows=result['book']['daily_ledger'];sid='research:security:mrna'
    assert result['trace'][0]['news_active']
    assert rows[0]['shares'][sid]==0
    assert Fraction(rows[0]['cash'])==500+4*Fraction(120)*Fraction('0.9995')
    assert rows[1]['shares'][sid]==0
    assert not result['trace'][2]['news_active']
    assert rows[2]['shares'][sid]==4
    assert Fraction(rows[2]['cash'])==500+4*120*Fraction('0.9995')-4*120*Fraction('1.0005')


def test_late_news_does_not_rewrite_first_open():
    i,b=fixture();result=replay(i,b,'EXIT',published='2021-07-16T10:00:00-04:00')
    assert result['book']['daily_ledger'][0]['shares']['research:security:mrna']==4
    assert not result['trace'][0]['news_active']


def test_expiry_cannot_unlock_original_exit():
    i,b=fixture();sid='research:security:mrna'
    for day in ('2021-07-16','2021-07-19','2021-07-20'):
        i['assembled']['close_prices'][sid][day]='70'
        i['ohlc'][sid][day]={'open':'100','high':'100','low':'70','close':'70'}
    result=replay(i,b,'EXIT')
    assert not result['trace'][2]['news_active']
    assert result['trace'][2]['original_target'][sid]==0
    assert result['book']['daily_ledger'][-1]['shares'][sid]==0


def test_event_day_close_cannot_change_same_open_order_or_fill():
    inputs,book=fixture()
    changed=deepcopy(inputs);sid='research:security:mrna'
    changed['assembled']['close_prices'][sid]['2021-07-16']='50'
    changed['ohlc'][sid]['2021-07-16']['close']='50'
    changed['ohlc'][sid]['2021-07-16']['low']='50'
    for action in ('NO_CHANGE','BLOCK_NEW_BUYS','EXIT','HALF_TARGET'):
        original=replay(inputs,book,action); altered=replay(changed,book,action)
        assert original['trace'][0]==altered['trace'][0]
        def fills(result):
            return [x for x in result['book']['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED' and x['date']=='2021-07-16']
        assert fills(original)==fills(altered)


def test_gap_excluded_from_common_open_performance():
    from scripts.research.run_news_preopen_execution_probe_v1 import opening_metrics
    i,b=fixture();initial=dict(b['daily_ledger'][0],equity='900')
    results={'EXIT':replay(i,b,'EXIT')}
    m=opening_metrics(initial,i['ohlc'],results,'2021-07-16')
    assert Fraction(m['common_pre_fill_open_equity'])==980
    assert Fraction(m['shared_close_to_open_gap_pnl'])==80
    assert Fraction(m['arms']['EXIT']['first_open_execution_cost'])==Fraction('0.24')
    assert Fraction(m['arms']['EXIT']['post_fill_open_equity'])==Fraction('979.76')
