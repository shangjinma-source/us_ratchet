"""Check saved daily training arrays against existing monthly execution inputs."""
import argparse
from datetime import date
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path


def check_series(dates, values, decision_date, expected_gross, price):
    if (len(dates) != 253 or len(values) != 253 or dates != sorted(set(dates)) or
            dates[-1] != decision_date or any(date.fromisoformat(day).isoformat() != day for day in dates)):
        raise ValueError('COMPLETE_ORDERED_TRAINING_WINDOW_REQUIRED')
    values = [F(value) for value in values]
    if any(value <= 0 for value in values):
        raise ValueError('POSITIVE_TRAINING_PRICE_REQUIRED')
    if F(price) <= 0:
        raise ValueError('POSITIVE_DECISION_PRICE_REQUIRED')
    if [values[i + 21] / values[i] for i in range(0, 252, 21)] != [F(value) for value in expected_gross]:
        raise ValueError('TRAINING_SCENARIOS_MISMATCH')
    return values[-1] / F(price)


def review(prepared, assembled, last_date):
    windows = {window['decision_date']: window for window in prepared['windows']}
    if len(windows) != len(prepared['windows']):
        raise ValueError('DUPLICATE_PREPARED_DATE')
    rows = []
    verified = {}
    for monthly in assembled['monthly_inputs']:
        day = monthly['decision_date']
        if day > last_date:
            continue
        window = windows[day]
        dates = window['training_dates']
        arguments = monthly['search_arguments']
        if arguments['decision_date'] != day or arguments['scenario_dates'] != dates[21::21]:
            raise ValueError('MONTHLY_DATE_BINDING')
        eligible_rows = [row for row in window['candidates']
                         if row.get('security_id') in arguments['prices']]
        candidates = {row['security_id']: row for row in eligible_rows}
        if len(candidates) != len(eligible_rows):
            raise ValueError('DUPLICATE_CANDIDATE')
        count = 0
        coordinate_ratios = {}
        for sid, price in arguments['prices'].items():
            candidate = candidates[sid]
            if F(candidate['decision_cost']) != F(price):
                raise ValueError('DECISION_COST_BINDING')
            ratio = check_series(dates, candidate['training_close'], day,
                                 [scenario[sid] for scenario in arguments['training_scenarios']], price)
            if ratio != 1:
                coordinate_ratios[candidate['ticker']] = str(ratio)
            source = candidate['training_source']
            expected = prepared['source_hashes'][source]
            if source not in verified:
                verified[source] = sha256(Path(source).read_bytes()).hexdigest()
            if verified[source] != expected:
                raise ValueError('TRAINING_SOURCE_HASH_MISMATCH')
            count += 1
        rows.append(dict(decision_date=day, first_training_date=dates[0],
                         closes=253, daily_returns=252, securities=count,
                         training_last_to_decision_price=coordinate_ratios))
    return dict(status='SAVED_TRAINING_ARITHMETIC_AND_SOURCE_BYTES_MATCH', rows=rows,
        decisions=len(rows), security_windows=sum(row['securities'] for row in rows),
        verified_training_sources=len(verified), optimization_calls=0, book_calls=0,
        limitation='Conditional inherited training coordinates; not independent action reconstruction, '
                   'calendar authentication, historical availability or PIT certification.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--assembled', type=Path, required=True)
    parser.add_argument('--last-date', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw_prepared, raw_assembled = args.prepared.read_bytes(), args.assembled.read_bytes()
    result = review(json.loads(raw_prepared), json.loads(raw_assembled), args.last_date)
    result['inputs'] = {str(args.prepared): sha256(raw_prepared).hexdigest(),
                        str(args.assembled): sha256(raw_assembled).hexdigest()}
    result['script_sha256'] = sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key not in ('rows', 'inputs')}))


if __name__ == '__main__':
    main()
