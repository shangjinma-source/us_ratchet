"""Read-only attribution of a pinned saved daily signal, never current advice."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction
from backtest.partial_trend_exposure import partial_sma20_target

RECEIPT = 'd1cb83187bc46acf386297ec612981148271588a27b8ba3fa8dcffa548243b2a'

def inspect_saved(root):
    folder = root / 'data/strategy_account/dynamic_daily_policy_reviewed_v1' / RECEIPT
    raw = (folder / 'receipt.json').read_bytes()
    assert sha256(raw).hexdigest() == RECEIPT
    receipt = json.loads(raw)
    manifest_raw = (folder / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    complete = json.loads((folder / 'complete.json').read_bytes())
    assert complete['receipt_sha256'] == RECEIPT
    assert complete['manifest_sha256'] == sha256(manifest_raw).hexdigest()
    assert manifest['source_sha256'] == receipt['source_sha256']
    sources = {}
    for name, digest in receipt['source_sha256'].items():
        data = (folder / 'sources' / (digest + '.bin')).read_bytes()
        assert sha256(data).hexdigest() == digest
        sources[name] = data
    inputs = json.loads(sources[receipt['normalized_inputs_path']])
    result = partial_sma20_target(**inputs)
    rows = []
    for sid, diagnostic in result['diagnostics'].items():
        closes = [Fraction(str(row['close'])) for row in inputs['histories'][sid]['closes']]
        assert len(closes) == 20
        average = sum(closes, Fraction()) / 20
        monthly = diagnostic['monthly_ceiling']
        effective = monthly if closes[-1] > average else monthly // 2
        assert result['target_quantities'][sid] == effective
        assert Fraction(diagnostic['sma20']) == average
        rows.append(dict(security_id=sid,signal_date=inputs['signal_date'],
            monthly_target=monthly,effective_target=effective,
            close=str(closes[-1]),sma20=str(average),
            reason='CLOSE_ABOVE_SMA20_KEEP_MONTHLY' if closes[-1]>average else 'CLOSE_AT_OR_BELOW_SMA20_HALF_FLOOR'))
    return dict(status='SAVED_SIGNAL_REPRODUCED_NOT_CURRENT_ADVICE',receipt_sha256=RECEIPT,
        execution_session=receipt['execution_session'],market_asof=receipt['market_asof'],
        source_files_verified=len(sources),rows=rows,
        ui_gap='Production signal omits indicator diagnostics; UI currently explains quantity change only.',
        account_mutated=False,network_calls=0)

if __name__ == '__main__':
    root=Path(__file__).resolve().parents[1]
    report=inspect_saved(root)
    output=root/'tmp/saved_daily_reason_attribution_20261023_v1.json'
    with output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False))
