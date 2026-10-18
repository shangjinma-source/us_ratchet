"""Explicit reviewed-domain input preparation; never imports search or writes live state."""
import argparse
from datetime import date
from fractions import Fraction
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SHA = '756a16a83735279db24332d096aa149b54fc7ff4e91cb807410b3f33f425b588'


def build(panel, accepted_metadata, excluded_reasons, *, decision_date='2026-10-13', expected_domain_size=101):
    """accepted_metadata=[{ticker,security_id,issuer_id}], exclusions={ticker:[reason]}.

    Every panel ticker must be accepted or explicitly excluded by the reviewer.
    Exclusions are declarations, never inferred from volume, risk_chain or prices.
    Accepted rows with missing identity or Close block the whole preparation.
    """
    calendar = panel['calendar']
    if (not isinstance(calendar, list) or len(calendar) < 253 or calendar != sorted(set(calendar))
            or any(date.fromisoformat(d).isoformat() != d for d in calendar) or calendar[-1] != decision_date):
        raise ValueError('Ordered full calendar ending exactly at decision required')
    stocks = panel['stocks']
    tickers = [r['ticker'] for r in stocks]
    if len(stocks) != expected_domain_size or len(set(tickers)) != len(tickers):
        raise ValueError('Full unique panel domain required')
    if not isinstance(accepted_metadata, list) or not accepted_metadata:
        raise ValueError('Explicit nonempty reviewed candidate list required')
    accepted = {}
    for row in accepted_metadata:
        ticker = row['ticker']
        if ticker not in tickers or ticker in accepted:
            raise ValueError('Duplicate or unknown accepted ticker')
        accepted[ticker] = row
    if not isinstance(excluded_reasons, dict) or set(accepted) & set(excluded_reasons) or set(accepted) | set(excluded_reasons) != set(tickers):
        raise ValueError('Every full-domain name needs explicit acceptance or exclusion')
    if any(not isinstance(reasons, list) or not reasons or any(not isinstance(r, str) or not r.strip() for r in reasons)
           for reasons in excluded_reasons.values()):
        raise ValueError('Explicit nonempty exclusion reasons required')
    days = calendar[-253:]
    coverage, prices, metadata, scenarios, blockers = [], {}, {}, [{} for _ in range(12)], []
    seen_sids = set()
    for stock in stocks:
        ticker = stock['ticker']
        if len(stock['values']) != len(calendar):
            raise ValueError('Panel/calendar row alignment differs: ' + ticker)
        values, missing = [], []
        for day, row in zip(days, stock['values'][-253:]):
            try:
                value = row[3]
                if isinstance(value, bool) or value is None:
                    raise ValueError('Invalid Close')
                parsed = Fraction(str(value))
                if parsed <= 0:
                    raise ValueError('Nonpositive Close')
                values.append(parsed)
            except (IndexError, TypeError, ValueError, ZeroDivisionError):
                values.append(None)
                missing.append(day)
        reasons = []
        candidate = accepted.get(ticker)
        if candidate is not None:
            if any(not isinstance(candidate.get(k), str) or not candidate[k].strip() for k in ('security_id', 'issuer_id')):
                reasons.append('ACCEPTED_IDENTITY_INSUFFICIENT')
            elif candidate['security_id'] in seen_sids:
                raise ValueError('Duplicate accepted security_id')
            else:
                seen_sids.add(candidate['security_id'])
            if missing:
                reasons.append('ACCEPTED_TRAINING_CLOSE_INCOMPLETE')
            if reasons:
                blockers.append(dict(ticker=ticker, reasons=reasons))
            else:
                sid = candidate['security_id']
                prices[sid] = str(values[-1])
                metadata[sid] = dict(ticker=ticker, issuer_id=candidate['issuer_id'])
                for i, scenario in enumerate(scenarios):
                    scenario[sid] = str(values[(i+1)*21] / values[i*21])
        coverage.append(dict(ticker=ticker, accepted=candidate is not None,
            exclusion_reasons=excluded_reasons.get(ticker, []), preparation_blockers=reasons,
            missing_close_dates=missing, complete_253_closes=not missing,
            identity=candidate, price_basis='CONDITIONAL_PANEL_CLOSE_NO_NOMINAL_OR_TOTAL_RETURN_CERTIFICATION'))
    arguments = None if blockers else dict(prices=prices, metadata=metadata, entered_cash='20000', fee_bps='0',
        minimum_cash_buffer='0', training_scenarios=scenarios, scenario_dates=days[21::21],
        decision_date=decision_date, max_objective_evaluations=8192, fixed_seed='fresh-quantity-20261014-v1')
    return dict(status='BLOCKED' if blockers else 'READY_CONDITIONAL_REQUIRES_REVIEW',
        search_arguments=arguments, full_domain_count=len(stocks), accepted_count=len(accepted),
        coverage=coverage, blockers=blockers, training_dates=days,
        scenario_start_dates=days[:-1:21], scenario_end_dates=days[21::21],
        duplicate_issuer_classes_allowed=True, issuer_exclusivity_authority='UNCHANGED_QUANTITY_CORE',
        automatic_domain_selection=False, missing_values_filled=False, volume_or_risk_chain_gate=False,
        search_calls=0, book_calls=0, research_only=True, execution_blocked=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--panel', required=True, type=Path)
    parser.add_argument('--panel-sha256', required=True)
    parser.add_argument('--acceptance', required=True, type=Path)
    parser.add_argument('--acceptance-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or (ROOT/'tmp').resolve() not in output.parents:
        raise ValueError('Create-only tmp output required')
    pins = {}
    def read(path, expected):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected:
            raise ValueError('Input pin differs: ' + str(path))
        pins[str(path.resolve())] = digest
        return raw
    panel = json.loads(read(args.panel, args.panel_sha256))
    approval = json.loads(read(args.acceptance, args.acceptance_sha256))
    if approval.get('status') != 'ROOT_REVIEWED_EXPLICIT_DOMAIN' or approval.get('decision_date') != '2026-10-13' or approval.get('panel_sha256') != args.panel_sha256:
        raise ValueError('Explicit review/date/panel binding required')
    evidence = approval.get('source_hashes')
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError('Nonempty reviewed evidence source_hashes required')
    for name, expected in evidence.items():
        path = Path(name)
        if not path.is_absolute():
            path = ROOT / path
        read(path, expected)
    read(ROOT/'backtest/return_priority_fresh_cash_quantity_search.py', CORE_SHA)
    result = build(panel, approval['accepted_metadata'], approval['excluded_reasons'])
    pins[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['source_hashes'] = pins
    for path, digest in pins.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Source changed during preparation')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(dict(status=result['status'], accepted_count=result['accepted_count'], search_calls=0)))
