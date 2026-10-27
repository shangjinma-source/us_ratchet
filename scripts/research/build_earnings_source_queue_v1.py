"""Bounded original-document queue from 8-K Item 2.02, without outcome filtering."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.build_news_session_clock_v1 import build, event_execution

ROOT = Path(__file__).resolve().parents[2]


def run(root=ROOT):
    refs = {}
    def read(path, digest=None):
        raw = (root/path).read_bytes()
        actual = sha256(raw).hexdigest()
        if digest and actual != digest:
            raise ValueError('SOURCE_CHANGED')
        refs[path] = actual
        return json.loads(raw)
    manifest = read('tmp/held_disclosure_inventory_20261027/manifest.json')
    inventory = read('tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_v5.json')
    clock = build(root)
    cache = {}
    results = []
    for window, source in zip(manifest['windows'], inventory['windows']):
        if window['window'] != source['window']:
            raise ValueError('WINDOW_MISMATCH')
        book = read(source['frozen_book']['path'], source['frozen_book']['sha256'])
        inputs = read(source['frozen_inputs']['path'], source['frozen_inputs']['sha256'])
        dates = inputs['assembled']['session_dates']
        if book['status'] != 'COMPLETE' or len(book['provider_audit']) != len(dates)-1:
            raise ValueError('INCOMPLETE_BASELINE')
        audit = dict(zip(dates[:-1], book['provider_audit']))
        held = {row['date']: row['shares'] for row in book['daily_ledger']}
        selected, unknown = [], []
        for filing in window['rows']:
            if filing['metadata_conflict']:
                continue
            version = filing['versions'][0]
            if version['form'] not in ('8-K', '8-K/A', '6-K', '6-K/A'):
                continue
            timing = event_execution(clock['sessions'], version['acceptanceDateTime'])
            if timing is None or timing['decision_date'] not in audit:
                continue
            day, security = timing['decision_date'], filing['security_id']
            if not (held.get(day, {}).get(security, 0) or audit[day].get('target_shares', {}).get(security, 0)):
                continue
            items = set()
            for path, digest in inventory['issuers'][filing['cik']]['inputs']['submissions'].items():
                if path not in cache:
                    document = read(path, digest)
                    recent = document.get('filings', {}).get('recent', document)
                    cache[path] = dict(zip(recent.get('accessionNumber', []), recent.get('items', [])))
                if filing['accession'] in cache[path]:
                    items.add(cache[path][filing['accession']])
            row = dict(security_id=security, tickers=filing['tickers'], cik=filing['cik'],
                       accession=filing['accession'], acceptance=version['acceptanceDateTime'],
                       timing=timing, items=sorted(items), form=version['form'],
                       index_url='https://www.sec.gov/Archives/edgar/data/'+str(int(filing['cik']))+'/'+
                       filing['accession']+'-index.htm')
            if len(items) == 1 and '2.02' in next(iter(items)).split(','):
                selected.append(row)
            else:
                unknown.append(row)
        selected.sort(key=lambda row: (datetime.fromisoformat(row['acceptance'].replace('Z', '+00:00')), row['security_id']))
        results.append(dict(window=window['window'], earnings_candidates=len(selected),
                            other_or_unclassified_exposed_filings=len(unknown), queue=selected, unclassified=unknown))
    return dict(windows=results, source_hashes=refs, selection='ITEM_2_02_AND_BASELINE_EXPOSURE_THEN_CHRONOLOGICAL',
                limitations=['Item 2.02 is an earnings disclosure lead, not authenticated original attachment.',
                    '6-K and unclassified items retained separately, not assumed irrelevant.',
                    'Only baseline current exposure; pre-entry events and changed-account branches are not covered.',
                    'No outcome filtering, model calls or trading authorization.'])


if __name__ == '__main__':
    result = run()
    output = ROOT/'tmp/held_disclosure_inventory_20261027/earnings_queue.json'
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    for window in result['windows']:
        print(window['window'], window['earnings_candidates'], window['other_or_unclassified_exposed_filings'])
        print(json.dumps(window['queue'][:2]))
