"""Create-only 4x295 conditional nominal quote research from sealed inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest import ndx_nominal_quote_reconstruction_research as nominal

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BOUND = {
    'data/cache/research/preference_price_action_supplement_20260912_v1/manifest.json':
        'ef8baa8d5d370b87f31543c770b09703c2b2750c2f19686e444582eea6a67e32',
    'data/cache/research/preference_price_action_supplement_20260912_v1/price_basis_review_20260912.json':
        '0bc889f6711a64f3e2be897dd8551ff2b40e5a3a984b08afdcfc18d6abb69dd1',
    'data/cache/research/dynamic_frozen_v2/preference_refit_schedule_20260912.json':
        '4325a37801e915179bd0c428b132be56d5c2e6273524c6e2ad1101741587b559'}


def build_report():
    sources = {str(ROOT / path): digest for path, digest in BOUND.items()}
    sources[str(SOURCE)] = LOADED_SHA
    nominal.verify(sources)
    manifest, basis, schedule = [json.loads((ROOT / path).read_bytes()) for path in BOUND]
    if (basis['quote_field_basis'] != nominal.BASIS or basis['basis_status'] != 'CONDITIONAL_RESEARCH_ONLY'
            or basis['strategy_information_pit_verified'] is not False
            or basis['current_to_historical_security_binding_verified'] is not False):
        raise ValueError('Sealed conditional research basis decision required')
    for path, digest in basis['source_hashes'].items():
        if path in sources and sources[path] != digest:
            raise ValueError('Conflicting basis source closure')
        sources[path] = digest
    calendar = schedule['schedule_result']['calendar']
    if len(calendar) != 295 or calendar[0] != '2023-03-31' or calendar[-1] != '2024-06-03':
        raise ValueError('Original 295-session schedule required')
    probes = {}
    for ticker in ('AMAT', 'AVGO', 'CDNS', 'GOOG'):
        matching = [row for row in manifest['probes'] if row['name'] == 'yahoo_' + ticker.lower() + '_through_received_daily_events']
        if len(matching) != 1:
            raise ValueError('Unique original full quote probe required')
        probe = matching[0]
        if sources.get(probe['response_path']) != probe['response_sha256']:
            raise ValueError('Basis and raw quote response bindings differ')
        probes[ticker] = probe
    report = nominal.build_nominal_quote_research(calendar=calendar, probes=probes,
        quote_field_basis=basis['quote_field_basis'], source_hashes=sources)
    report.update(basis_review_path=str(ROOT / list(BOUND)[1]), basis_review_sha256=list(BOUND.values())[1],
        basis_review_status=basis['basis_status'], basis_limit=basis['raw_provider_documentation_limit'],
        schedule_path=str(ROOT / list(BOUND)[2]), schedule_sha256=list(BOUND.values())[2],
        provider_reporting_completeness_independently_certified=False)
    if report['total_rows'] != 1180:
        raise ValueError('Complete four-ticker calendar denominator required')
    nominal.verify(report['source_hashes'])
    return report


def save_report(output):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'data/cache/research').resolve()):
        raise ValueError('Research output directory required')
    report = build_report()
    encoded = (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')
    nominal.verify(report['source_hashes'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        handle.write(encoded)
    nominal.verify(report['source_hashes'])
    if output.read_bytes() != encoded:
        raise ValueError('Saved output differs')
    return dict(path=str(output), sha256=hashlib.sha256(encoded).hexdigest(), total_rows=report['total_rows'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(save_report(args.output)))
