"""Capture three explicitly located public SEC submissions once; no admission."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/cache/research/three_incumbent_identity_capture_20260925_v1'
REQUESTS = {
    'MU': 'https://www.sec.gov/Archives/edgar/data/723125/000142284823000131/0001422848-23-000131.txt',
    'MSFT': 'https://www.sec.gov/Archives/edgar/data/789019/000110465923016476/0001104659-23-016476.txt',
    'NVDA': 'https://www.sec.gov/Archives/edgar/data/1045810/000110465923016606/0001104659-23-016606.txt',
}


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


def capture():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    started_sha = save(OUTPUT / 'started.json', {
        'started_at_utc': now(), 'requests': REQUESTS, 'automatic_retry': False,
        'tls_verification_disabled': False, 'method': 'GET',
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    })
    results = []
    for ticker, url in REQUESTS.items():
        path = OUTPUT / (ticker + '.response.bin')
        began = now()
        completed = subprocess.run([
            'curl.exe', '--silent', '--show-error', '--location', '--retry', '0',
            '--max-time', '30', '--user-agent', 'us-ratchet public-research-source-capture',
            '--output', str(path), '--write-out', '%{json}', url,
        ], capture_output=True, text=True, timeout=40)
        try:
            metadata = json.loads(completed.stdout)
        except (ValueError, TypeError):
            metadata = {}
        raw = path.read_bytes() if path.exists() else b''
        record = {
            'ticker': ticker, 'request_url': url, 'started_at_utc': began,
            'received_at_utc': now(), 'curl_exit_code': completed.returncode,
            'http_status': metadata.get('http_code'),
            'final_url': metadata.get('url_effective'),
            'content_type': metadata.get('content_type'),
            'ssl_verify_result': metadata.get('ssl_verify_result'),
            'raw_path': str(path) if path.exists() else None,
            'raw_sha256': hashlib.sha256(raw).hexdigest() if path.exists() else None,
            'raw_bytes': len(raw), 'starts_with_sec_document': raw.startswith(b'<SEC-DOCUMENT>'),
            'stderr': completed.stderr, 'automatic_retry': False,
            'tls_verification_disabled': False, 'source_authenticated': False,
            'point_in_time_verified': False, 'identity_declaration_created': False,
        }
        record['status'] = ('CAPTURED_REQUIRES_INDEPENDENT_READBACK'
                            if completed.returncode == 0 and record['http_status'] == 200
                            and record['starts_with_sec_document'] else 'CAPTURE_FAILED_OR_NON_SUBMISSION')
        receipt = OUTPUT / (ticker + '.receipt.json')
        receipt_sha = save(receipt, record)
        results.append(dict(ticker=ticker, status=record['status'], raw_sha256=record['raw_sha256'],
                            receipt_sha256=receipt_sha, http_status=record['http_status']))
    manifest_sha = save(OUTPUT / 'manifest.json', {
        'started_sha256': started_sha, 'results': results, 'finished_at_utc': now(),
        'fit_performed': False, 'existing_artifacts_modified': False,
    })
    print(json.dumps(dict(output=str(OUTPUT), manifest_sha256=manifest_sha, results=results), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true')
    args = parser.parse_args()
    if not args.capture:
        parser.error('Explicit --capture required; existing namespace is never reused')
    capture()
