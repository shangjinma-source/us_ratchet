"""Fixed saved-month candidate diagnostic; never runs V2 or a portfolio book."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import time
from backtest.saved_quantity_candidate_comparison import compare_saved_candidates, canonical_sha256

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'tmp/continuous_candidate_diagnostic_20261016_v1'

def main(execute=False):
    preflight = json.loads((ROOT / 'tmp/continuous_candidate_diagnostic_preflight_20261016_v1.json').read_bytes())
    pins = dict(preflight['source_hashes'])
    for path, digest in pins.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    prepared = json.loads((ROOT / 'tmp/daily_verified_domain_experiment_20261016_v2/prepared.json').read_bytes())
    outcome = json.loads((ROOT / 'tmp/daily_exclusion_B0_20261016_v1/outcome.json').read_bytes())
    contract = json.loads((ROOT / 'research_contracts/continuous_candidate_diagnostic_20261016_v1.json').read_bytes())
    assert contract['fixed_iterations_per_month'] == 32
    windows = {row['decision_date']: row for row in prepared['windows']}
    selections = [row['selection'] for row in outcome['provider_audit'] if row.get('selection')]
    assert len(selections) == len(windows) == 34
    assert {row['decision_date'] for row in selections} == set(windows)
    cases = []
    for selection in selections:
        binding = selection['binding']
        digest = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        assert digest == selection['decision_id']
        args = deepcopy(windows[selection['decision_date']]['search_arguments'])
        assert args['decision_date'] == selection['decision_date']
        bases = {quote['price_basis'] for quote in binding['valuation_quotes'].values()}
        assert len(bases) == 1
        basis = next(iter(bases))
        args['entered_cash'] = selection['investable_equity']
        assert args == binding['search_arguments']
        equity = F(binding['available_cash'])
        for sid, shares in binding['shares'].items():
            assert type(shares) is int and shares >= 0
            if not shares:
                continue
            quote = binding['valuation_quotes'][sid]
            assert quote['price_basis'] == basis and quote['as_of'] == selection['decision_date']
            equity += shares * F(quote['price'])
        assert equity == F(selection['investable_equity'])
        for path, digest in binding['source_hashes'].items():
            assert path not in pins or pins[path] == digest
            pins[path] = digest
        cases.append((selection, args))
    for path, digest in pins.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    for path in ['scripts/run_continuous_candidate_diagnostic.py', 'backtest/saved_quantity_candidate_comparison.py', 'tmp/continuous_candidate_diagnostic_preflight_20261016_v1.json']:
        pins[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    if not execute:
        print(json.dumps({'status':'PREFLIGHT_PASS','cases':len(cases),'iterations':32}))
        return
    OUTPUT.mkdir(exist_ok=False)
    (OUTPUT / 'started.json').write_text(json.dumps({'source_hashes':pins,'started_at':datetime.now(timezone.utc).isoformat()},indent=2),encoding='utf-8')
    rows = []
    for selection, args in cases:
        started = time.monotonic()
        result = compare_saved_candidates(search_arguments=args, saved_result=selection['search_result'], iterations=32,
            expected_search_arguments_sha256=canonical_sha256(args), expected_saved_result_sha256=canonical_sha256(selection['search_result']))
        day = selection['decision_date']
        def product(target):
            cash = F(args['entered_cash'])
            notional = sum((F(args['prices'][sid])*q for sid,q in target.items()),F(0))
            residual = cash-notional*(1+F(args['fee_bps'])/10000)
            return math.prod((residual+sum((F(args['prices'][sid])*q*F(scenario[sid]) for sid,q in target.items()),F(0)))/cash for scenario in args['training_scenarios'])
        old_product = product(selection['target_quantities'])
        new_product = product(result['selected']['quantities'])
        assert new_product >= old_product
        with (OUTPUT / (day + '.json')).open('x',encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
        row = {'decision_date':day, 'elapsed_seconds':time.monotonic()-started,
               'old_quantities':selection['target_quantities'], 'new_quantities':result['selected']['quantities'],
               'changed':selection['target_quantities'] != result['selected']['quantities'],
               'strict_score_improvement':new_product > old_product,
               'tie_only_change':new_product == old_product and selection['target_quantities'] != result['selected']['quantities'],
               'additional_candidates':result['exact_evaluations']['new_unique']}
        rows.append(row)
        print(json.dumps(row), flush=True)
    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest()==h for p,h in pins.items())
    with (OUTPUT / 'complete.json').open('x',encoding='utf-8') as stream:
        json.dump({'status':'COMPLETE_PENDING_INDEPENDENT_REVIEW','rows':rows,'source_hashes':pins,
                   'economic_runs':0,'changed_months':sum(row['changed'] for row in rows),
                   'strict_improvements':sum(row['strict_score_improvement'] for row in rows),
                   'tie_only_changes':sum(row['tie_only_change'] for row in rows)},stream,indent=2)

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    main(parser.parse_args().execute)
