"""Create-only five-cutoff conditional research; no service/account mutation.

Prepare registration first; separately run its exact reviewed hash. Each stage
is saved before the next starts. Interrupted runs are never silently resumed.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import types


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'tmp/quantity_temporal_conditional_20261014_v1'
CORE = 'backtest/return_priority_fresh_cash_quantity_search.py'
LEDGER = 'backtest/return_priority_paper_continuous_book_research.py'
PANEL = 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
METADATA = 'tmp/current_conditional_metadata_proposal_20261014_v3/proposal.json'
ACCEPTED = 'tmp/latest_saved_snapshot_actual_20261014_v1/registration.json'
POLICY = 'research_contracts/return_priority_uncapped_concentration_domain_20261014.json'
USER_POLICY = 'research_contracts/user_single_stock_concentration_preference_20261014.json'
COMMISSION = 'research_contracts/user_broker_commission_confirmation_20261014.json'
PINS = {
    CORE: '756a16a83735279db24332d096aa149b54fc7ff4e91cb807410b3f33f425b588',
    LEDGER: 'a60eb8602d42ec35b973c0d54097cf47aa186c6f8c56a80b08b3f39ced2184e3',
    PANEL: '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822',
    METADATA: 'e61c04aaec6f2f7b477eb7a83c9b882305c7e0449ec60fae85c5e8c01f51d92c',
    ACCEPTED: '05efcc02c4bc6da4f45783c536776cf721527fd3042e3b87374e981e4a2e0ba7',
    POLICY: '462e87664e87e5a37b179fc514e155009ce522b35686426677c84c0638c142ad',
    USER_POLICY: 'd9d342481221228dc93d3e9a2cd246261fae33b66811f7de381015ceae01645c',
    COMMISSION: '0fb4622cac5dec9a60c0a6d351ee6f1df430dc5904442d5417fc9580fd5e3d6f',
}
DECISIONS = ['2026-05-20', '2026-06-22', '2026-07-22', '2026-08-20', '2026-09-21']
ENDS = DECISIONS[1:] + ['2026-10-12']
PROTECTED = ['data/state.json', 'data/broker_positions.json', 'config/config.yaml',
             'api/server.py', 'web/index.html', 'web/selected_stock_charts.js',
             'data/current_cash_portfolio_research.py']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    with path.open('xb') as stream:
        stream.write(raw)
    return digest(raw)


def load_sources():
    sources = {}
    for relative, expected in PINS.items():
        raw = (ROOT / relative).read_bytes()
        require(digest(raw) == expected, 'Source pin mismatch: '+relative)
        sources[relative] = raw
    return sources


def guards():
    return {relative: digest((ROOT / relative).read_bytes()) for relative in PROTECTED}


def prepare():
    require(not OUTPUT.exists(), 'Create-only output already exists')
    load_sources()
    registration = dict(schema='QUANTITY_TEMPORAL_CONDITIONAL_REGISTRATION_V1',
                        runner_sha256=digest(Path(__file__).read_bytes()), source_pins=PINS,
                        decisions=DECISIONS, outcome_ends=ENDS, max_search_calls=5,
                        max_book_calls=15, max_book_calls_per_cutoff=3,
                        objective_evaluations_per_cutoff=8192,
                        fixed_seed='fresh-quantity-20261014-v1', entered_cash=20000,
                        fee_bps=0, minimum_cash_buffer=0, scenario_count=12,
                        intervals_per_scenario=21, protected_before=guards(),
                        conditional_current_accepted_metadata_retrospective=True,
                        point_in_time_verified=False, independent_oos=False,
                        price_returns_not_total_returns=True, current_service_changed=False,
                        no_continuous_nav_or_cagr=True, no_reselection_using_outcome=True,
                        other_charges_included=False, dividend_accounting_verified=False)
    OUTPUT.mkdir()
    print(json.dumps({'registration': str(OUTPUT / 'registration.json'),
                      'sha256': save(OUTPUT / 'registration.json', registration)}))


def module(raw, name):
    value = types.ModuleType(name)
    exec(compile(raw, name, 'exec'), value.__dict__)
    return value


def inputs_at(panel, proposal, accepted, decision):
    calendar = panel['calendar']
    end = calendar.index(decision)
    require(end >= 252, 'Insufficient common calendar')
    boundary_indices = list(range(end-252, end+1, 21))
    channels = {row['ticker']: row for row in panel['stocks']}
    proposed = {row['ticker']: row for row in proposal['proposed_metadata']}
    prices, metadata, risk_metadata, gross, exclusions = {}, {}, {}, {}, []
    for ticker in accepted:
        row = proposed[ticker]
        values = channels[ticker]['values']
        require(len(values) == len(calendar), 'Calendar alignment differs')
        # Only the mature 253 closes are touched here. Future Open/Close enters
        # a separate outcome call after the search result has been saved.
        history = [values[index][3] for index in range(end-252, end+1)]
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in history):
            exclusions.append(dict(ticker=ticker, security_id=row['security_id'], reason='INCOMPLETE_MATURE_253_CLOSE_HISTORY'))
            continue
        sid = row['security_id']
        require(sid not in metadata, 'Duplicate accepted SID')
        prices[sid] = str(Fraction(str(history[-1])))
        metadata[sid] = {key: row[key] for key in ('ticker', 'issuer_id')}
        risk_metadata[sid] = {key: row[key] for key in ('ticker', 'issuer_id', 'risk_chain')}
        gross[sid] = [str(Fraction(str(history[(index+1)*21])) / Fraction(str(history[index*21]))) for index in range(12)]
    require(metadata, 'No eligible mature history')
    args = dict(prices=prices, metadata=metadata, entered_cash=20000, fee_bps=0, minimum_cash_buffer=0,
                training_scenarios=[{sid: values[index] for sid, values in gross.items()} for index in range(12)],
                scenario_dates=[calendar[index] for index in boundary_indices[1:]], decision_date=decision,
                max_objective_evaluations=8192, fixed_seed='fresh-quantity-20261014-v1')
    return dict(search_arguments=args, ledger_metadata=risk_metadata, exclusions=exclusions,
                accepted_count=len(accepted), eligible_count=len(metadata),
                scenario_start_dates=[calendar[index] for index in boundary_indices[:-1]],
                current_metadata_retroactive_conditional_not_pit=True,
                price_basis=panel['price_basis'], source_pins=PINS)


def outcome(*, panel, ledger, metadata, weights, decision, end, policy, name, directory):
    if not weights:
        result = dict(status='ALL_CASH_NO_BOOK', proposed_k=0, executed_k=0,
                      net_return='0', drawdown='0', final_equity='20000', book_calls=0)
        save(directory / (name+'_outcome.json'), result)
        return result
    calendar = panel['calendar']
    first, last = calendar.index(decision), calendar.index(end)
    require(last > first, 'Outcome needs a next Open')
    channels = {row['ticker']: row for row in panel['stocks']+panel['controls']}
    dates = calendar[first:last+1]
    opens = {day: {sid: channels[row['ticker']]['values'][first+i][0] for sid, row in metadata.items()}
             for i, day in enumerate(dates)}
    closes = {day: {sid: channels[row['ticker']]['values'][first+i][3] for sid, row in metadata.items()}
              for i, day in enumerate(dates)}
    save(directory / (name+'_book_intent.json'), dict(decision=decision, end=end, target_weights=weights,
                                                    maximum_calls=1, reference_only=name != 'strategy'))
    book = ledger.simulate_paper_book(calendar=dates, open_prices=opens, close_prices=closes,
        metadata=metadata, initial_shares={}, initial_cash=20000, fee_bps=0, minimum_cash_buffer=0,
        decisions=[dict(id=name+':'+decision, decision_date=decision, target_weights=weights)], cash_events=[],
        risk_parameters=policy, enforce_initial_target_risk=False,
        declared_price_basis='CONDITIONAL_PROVIDER_OHLC_PRICE_RETURN_NOT_TOTAL_RETURN')
    # Disabling the old nonempty-target gate permits all proposed small lots to
    # floor to zero; no concentration constraint is weakened in this new domain.
    save(directory / (name+'_book.json'), book)
    executed = book['executions'][0]['target_shares'] if book['executions'] and book['executions'][0]['status']=='COMMITTED_SELLS_THEN_BUYS' else None
    result = dict(status=book['status'], reason=book['reason'], proposed_k=len(weights),
                  executed_k=None if executed is None else len(executed), executed_quantities=executed,
                  dropped_by_next_open_floor=None if executed is None else sorted(set(weights)-set(executed)),
                  book_calls=1, reference_only=name != 'strategy', net_return=None, drawdown=None,
                  no_liquidation_fee=True, dividends_included=False)
    if book['status']=='COMPLETE_CONDITIONAL_PAPER_BOOK':
        require(all(row['daily_risk']['all_passed'] is True or row['daily_risk']['status']=='NO_STOCK_HOLDINGS'
                    for row in book['daily_rows']), 'Uncapped-domain diagnostics failed')
        values = [Fraction(20000)]+[Fraction(row['close_equity']) for row in book['daily_rows']]
        peak, drawdown = values[0], Fraction(0)
        for value in values:
            peak = max(peak, value); drawdown = max(drawdown, 1-value/peak)
        result.update(net_return=str(values[-1]/20000-1), drawdown=str(drawdown), final_equity=str(values[-1]))
    save(directory / (name+'_outcome.json'), result)
    return result


def run(registration_sha):
    registration_raw = (OUTPUT / 'registration.json').read_bytes()
    require(digest(registration_raw)==registration_sha, 'Registration hash mismatch')
    registration = json.loads(registration_raw)
    require(registration['runner_sha256']==digest(Path(__file__).read_bytes()) and registration['source_pins']==PINS,
            'Reviewed runner/source binding differs')
    require({path.name for path in OUTPUT.iterdir()}=={'registration.json'}, 'Already started; inspect saved stages, do not blindly rerun')
    require(guards()==registration['protected_before'], 'Protected files changed after registration')
    sources = load_sources()
    core, ledger = module(sources[CORE], 'pinned_quantity_core'), module(sources[LEDGER], 'pinned_temporal_ledger')
    panel, proposal, accepted_source, policy_source = [json.loads(sources[path]) for path in (PANEL, METADATA, ACCEPTED, POLICY)]
    accepted = accepted_source['accepted_current_conditional_tickers']
    require(len(accepted)==len(set(accepted))==84, 'Original accepted84 list required')
    policy = {key: float(Fraction(value)) for key, value in policy_source['risk_parameters'].items()}
    require(policy==dict(min_single_weight=0, max_single_weight=1, top_three_cap=1, min_neff_ratio=0, chain_cap=1), 'New uncapped domain required')
    summary = []
    save(OUTPUT / 'started.json', dict(registration_sha256=registration_sha, maximum_search_calls=5, maximum_book_calls=15))
    try:
        for decision, end in zip(DECISIONS, ENDS):
            directory = OUTPUT / decision
            directory.mkdir()
            inputs = inputs_at(panel, proposal, accepted, decision)
            save(directory / 'inputs.json', inputs)
            save(directory / 'search_intent.json', dict(maximum_calls=1, objective_evaluation_limit=8192))
            search = core.search_fresh_cash_quantities(**inputs['search_arguments'])
            save(directory / 'search.json', search)
            require(search['selected'] is not None, 'Search did not produce a candidate')
            selected = search['selected']
            weights = selected['actual_weights']
            frozen = dict(target_weights=weights, residual_cash_weight=selected['cash_fraction'],
                          proposed_k=selected['actual_k'], selection_frozen_before_outcome=True)
            save(directory / 'frozen_execution_target.json', frozen)
            selected_metadata = {sid: inputs['ledger_metadata'][sid] for sid in weights}
            result = dict(decision=decision, end=end, strategy=outcome(panel=panel, ledger=ledger,
                metadata=selected_metadata, weights=weights, decision=decision, end=end, policy=policy,
                name='strategy', directory=directory), references={})
            for ticker in ('QQQ', 'SPY'):
                # Reference ticker keys are local ledger coordinates, not new
                # securities admitted to the candidate metadata pool.
                result['references'][ticker] = outcome(panel=panel, ledger=ledger,
                    metadata={ticker: dict(ticker=ticker, issuer_id=ticker, risk_chain='REFERENCE_FUND')},
                    weights={ticker: '1'}, decision=decision, end=end, policy=policy, name=ticker, directory=directory)
            save(directory / 'outcome.json', result)
            summary.append(result)
        save(OUTPUT / 'result.json', dict(status='COMPLETE_CONDITIONAL_TEMPORAL_RESEARCH', windows=summary,
             search_calls=5, book_calls=sum(row['strategy']['book_calls']+sum(ref['book_calls'] for ref in row['references'].values()) for row in summary),
             independent_fresh_cash_windows=True, continuous_nav=False, cagr=None, independent_oos=False,
             retrospective_current_metadata_not_pit=True, price_return_not_total_return=True,
             new_winner_selected=False, current_service_changed=False, source_pins=PINS))
    except Exception as error:
        save(OUTPUT / 'failure.json', dict(error_type=type(error).__name__, message=str(error),
                                         completed_windows=len(summary), automatic_retry_allowed=False))
        raise
    finally:
        after = guards()
        save(OUTPUT / 'protected_after.json', dict(hashes=after, unchanged=after==registration['protected_before']))
        require(after==registration['protected_before'], 'Protected files changed during research')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--run', action='store_true')
    parser.add_argument('--registration-sha')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        require(args.registration_sha is not None, 'Explicit reviewed registration SHA required')
        run(args.registration_sha)
