"""Pure wiring of saved full-domain evidence; no state, search, book or IO."""
from copy import deepcopy
from fractions import Fraction
from backtest.return_priority_limit_book_v2 import combine_split_identity_events

BASIS = 'CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED'


def assemble_monthly_execution_inputs(prepared):
    sessions=prepared['session_dates']
    if len(sessions)<2 or sessions!=sorted(set(sessions)):
        raise ValueError('INVALID_EXPLICIT_CALENDAR')
    pins=deepcopy(prepared['source_hashes'])
    if 'backtest/return_priority_fresh_cash_quantity_search.py' not in pins:
        raise ValueError('MISSING_CORE_SOURCE_PIN')
    metadata=prepared['metadata'];provenance=prepared['source_provenance']
    if set(metadata)!=set(prepared['ohlc']) or set(metadata)!=set(provenance):
        raise ValueError('INCOMPLETE_SECURITY_SOURCE_DOMAIN')
    close_prices={};missing={}
    for sid,rows in prepared['ohlc'].items():
        close_prices[sid]={}
        if provenance[sid]['price_basis']!=BASIS:
            raise ValueError('UNSUPPORTED_PRICE_COORDINATE')
        if provenance[sid]['whole_source'] not in pins:
            raise ValueError('UNPINNED_PRICE_SOURCE')
        for day,bar in rows.items():
            if day not in sessions:raise ValueError('PRICE_OUTSIDE_CALENDAR')
            value=bar.get('close')
            if value is None:
                missing.setdefault(day,[]).append(sid)
                continue
            if isinstance(value,bool) or Fraction(value)<=0:
                raise ValueError('INVALID_CLOSE')
            close_prices[sid][day]=value
    monthly=[];seen=set()
    for window in prepared['windows']:
        day=window['decision_date'];args=deepcopy(window['search_arguments'])
        if day not in sessions[:-1] or day in seen or args['decision_date']!=day:
            raise ValueError('INVALID_MONTHLY_DECISION')
        seen.add(day);active=sessions[sessions.index(day)+1]
        if window.get('active_date',active)!=active:raise ValueError('WRONG_ACTIVE_SESSION')
        domain=set(args['prices'])
        if domain!=set(args['metadata']) or not domain<=set(metadata) or any(set(s)!=domain for s in args['training_scenarios']):
            raise ValueError('INCOMPLETE_SEARCH_DOMAIN')
        for sid,price in args['prices'].items():
            if sid not in close_prices or day not in close_prices[sid]:raise ValueError('MISSING_CANDIDATE_DECISION_PRICE:'+sid)
            if Fraction(price)!=Fraction(close_prices[sid][day]):raise ValueError('SEARCH_EXECUTION_PRICE_MISMATCH:'+sid)
            if args['metadata'][sid]!=metadata[sid]:raise ValueError('SEARCH_EXECUTION_IDENTITY_MISMATCH:'+sid)
        quotes=[dict(security_id=sid,ticker=metadata[sid]['ticker'],price=rows[day],as_of=day,price_basis=BASIS,
                     source_references=[provenance[sid]['whole_source']])
                for sid,rows in sorted(close_prices.items()) if day in rows]
        args.update(quote_as_of=day,price_basis=BASIS)
        monthly.append(dict(decision_date=day,active_date=active,search_arguments=args,valuation_quotes=quotes,
                            source_hashes=deepcopy(pins),missing_historical_marks=missing.get(day,[]),
                            actual_held_price_policy='MISSING_HELD_MARK_MUST_BLOCK_NO_ZERO_NO_REMOVAL'))
    if not monthly or monthly[0]['decision_date']!=sessions[0]:raise ValueError('INITIAL_SELECTION_REQUIRED')
    actions=combine_split_identity_events(split_events=prepared['split_events_reference_only'],
        identity_migrations=prepared['identity_migrations'],start_date=sessions[0],end_date=sessions[-1])
    provider_actions=deepcopy(actions)
    for event in prepared['cash_stock_merger_events']:
        provider_actions.append(dict(date=event['effective_date'],security_id=event['old_sid'],type='cash_stock_merger',source_references=deepcopy(event['source_references'])))
    return dict(session_dates=deepcopy(sessions),monthly_inputs=monthly,close_prices=close_prices,actions=actions,
        provider_actions=provider_actions,price_source_references={sid:[p['whole_source']] for sid,p in provenance.items()},
        cash_stock_merger_events=deepcopy(prepared['cash_stock_merger_events']),fractional_settlements=deepcopy(prepared['fractional_settlements']),
        missing_marks_by_date=missing,metadata=deepcopy(metadata),source_hashes=pins,search_calls=0,book_calls=0,
        limitations=['No actual state is inferred; actual held SID missing a mark must fail at decision.',
                    'Mixed merger events are separate mandatory kernel inputs, never silently dropped.',
                    'Price-only conditional coordinates; dividends not cash and no PIT certification.'])
