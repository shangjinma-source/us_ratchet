"""Create-only extraction of the sealed public-source probe; no network or execution."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest.ndx_identity_raw_fact_research import extract_bound_probe, verify

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
MANIFEST = ROOT / 'data/cache/research/identity_public_source_probe_20260912_v1/manifest.json'
MANIFEST_SHA = '93de067b0e994adb0d2b6b1860cb9c3f36e2173c445f044db5f08bc14e20a3c2'


def build_report():
    result = extract_bound_probe(manifest_path=MANIFEST, expected_sha256=MANIFEST_SHA)
    result['source_hashes'][str(SOURCE)] = LOADED_SHA
    result['input_probe_manifest_sha256'] = MANIFEST_SHA
    verify(result['source_hashes'])
    return result


def save_report(output):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'data/cache/research').resolve()):
        raise ValueError('Research directory required')
    result = build_report()
    encoded = (json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    verify(result['source_hashes'])
    with output.open('xb') as handle:
        handle.write(encoded)
    verify(result['source_hashes'])
    return {'path': str(output), 'sha256': hashlib.sha256(encoded).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    print(json.dumps(save_report(arguments.output), ensure_ascii=False))
