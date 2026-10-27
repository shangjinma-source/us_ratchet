"""Offline fixed five-document, 20-session case inventories; NOT a backtest.

Initial wealth is the recorded baseline close before the conservative disclosure
time. All five local accession times are after 16:00 New York on a session date.
No original publication-time certification is inferred from this metadata join.
Future baseline selections are comparison observations, never branch decisions.
"""
import argparse
from datetime import datetime, time
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

CASES = [('MRNA_Q2','MRNA','2021-06-30','mrna_review.json'),
         ('MRNA_Q3','MRNA','2021-09-30','mrna_review.json'),
         ('NVDA_Q3_2023','NVDA','2023-10-29','nvda_review.json'),
         ('NVDA_Q3_2024','NVDA','2024-10-27','nvda_review.json'),
         ('APP_Q3','APP','2025-09-30','app_review.json')]


def build(root, source, output):
    pins = {}
    def read(path):
        raw = path.read_bytes()
        pins[str(path.relative_to(root))] = sha256(raw).hexdigest()
        return json.loads(raw)
    catalogue = read(source/'catalogue.json')
    cache, results = {}, []
    output.mkdir(parents=True, exist_ok=True)
    for name, ticker, end, review_file in CASES:
        rows = [r for r in catalogue['rows'] if r['ticker'] == ticker and r['current_period']['end'] == end]
        if len(rows) != 1:
            raise ValueError('UNIQUE_CATALOGUE_CASE_REQUIRED')
        row = rows[0]
        review = read(source/review_file)
        original = source/(name+'.bin')
        pins[str(original.relative_to(root))] = sha256(original.read_bytes()).hexdigest()
        window = row['window']
        if window not in cache:
            directory = root/'tmp'/window
            book = read(directory/'book.json')
            inputs = read(directory/'execution_inputs.json')
            proof = read(directory/'independent_prefix_review.json')
            if book['status'] != 'COMPLETE':
                raise ValueError('COMPLETE_BASELINE_REQUIRED')
            cache[window] = book, inputs, proof
        book, inputs, proof = cache[window]
        sessions = inputs['assembled']['session_dates']
        available = datetime.fromisoformat(row['acceptanceDateTime'].replace('Z','+00:00'))
        local = available.astimezone(ZoneInfo('America/New_York'))
        initial = local.date().isoformat()
        if local.time() <= time(16) or initial not in sessions:
            raise ValueError('FIXED_CASE_AFTER_REGULAR_CLOSE_BINDING_REQUIRED')
        index = sessions.index(initial)
        subsequent = sessions[index+1:index+21]
        ledger = [x for x in book['daily_ledger'] if x['date'] == initial]
        if len(ledger) != 1:
            raise ValueError('UNIQUE_INITIAL_CLOSE_REQUIRED')
        audits = dict(zip(sessions[:-1], book['provider_audit']))
        state = ledger[0]
        stop = subsequent[-1] if subsequent else initial
        dates = [initial, *subsequent]
        pending = any(state.get(k) for k in ('distribution_rights','merger_entitlements'))
        pending |= state.get('valuation_phase') != 'REGULAR_CLOSE'
        pending |= any(str(state.get(k,'0')) != '0' for k in ('receivable','dividend_receivable','nontradable_entitlement_value'))
        case = dict(schema='FIXED_LOCAL_NEWS_CASE_INPUTS_V1', case=name, ticker=ticker,
            security_id=row['security_id'], accession=row['accession'], window=window,
            action='NO_ACTION', action_reason='NO_INDEPENDENTLY_ADMITTED_FIXED_EVENT_ACTION; original reports retain specific facts but not trade authorization',
            report_review=review_file, report_review_conclusion=review.get('conclusion',review.get('candidate',review.get('status'))),
            metadata_availability=row['acceptanceDateTime'], availability_binding='CATALOGUE_ACCESSION_PROXY_ONLY_NOT_ORIGINAL_PUBLICATION_CERTIFIED',
            initial_date=initial, initial_baseline_ledger=state,
            initial_risk_state_before_close=audits[sessions[index-1]].get('risk_overlay',{}).get('state') if index else None,
            initial_close_baseline_audit=audits.get(initial),
            first_news_decision_close=subsequent[0] if subsequent else None,
            first_news_execution_open=subsequent[1] if len(subsequent)>1 else None,
            requested_following_sessions=20, actual_following_sessions=len(subsequent),
            window_status='COMPLETE_20_SESSION_INPUTS' if len(subsequent)==20 else 'SHORT_BASELINE_TAIL',
            session_dates=dates, initialization_requires_entitlement_reconstruction=bool(pending),
            local_replay_initialization_status='BLOCKED_INITIAL_ENTITLEMENTS' if pending else 'CASH_AND_INTEGER_SHARES_INITIALIZATION_AVAILABLE',
            comparison_design='FIXED_RECORDED_BASELINE_EFFECTIVE_TARGET_PATH_ATTRIBUTION_ONLY_NOT_BRANCH_REOPTIMIZATION',
            ohlc={sid:{d:bar for d,bar in bars.items() if d in dates} for sid,bars in inputs['ohlc'].items()},
            close_prices={sid:{d:v for d,v in prices.items() if d in dates} for sid,prices in inputs['assembled']['close_prices'].items()},
            baseline_comparison_ledger=[x for x in book['daily_ledger'] if initial < x['date'] <= stop],
            baseline_audits=[dict(decision_date=d,audit=audits[d]) for d in dates[:-1]],
            fixed_effective_target_path=[dict(decision_date=d,active_date=sessions[sessions.index(d)+1],
                target_shares=audits[d]['target_shares'],
                risk_effective_target=audits[d].get('risk_overlay',{}).get('effective_target_quantities'),
                action=audits[d]['action'],monthly_ceiling=audits[d].get('monthly_ceiling'),
                original_orders=audits[d]['orders']) for d in dates[:-1]],
            monthly_reset_dates=[x['decision_date'] for x in inputs['assembled']['monthly_inputs'] if initial <= x['decision_date'] < stop],
            corporate_action_inputs={k:inputs['assembled'].get(k) for k in ['actions','provider_actions','cash_stock_merger_events','distribution_events','fractional_settlements','distribution_fractional_cash_values','price_source_references']},
            dividend_events=inputs.get('dividend_events',[]),
            baseline_review_status=proof.get('status'),
            limitations=['Inputs only; no economic result or branch executed.',
              'A replay of the fixed recorded target path is an attribution comparison, not the original selection algorithm on changed branch wealth.',
              'Keep baseline current monthly ceiling and original risk state; never start a new selection at arbitrary event date.',
              'At subsequent monthly reset recompute selection using branch real cash and shares; baseline future target is not branch proof.',
              'Company actions and dividend entitlement require original kernel chronology; pending rights must not be dropped.',
              'Window fixed at 20 sessions before reading outcomes; no annualization from short cases.'])
        path = output/(name+'.json')
        path.write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding='utf-8')
        results.append(dict(case=name,path=str(path.relative_to(root)),sha256=sha256(path.read_bytes()).hexdigest(),
                            initial_date=initial,first_decision=case['first_news_decision_close'],last_date=stop,
                            sessions=len(subsequent),action='NO_ACTION',pending_rights=bool(pending)))
    manifest=dict(schema='FIXED_LOCAL_NEWS_CASE_MANIFEST_V1',case_count=5,window_policy='NEXT_20_BASELINE_SESSIONS_AFTER_PRE_EVENT_CLOSE',
                  cases=results,source_hashes=pins,economic_run=False,network_calls=0,model_calls=0)
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='.')
    parser.add_argument('--source',default='tmp/news_fixed26_20261027')
    parser.add_argument('--output',default='tmp/local_news_cases_20261027')
    args=parser.parse_args()
    root=Path(args.root).resolve()
    result=build(root,root/args.source,root/args.output)
    print(json.dumps(result['cases'],ensure_ascii=False))
