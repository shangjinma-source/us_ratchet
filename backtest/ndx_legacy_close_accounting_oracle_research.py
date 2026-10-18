"""Independent Decimal ledger for the legacy same-Close whole-share contract."""
from decimal import Decimal,localcontext,ROUND_FLOOR


def number(value):
    if type(value) not in (int,float,str,Decimal):raise ValueError('Explicit finite number required')
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Finite number required')
    return result


def account(*,dates,prices,schedule,risk_chains,contract):
    """prices: ticker -> same-length closes; schedule: date -> target weights."""
    if not dates or dates!=sorted(set(dates)) or not schedule or not set(schedule)<=set(dates):raise ValueError('Unique ordered calendar and schedule required')
    tickers=sorted(prices)
    if not tickers or any(set(w)!=set(tickers) for w in schedule.values()):raise ValueError('Constant complete ticker coordinate required')
    if set(risk_chains)!=set(tickers) or any(not c for c in risk_chains.values()):raise ValueError('Complete risk-chain coordinate required')
    panel={t:[number(x) for x in prices[t]] for t in tickers}
    if any(len(v)!=len(dates) or min(v)<=0 for v in panel.values()):raise ValueError('Complete positive Close panel required')
    with localcontext() as context:
        context.prec=40
        cash=number(contract['portfolio_cash_usd']);initial=cash;buffer=number(contract['minimum_cash_buffer_usd'])
        rate=number(contract['transaction_cost_bps'])/10000;tolerance=Decimal('1e-9')
        if not 0<=buffer<cash or rate<0:raise ValueError('Valid cash/fee contract required')
        quantities={t:0 for t in tickers};daily=[];trades=[];fees_total=Decimal(0);traded_total=Decimal(0);changes_total=0
        all_risk=True;minimum_cash=cash;peak=None;max_dd=Decimal(0);first_shares=None
        def positions_text():return ';'.join(f'{t}:{quantities[t]}' for t in tickers)
        def risk(marks):
            values={t:marks[t]*quantities[t] for t in tickers};stock=sum(values.values())
            if stock<=0:return dict(top1=1.,top3=1.,effective_n=0.,risk_chain_top1=1.,minimum_weight=0.,constraints_passed=False)
            weights={t:v/stock for t,v in values.items()};ordered=sorted(weights.values(),reverse=True)
            effective=1/sum(w*w for w in weights.values());chains={}
            for t,w in weights.items():chains[risk_chains[t]]=chains.get(risk_chains[t],Decimal(0))+w
            checks=[ordered[0]<=number(contract['max_single_weight'])+tolerance,
                    ordered[-1]>=number(contract['min_single_weight'])-tolerance,
                    sum(ordered[:3])<=number(contract['top_weight_cap'])+tolerance,
                    effective>=number(contract['minimum_effective_n_ratio'])*len(tickers)-tolerance,
                    max(chains.values())<=number(contract['risk_chain_top1_cap'])+tolerance]
            return dict(top1=float(ordered[0]),top3=float(sum(ordered[:3])),effective_n=float(effective),risk_chain_top1=float(max(chains.values())),
                        minimum_weight=float(ordered[-1]),constraints_passed=all(checks),checks=checks)
        for i,date in enumerate(dates):
            marks={t:panel[t][i] for t in tickers}
            if date in schedule:
                weights={t:number(schedule[date][t]) for t in tickers}
                if min(weights.values())<=0:raise ValueError('Positive target weights required')
                mass=sum(weights.values());weights={t:w/mass for t,w in weights.items()}
                equity=cash+sum(marks[t]*quantities[t] for t in tickers)
                budget=max(Decimal(0),equity-buffer)
                desired={t:int((budget*weights[t]/marks[t]).to_integral_value(rounding=ROUND_FLOOR)) for t in tickers}
                def transaction():
                    buys=sum(max(0,desired[t]-quantities[t])*marks[t] for t in tickers)
                    sells=sum(max(0,quantities[t]-desired[t])*marks[t] for t in tickers)
                    fees=(buys+sells)*rate
                    return cash+sells-buys-fees,buys+sells,fees
                after,traded,fees=transaction();trimmed=[]
                while after<buffer-tolerance:
                    eligible=[t for t in tickers if desired[t]>quantities[t]]
                    if not eligible:raise ValueError('No purchasable share can preserve cash buffer')
                    trim=max(eligible,key=lambda t:(marks[t],t));desired[trim]-=1;trimmed.append(trim)
                    after,traded,fees=transaction()
                changes=sum(quantities[t]!=desired[t] for t in tickers);quantities=desired;cash=after
                fees_total+=fees;traded_total+=traded;changes_total+=changes
                if first_shares is None:first_shares=positions_text()
                trades.append(dict(date=date,pretrade_equity=float(equity),posttrade_cash=float(cash),traded_notional=float(traded),fees=float(fees),
                                   shares=dict(quantities),changed_ticker_count=changes,fee_buffer_trimmed_tickers=trimmed,risk=risk(marks)))
            snapshot=risk(marks);all_risk&=snapshot['constraints_passed'];minimum_cash=min(minimum_cash,cash)
            value=cash+sum(quantities[t]*marks[t] for t in tickers)
            peak=value if peak is None else max(peak,value);max_dd=max(max_dd,1-value/peak)
            daily.append(dict(date=date,cash=float(cash),shares=dict(quantities),value=float(value),drawdown=float(1-value/peak),risk=snapshot))
        summary=dict(whole_lot_rebalance_count=len(trades),whole_lot_initial_shares=first_shares,whole_lot_terminal_shares=positions_text(),
            whole_lot_share_change_count=changes_total,whole_lot_total_trade_notional_usd=float(traded_total),whole_lot_total_transaction_cost_usd=float(fees_total),
            whole_lot_min_cash_usd=float(minimum_cash),whole_lot_cash_buffer_preserved=minimum_cash>=buffer-tolerance,
            whole_lot_constraints_preserved_all_days=all_risk,whole_lot_terminal_value_usd=float(value),whole_lot_path_return_net=float(value/initial-1),
            whole_lot_path_max_drawdown=float(max_dd),whole_lot_execution_mode='CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES')
        return dict(summary=summary,daily=daily,trades=trades,uses_initial_cash_in_drawdown_peak=False,
                    same_close_legacy_model=True,dynamic_next_open_execution_validated=False)
