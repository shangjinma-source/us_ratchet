"""Join saved candidate continuous holdings to original Close columns by SID."""
from backtest import ndx_saved_holdings_risk_diagnostic_research as diagnostic


def project_path(*, stateful_input, daily):
    require = diagnostic.require
    calendar = stateful_input['calendar']
    require(type(calendar) is list and len(calendar) == 120 and calendar == sorted(set(calendar)),
            'Complete original 120-session calendar')
    for session in calendar:
        diagnostic.session_date(session)
    require(type(daily) is list and [day['session'] for day in daily] == calendar,
            'Complete saved daily sequence')
    closes = stateful_input['closes']
    require(closes['index'] == calendar, 'Original Close calendar')
    columns, data = closes['columns'], closes['data']
    require(type(columns) is list and len(columns) == len(set(columns)), 'Unique Close columns')
    require(type(data) is list and len(data) == 120 and
            all(type(row) is list and len(row) == len(columns) for row in data), 'Full original Close matrix')
    aliases = stateful_input['internal_columns_by_security']
    require(type(aliases) is dict and len(set(aliases.values())) == len(aliases), 'Unique SID aliases')
    require(set(aliases.values()) == set(columns), 'Exact original alias/Close column coverage')
    positions = {sid: columns.index(alias) for sid, alias in aliases.items()}
    observations = stateful_input['risk_chains_by_decision']
    rows = []
    for index, day in enumerate(daily):
        require('risk' not in day, 'Do not overwrite or relabel an original saved risk')
        holdings = day['holdings']
        require(type(holdings) is dict and set(holdings) <= set(aliases), 'Saved holdings resolve by SID')
        shares, prices, pointers = {}, {}, {}
        labels = diagnostic.latest_labels(session=calendar[index], security_ids=list(holdings), observations=observations)
        for sid, holding in holdings.items():
            require(holding['ticker'] == aliases[sid], 'Original internal holding alias')
            shares[sid] = holding['shares']
            prices[sid] = data[index][positions[sid]]
            # Use token arrays instead of unescaped JSON Pointer strings: SIDs
            # may legally contain slash or tilde characters.
            pointers[sid] = dict(
                quantity_tokens=['daily', index, 'holdings', sid, 'shares'],
                price_tokens=['closes', 'data', index, positions[sid]],
                label_tokens=['risk_chains_by_decision', labels[sid]['observation_session'], sid])
        rows.append(dict(diagnostic=diagnostic.derive_daily_diagnostic(
            session=calendar[index], shares=shares, close_prices=prices, labels=labels),
            source_locator_tokens=pointers, daily_index=index))
    return dict(schema='CANDIDATE_CONTINUOUS_SAVED_DAILY_RISK_PROJECTION_V1', rows=rows,
                path_day_count=len(rows), source_bytes_authenticated=False,
                account_executed=False, original_saved_risk=False, order_gate_evaluated=False,
                point_in_time_verified=False, promotion_allowed=False)
