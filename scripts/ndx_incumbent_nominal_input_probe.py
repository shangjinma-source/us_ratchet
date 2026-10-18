"""Read-only restoration of all incumbent nominal prices on a captured calendar."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_joint_weight_runner as encoding
from scripts.ndx_joint_weight_verify import _restore_input
from backtest.ndx_execution_nominal_bundle_research import load_execution_nominal_bundle

CONTEXT = '500e4eb1027aac7357b72a48dcc1418804b12524f3b9bca49d043cf3c600f5f2'
INVENTORY_SHA = '6e16c3fea22421e650663f617e2bf2d6c6cc87db52bf1303f7a3380e6b600961'


def run():
    context_path = ROOT/'data/cache/research/ndx_joint_weight_runs_v2'/CONTEXT/'context.json'
    raw = context_path.read_bytes()
    context = json.loads(raw)
    if encoding._sha(context) != CONTEXT or encoding._json_bytes(context) != raw:
        raise ValueError('Captured context identity differs')
    sources = [Path(__file__), ROOT/'backtest/ndx_joint_weight_runner.py',
               ROOT/'scripts/ndx_joint_weight_verify.py', ROOT/'backtest/ndx_execution_nominal_bundle_research.py']
    hashes = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    inputs = {k:_restore_input(v) for k,v in context['prepared_inputs'].items()}
    weights = inputs['incumbent_weights']
    original = inputs['nominal_prices']
    result = load_execution_nominal_bundle(
        inventory_path=ROOT/'data/cache/research/ndx_cardinality_execution_prices_walkforward_v2/execution_price_inventory.csv',
        expected_inventory_sha256=INVENTORY_SHA, tickers=sorted(weights), execution_calendar=original.index)
    prices = result.pop('prices')
    overlap = sorted(set(prices) & set(original))
    differences = {t: float((prices[t]-original[t]).abs().max()) for t in overlap}
    if any(differences.values()):
        raise ValueError('Overlapping incumbent prices differ from frozen context')
    if context_path.read_bytes() != raw or any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p,h in hashes.items()):
        raise ValueError('Probe context or source drift')
    return dict(schema='ndx_incumbent_nominal_input_probe_v1', context_sha256=CONTEXT,
        source_hashes=hashes, incumbent_weights=weights, weights_changed=False,
        date_start=str(prices.index[0].date()), date_end=str(prices.index[-1].date()),
        calendar=list(prices.index.strftime('%Y-%m-%d')), rows=len(prices), tickers=list(prices),
        restored_missing_tickers=sorted(set(prices)-set(original)), overlap_max_abs_difference=differences,
        panel_context_sha256=encoding._sha(encoding._panel_context(prices)),
        price_summary={t:dict(first=float(prices[t].iloc[0]),last=float(prices[t].iloc[-1]),
                             minimum=float(prices[t].min()),maximum=float(prices[t].max())) for t in prices},
        nominal_bundle=result, scope='INPUT_ONLY_NOT_EXECUTION_OR_BENCHMARK_QUALIFICATION',
        promotion_allowed=False, order_generation_allowed=False)


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
