"""Join explicitly named original-response registries; no filesystem-wide search."""
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


def run(root=ROOT):
    refs = {}
    def raw(path, expected=None):
        data = (root/path).read_bytes()
        digest = sha256(data).hexdigest()
        if expected and digest != expected:
            raise ValueError('RECEIPT_BYTES_CHANGED')
        refs[path] = digest
        return data
    manifest_path = 'tmp/held_disclosure_inventory_20261027/manifest.json'
    manifest = json.loads(raw(manifest_path))
    originals = {}
    registries = ('tmp/sec_original_filing_check_20261027/receipt.json',
                  'tmp/historical_news_identity_20261027/cover_evidence/receipts.json')
    for registry in registries:
        for receipt in json.loads(raw(registry)):
            url = urlsplit(receipt['url'])
            match = re.fullmatch(r'/Archives/edgar/data/(\d+)/(\d{18})/[^/]+', url.path)
            if receipt['status'] != 200 or url.scheme != 'https' or url.hostname != 'www.sec.gov' or not match:
                raise ValueError('OFFICIAL_SEC_ORIGINAL_REQUIRED')
            if receipt['accession'].replace('-', '') != match[2]:
                raise ValueError('ACCESSION_URL_MISMATCH')
            if receipt.get('cik') and int(receipt['cik']) != int(match[1]):
                raise ValueError('CIK_URL_MISMATCH')
            path = str(Path(registry).parent/ (receipt['ticker'] + '.html'))
            content = raw(path, receipt['sha256'])
            if len(content) != receipt['bytes'] or b'<html' not in content.lower():
                raise ValueError('HTML_BYTES_REQUIRED')
            key = (str(int(match[1])).zfill(10), receipt['accession'])
            originals[key] = dict(path=path, sha256=receipt['sha256'], url=receipt['url'],
                                  registry=registry, status='ORIGINAL_BYTES_BOUND_NOT_TRADING_ADMISSION')
    windows = []
    matched = set()
    for window in manifest['windows']:
        rows = []
        for row in window['rows']:
            key = (row['cik'], row['accession'])
            if key in originals:
                matched.add(key)
                rows.append(dict(security_id=row['security_id'], accession=row['accession'],
                                 original=originals[key], metadata_conflict=row['metadata_conflict']))
        windows.append(dict(window=window['window'], filing_records=window['security_filings'],
                            matched_originals=len(rows), not_located_in_named_registries=window['security_filings']-len(rows), rows=rows))
    return dict(windows=windows, source_hashes=refs, registry_count=len(registries),
                originals_outside_manifest=[originals[key] for key in originals.keys()-matched],
                limitations=['Only two explicitly named original registries, not all repository caches.',
                    'Unmatched does not mean absent, and is not a download queue.',
                    'Byte/URL binding does not validate every fact, context or earliest release time.',
                    'AMD guidance sources are outside the held-security filing universe; not counted.',
                    'No network or production change.'])


if __name__ == '__main__':
    result = run()
    destination = ROOT/'tmp/held_disclosure_inventory_20261027/original_join.json'
    destination.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps([{key:value for key,value in row.items() if key != 'rows'} for row in result['windows']]))
    print('outside_manifest', len(result['originals_outside_manifest']))
