"""One deterministic 67-month ranking inventory; no optimizer or account replay."""
import json
import time
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from scripts.audit_capped_training_frontier import validate_binding
from backtest.long_market_trend_research_v1 import signal_proof

ROOT = Path(__file__).resolve().parents[2]


def main():
    started = time.monotonic()
    output = ROOT / 'tmp/cross_sectional_momentum_static_20261105'
    output.mkdir(exist_ok=False)
    pins = {}
    def read(name):
        return json.loads((ROOT / name).read_bytes())
    def verify(expected):
        for name, digest in expected.items():
            if name in pins and pins[name] != digest:
                raise ValueError('PIN_CONFLICT:' + name)
            if sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise ValueError('FROZEN_SOURCE_CHANGED:' + name)
            pins[name] = digest
    manifest_path = 'research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json'
    manifest = read(manifest_path)['base_file_dependencies']
    signal_path = 'tmp/qqq_month_end_warmup_20261026_v1/two_window_signal_input_manifest.json'
    verify({signal_path: manifest[signal_path]})
    signals = {w['name']: {r['decision_date']: r for r in w['inputs']}
               for w in read(signal_path)['windows']}
    rows = []
    local = {}
    specifications = [
        ('2021_2023', 36, 'tmp/recent_continuous_baseline_20261026_v7',
         'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'),
        ('2024_2026', 31, 'tmp/old_continuous_baseline_20261026_v9',
         'tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')]
    for label, count, base, training_path in specifications:
        verify({training_path: manifest[training_path]})
        document = read(training_path)
        verify(document['source_hashes'])
        assert len(document['windows']) == count
        for outer in document['windows']:
            window = outer.get('window', outer)
            day = window.get('decision_cutoff', window.get('decision_date'))
            dates = window['training_dates']
            assert len(dates) == 253 and dates == sorted(set(dates)) and dates[-1] == day
            name = base + '/' + day + '.selection.json'
            saved = read(name)
            raw = saved['raw_selection']
            arguments = validate_binding(raw)
            verify(raw['binding']['source_hashes'])
            local[name] = sha256((ROOT / name).read_bytes()).hexdigest()
            assert arguments['scenario_dates'] == dates[21::21]
            candidates = {c['security_id']: c for c in window['candidates'] if c.get('security_id')}
            ranked = []
            for sid in arguments['prices']:
                candidate = candidates[sid]
                prices = list(map(F, candidate['training_close']))
                assert len(prices) == 253 and all(p > 0 for p in prices)
                assert all(F(arguments['training_scenarios'][j][sid]) == prices[(j+1)*21] / prices[j*21]
                           for j in range(12)), ('COORDINATE_SCENARIO_MISMATCH', day, sid)
                issuer = arguments['metadata'][sid]['issuer_id']
                assert issuer and issuer == candidate['issuer_id']
                ranked.append(dict(security_id=sid, issuer_id=issuer, ticker=candidate['ticker'],
                                   ratio=prices[-22]/prices[-253], numerator_date=dates[-22],
                                   denominator_date=dates[-253], training_status=candidate.get('status'),
                                   training_source=candidate.get('training_source')))
            ranked.sort(key=lambda r: (-r['ratio'], r['security_id']))
            selected = []
            issuers = set()
            for rank, item in enumerate(ranked, 1):
                item['rank'] = rank
                item['ratio_exact'] = str(item.pop('ratio'))
                item['issuer_unique_eligible'] = item['issuer_id'] not in issuers
                if item['issuer_unique_eligible']:
                    issuers.add(item['issuer_id'])
                    if len(selected) < 10:
                        selected.append(item.copy())
            if len(selected) != 10:
                raise ValueError('LESS_THAN_TEN_UNIQUE_ELIGIBLE:' + day)
            signal = signals[label][day]
            for price in signal['completed_month_end_prices']:
                verify({price['source']: manifest[price['source']]})
            proof = signal_proof(signal)
            rows.append(dict(window=label, decision_date=day, training_dates=dates,
                             legal_domain_count=len(ranked), ranked=ranked, selected=selected,
                             gate=proof, actual_exposure='SELECTED_TEN_PENDING_ACTION_ADMISSION' if proof['risk_on'] else 'CASH',
                             action_admission='NOT_PERFORMED_NO_EVIDENCE_BASED_REMOVALS',
                             coordinate_check='EXACT_EXISTING_12_SCENARIOS_CONDITIONAL_TRAINING_COORDINATE'))
        assert {r['decision_date'] for r in rows if r['window'] == label} == set(signals[label])
    verify(dict(pins))
    for name, digest in local.items():
        assert sha256((ROOT/name).read_bytes()).hexdigest() == digest
    summary = [dict(window=label, months=sum(r['window']==label for r in rows),
                    on_months=sum(r['window']==label and r['gate']['risk_on'] for r in rows),
                    selected_tickers=sorted({s['ticker'] for r in rows if r['window']==label for s in r['selected']}))
               for label, *_ in specifications]
    result = dict(status='STATIC_RANKING_COMPLETE_NOT_ACCOUNT_BACKTEST', summary=summary, rows=rows,
                  prior_expected_hashes_verified=pins, selection_artifact_hashes=local,
                  archive_manifest_sha256=sha256((ROOT/manifest_path).read_bytes()).hexdigest(),
                  script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  search_calls=0, economic_runs=0, elapsed_seconds=time.monotonic()-started,
                  limits=['Conditional historical legal domains, not certified full PIT universe',
                          'Training coordinate reused, not new corporate-action certification',
                          'Price momentum not total return; no execution quantities or profits computed'])
    (output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
