"""Seal a current Nasdaq component response; never backfill historical members."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_identity_source_probe import capture


def main():
    directory = ROOT / 'data/cache/research/ndx_current_official_membership_probe_20260912_v1'
    directory.mkdir(parents=True, exist_ok=False)
    request = dict(name='nasdaq_current_nasdaq100_components', method='GET', direct=False,
                   url='https://api.nasdaq.com/api/nasdaq100')
    metadata, raw = capture(request)
    if raw is not None:
        path = directory / 'components.response.bin'
        with path.open('xb') as stream:
            stream.write(raw)
        metadata.update(response_path=str(path), response_sha256=hashlib.sha256(raw).hexdigest(),
                        response_bytes=len(raw))
    else:
        metadata.update(response_path=None, response_sha256=None, response_bytes=0)
    sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
        Path(__file__).resolve(), ROOT / 'scripts/ndx_identity_source_probe.py')}
    report = dict(schema='ndx_current_official_membership_probe_research_v1', probe=metadata,
        source_hashes=sources, observed_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='CURRENT_SOURCE_OBSERVATION_ONLY_NOT_HISTORICAL_BASELINE',
        historical_backfill_allowed=False, membership_adjudicated=False,
        selection_performed=False, execution_performed=False, promotion_allowed=False)
    encoded = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    with (directory / 'manifest.json').open('xb') as stream:
        stream.write(encoded)
    print(json.dumps({'sha256': hashlib.sha256(encoded).hexdigest(),
                      'http_status': metadata['http_status'], 'bytes': metadata['response_bytes']}))


if __name__ == '__main__':
    main()
