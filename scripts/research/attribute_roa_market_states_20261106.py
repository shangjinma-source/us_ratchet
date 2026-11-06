"""Attribute the frozen continuous diagnostic; no parameter search or rerun."""
import hashlib
import json
from pathlib import Path

from scripts.research.screen_profitability_daily_regime_20261106 import read_qqq

ROOT = Path(__file__).resolve().parents[2]


def main():
    source = ROOT / 'tmp/profitability_roa_continuous_20261106_SMA200.json'
    pins = {str(source.relative_to(ROOT)): hashlib.sha256(source.read_bytes()).hexdigest()}
    result = json.loads(source.read_text())['results'][0]
    quotes = read_qqq(pins)
    previous_equity = 20000.0
    previous_quote = quotes[result['warmup']['anchor']]
    groups = {}
    switches = []
    last_risk = None
    for row in result['ledger']:
        risk = row['risk_on']
        if type(risk) is not bool:
            raise ValueError('EXPLICIT_MARKET_STATE_REQUIRED')
        if last_risk is not None and risk != last_risk:
            switches.append(dict(date=row['date'], risk_on=risk, signal_date=row['signal_date']))
        last_risk = risk
        key = (row['date'][:4], 'ON' if risk else 'OFF')
        group = groups.setdefault(key, dict(sessions=0, candidate_factor=1.0, qqq_factor=1.0,
            stock_exposure_sessions=0))
        group['sessions'] += 1
        group['candidate_factor'] *= row['equity'] / previous_equity
        group['qqq_factor'] *= quotes[row['date']] / previous_quote
        group['stock_exposure_sessions'] += int(sum(row['stock_values'].values()) > 0.000001)
        previous_equity = row['equity']
        previous_quote = quotes[row['date']]
    rows = [dict(year=year, market_state=state, **values) for (year, state), values in sorted(groups.items())]
    output = dict(status='READ_ONLY_PRICE_DIAGNOSTIC_ATTRIBUTION', groups=rows, switches=switches,
        source_hashes=pins, limitation='Conditional close-to-close compounded returns, not standalone strategies; switch-day overnight belongs to prior holdings. OFF is rule output, not hindsight bear label. No dividend/tax/account admission; QQQ conditional factors exclude initial entry cost.')
    path = ROOT / 'tmp/roa_market_states_20261106.json'
    path.write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(dict(groups=rows, switches=len(switches)), indent=2))


if __name__ == '__main__':
    main()
