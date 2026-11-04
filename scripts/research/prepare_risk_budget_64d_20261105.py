"""Compile fixed V27 target gross daily returns only. No account replay or selection."""
import json
import hashlib
from fractions import Fraction as F
from pathlib import Path
from inventory_risk_budget_64d_20261105 import ROOT, read, PINS, day


def main():
    inventory = read('tmp/risk_budget_64d_inventory_20261105/inventory.json')
    supplement = read('tmp/risk_budget_64d_inventory_20261105/bounded_supplement.json')
    frozen_path = 'research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json'
    frozen = read(frozen_path)['base_file_dependencies']
    def verify(expected):
        for name, digest in expected.items():
            actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            if actual != digest:
                raise ValueError('SOURCE_PIN_MISMATCH:' + name)
            PINS[name] = actual
    verify(inventory['source_hashes'])
    verify(supplement['source_hashes'])
    frozen_required = [
        'tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin',
        'data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin',
        'tmp/recent_continuous_baseline_20261026_v7/execution_inputs.json',
        'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json',
        'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json',
        'tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json',
        'tmp/old_continuous_baseline_20261026_v9/book.json']
    verify({name: frozen[name] for name in frozen_required})
    extra = {(e['ticker'], e['ex_date']): e for e in supplement['events']}
    absence = {e['ticker']: e for e in supplement['absence_reviews']}
    qprices, qdiv = {}, {}
    for path in ('tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin', 'data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
        body = read(path)['chart']['result'][0]
        for index, stamp in enumerate(body['timestamp']):
            close = body['indicators']['quote'][0]['close'][index]
            if close is not None:
                date = day(stamp)
                value = F(str(close))
                if date in qprices:
                    assert qprices[date] == value, ('QQQ_OVERLAP_CLOSE_MISMATCH', date)
                qprices[date] = value
        for event in body.get('events', {}).get('dividends', {}).values():
            date = day(event['date'])
            value = F(str(event['amount']))
            if date in qdiv:
                assert qdiv[date] == value, ('QQQ_OVERLAP_DIVIDEND_MISMATCH', date)
            qdiv[date] = value
    output = []
    all_checks = []
    for label, base, prepared in (
        ('early', 'tmp/recent_continuous_baseline_20261026_v7', 'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'),
        ('later', 'tmp/old_continuous_baseline_20261026_v9', 'tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')):
        book = read(base + '/book.json')
        inputs = read(base + '/execution_inputs.json')
        audits = {}
        for index, audit in enumerate(book['provider_audit']):
            decision = audit.get('target_decision_date')
            if decision and decision not in audits and 'monthly_ceiling' in audit:
                audits[decision] = (index, audit)
        for outer in read(prepared)['windows']:
            window = outer.get('window', outer)
            decision = window.get('decision_cutoff', window.get('decision_date'))
            index, audit = audits[decision]
            inv = next(r for r in inventory['rows'] if r['window'] == label and r['decision'] == decision)
            dates = window['training_dates'][-64:]
            candidates = {c['security_id']: c for c in window['candidates'] if c.get('security_id')}
            targets = {s: q for s, q in audit['monthly_ceiling'].items() if q > 0}
            stock_returns, prices, checks, blockers = {}, {}, [], []
            for sid in targets:
                candidate = candidates[sid]
                row = next(r for r in inv['target_stocks'] if r['security_id'] == sid)
                ticker = candidate['ticker']
                source = candidate['training_source'].replace('\\', '/')
                # Preserve provenance hash even for CSV source; no new download.
                PINS[source] = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
                closes = dict(zip(dates, map(F, candidate['training_close'][-64:])))
                anchor_price = F(candidate['decision_cost'])
                coordinate_factor = anchor_price / closes[decision]
                prices[sid] = str(anchor_price)
                dividends = {}
                splits = {}
                for event in row['events']:
                    if event['kind'] == 'splits':
                        assert event['training_coordinate'], (ticker, 'unreviewed split')
                        payload = event['payload']
                        splits[event['date']] = F(str(payload['numerator'])) / F(str(payload['denominator']))
                for gap in row['gaps']:
                    if gap.startswith('UNMAPPED_LOOKBACK_DIVIDEND:') and (ticker, gap.split(':', 1)[1]) in extra:
                        continue
                    if gap.startswith('SOURCE_EVENT_STREAM_NOT_JSON_CHART:') and ticker in absence:
                        review = absence[ticker]
                        assert review['start_exclusive'] <= dates[0] and review['end_inclusive'] >= decision
                        continue
                    blockers.append(ticker + ':' + gap)
                for event in row['events']:
                    if event['kind'] != 'dividends':
                        continue
                    ex = event['date']
                    terms = extra.get((ticker, ex)) or event.get('existing_dividend')
                    if not terms:
                        blockers.append(ticker + ':MISSING_DIVIDEND_TERMS:' + ex)
                        continue
                    terms = terms.get('event', terms)
                    assert ex <= decision
                    if terms.get('declaration_date'):
                        assert terms['declaration_date'] <= ex <= decision
                    divisor = coordinate_factor
                    for split_date, ratio in splits.items():
                        if ex < split_date <= decision:
                            divisor *= ratio
                    amount = F(terms['amount_per_share']) / divisor
                    dividends[ex] = amount
                    checks.append(dict(ticker=ticker, ex_date=ex, nominal_amount=terms['amount_per_share'],
                                       coordinate_divisor=str(divisor), adjusted_dividend=str(amount),
                                       arithmetic_check=str(amount * divisor), terms=terms))
                returns = {}
                for previous, current in zip(dates, dates[1:]):
                    returns[current] = str((closes[current] + dividends.get(current, F(0))) / closes[previous])
                    # Algebraic unit reconstruction, NOT independent source verification:
                    # event-day nominal close and prior-day
                    # nominal close are related by actual shares from any intervening split.
                    prior_factor, current_factor = coordinate_factor, coordinate_factor
                    for split_date, ratio in splits.items():
                        if previous < split_date <= decision:
                            prior_factor *= ratio
                        if current < split_date <= decision:
                            current_factor *= ratio
                    previous_nominal = closes[previous] * prior_factor
                    current_nominal = closes[current] * current_factor
                    shares_ratio = prior_factor / current_factor
                    nominal_dividend = dividends.get(current, F(0)) * current_factor
                    independent = shares_ratio * (current_nominal + nominal_dividend) / previous_nominal
                    assert independent == F(returns[current])
                stock_returns[sid] = returns
            qreturns = {current: str((qprices[current] + qdiv.get(current, F(0))) / qprices[previous])
                        for previous, current in zip(dates, dates[1:])}
            args = dict(target_quantities=targets, decision_prices=prices, tradable_equity=str(audit['investable_equity_at_reset']),
                        stock_gross_returns=stock_returns, qqq_gross_returns=qreturns, decision_date=decision)
            assert len(qreturns) == 63 and all(len(r) == 63 and set(r) == set(qreturns) for r in stock_returns.values())
            assert sum(F(prices[s]) * q for s, q in targets.items()) <= F(args['tradable_equity'])
            output.append(dict(window=label, decision_date=decision, status='BLOCKED' if blockers else 'CONDITIONAL_INPUT_READY',
                               blockers=blockers, arguments=args, source_binding=dict(book_path=base + '/book.json',
                               book_sha256=PINS[base + '/book.json'], provider_audit_index=index,
                               target_decision_date=audit['target_decision_date'],
                               rerank_decision_id=audit['selection'].get('rerank_decision_id')), dividend_checks=checks))
            all_checks.extend(checks)
    result = dict(schema='FIXED_ACTUAL_V27_TARGET_GROSS_RISK_INPUTS', windows=output, dividend_checks=all_checks,
                  source_hashes=PINS, verified_expected_pin_sources=['inventory.source_hashes','supplement.source_hashes',frozen_path],
                  unit_check_scope='Algebraic identity using same training closes and coordinate factor, not independent price verification',
                  economic_runs=0, variance_or_scaling_calculated=False,
                  scope='63 daily gross ex-dividend accrued returns; not tradable cash arrival or a reinvested account. Both QQQ/stocks same formula. Conditional historical source and retrospective no-action review retained. Future actual targets require new coverage gate.')
    path = ROOT / 'tmp/risk_budget_64d_inventory_20261105/risk_inputs.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(windows=len(output), ready=sum(r['status'] == 'CONDITIONAL_INPUT_READY' for r in output), dividend_checks=len(all_checks))))

if __name__ == '__main__':
    main()
