"""Verify all 36 new ordinary dividend pairs without running an account."""
import json
from hashlib import sha256
from pathlib import Path
from docs.candidates.downside_resume_chain_20261105 import append_ordinary_artifact

ROOT = Path(__file__).resolve().parents[2]


def main():
    batches = [
        ('2021_2023', 'tmp/recent_continuous_baseline_20261026_v7/execution_inputs.json',
         ['tmp/momentum_early_dividends_20261105/supplement.json'], 18),
        ('2024_2026', 'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json',
         ['tmp/momentum_late_dividends_20261105/supplement.json',
          'tmp/amat_202408_t1_resolution_20261105/supplement.json'], 18)]
    results, pins = [], {}

    def pin(name, expected=None):
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('PATH_OUTSIDE_WORKSPACE')
        digest = sha256(path.read_bytes()).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('SOURCE_CHANGED:' + name)
        if name in pins and pins[name] != digest:
            raise ValueError('PIN_CONFLICT:' + name)
        pins[name] = digest

    for window, document_path, artifacts, expected_count in batches:
        pin(document_path)
        document = json.loads((ROOT / document_path).read_bytes())
        if window == '2021_2023':
            # Early baseline stores the same required metadata under prepared.
            # Alias only the in-memory validator view; preserve all source files.
            document['prepared_input_candidate'] = document['prepared']
        review = dict(rows=[], source_hashes={})
        before = len(document['dividend_events'])
        for name in artifacts:
            pin(name)
            artifact = json.loads((ROOT / name).read_bytes())
            for source, digest in artifact['source_hashes'].items():
                pin(source, digest)
            append_ordinary_artifact(document, review, artifact)
        count = len(document['dividend_events']) - before
        if count != expected_count or len(review['rows']) != expected_count:
            raise ValueError('EXACT_BATCH_COUNT_REQUIRED')
        results.append(dict(window=window, paired_events=count,
                            status='PAIRED_APPEND_AND_SOURCE_PINS_PASS'))
    pin('docs/candidates/downside_resume_chain_20261105.py')
    pin(Path(__file__).relative_to(ROOT).as_posix())
    output = ROOT / 'tmp/momentum_dividend_batch_review_20261105'
    output.mkdir(exist_ok=False)
    report = dict(status='36_PAIRS_VERIFIED_NOT_ECONOMIC_ADMISSION', results=results,
                  source_hashes=pins,
                  limitations=['AMAT ex-date is rule-supported with issuer history conflict retained.',
                               'ASML final FX publication timing requires execution dependency review.',
                               'No full account replay, split admission or merger cash settlement approval.'])
    (output / 'review.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(dict(status=report['status'], results=results, pinned_files=len(pins))))


if __name__ == '__main__':
    main()
