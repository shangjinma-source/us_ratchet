"""Count supplied SEC filing metadata independently of extracted financial facts."""
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
FORMS = {'8-K', '8-K/A', '6-K', '6-K/A', '10-Q', '10-Q/A', '10-K', '10-K/A', '20-F', '20-F/A'}


def run(root=ROOT):
    references = {}
    def read(path, expected=None):
        raw = (root/path).read_bytes()
        digest = sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('SOURCE_CHANGED:' + path)
        references[path] = digest
        return json.loads(raw)
    inventory = read('tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_v5.json')
    queue = read('tmp/guidance_exposure_queue_20261027/queue.json')
    windows = []
    for window in inventory['windows']:
        exposure = [value for value in queue['windows'] if value['book_sha256'] == window['frozen_book']['sha256']]
        if len(exposure) != 1:
            raise ValueError('EXPOSURE_BINDING_REQUIRED')
        held = {row['security_id'] for row in exposure[0]['rows']}
        rows, missing = [], []
        for security in window['rows']:
            if security['security_id'] not in held:
                continue
            issuer = inventory['issuers'].get(security.get('cik'), {})
            paths = issuer.get('inputs', {}).get('submissions', {})
            grouped = defaultdict(dict)
            for path, digest in paths.items():
                document = read(path, digest)
                recent = document.get('filings', {}).get('recent', document)
                for index, accession in enumerate(recent.get('accessionNumber', [])):
                    row = {key: values[index] for key, values in recent.items()
                           if isinstance(values, list) and index < len(values)}
                    if row.get('form') not in FORMS:
                        continue
                    selected = {key: row.get(key) for key in
                        ('form', 'filingDate', 'reportDate', 'acceptanceDateTime', 'primaryDocument')}
                    grouped[accession][json.dumps(selected, sort_keys=True)] = selected
            if not grouped:
                missing.append(security['security_id'])
            fact_accessions = {event['accession'] for event in issuer.get('events', [])}
            for accession, versions in grouped.items():
                values = list(versions.values())
                # Filing-date scope retains records whose acceptance is missing or conflicting.
                if not any(window['start'] <= (row.get('filingDate') or '') <= window['end'] for row in values):
                    continue
                valid_time = True
                for row in values:
                    try:
                        parsed = datetime.fromisoformat((row.get('acceptanceDateTime') or '').replace('Z', '+00:00'))
                        if parsed.utcoffset() is None:
                            valid_time = False
                    except ValueError:
                        valid_time = False
                rows.append(dict(security_id=security['security_id'], tickers=security['tickers'],
                    cik=security['cik'], accession=accession, versions=values,
                    metadata_conflict=len(values) != 1,
                    conflicting_fields=[key for key in values[0] if len({value[key] for value in values}) > 1],
                    exact_acceptance_present=valid_time,
                    has_extracted_fact_candidate=accession in fact_accessions,
                    original_text_review_status='NOT_JOINED', historical_identity=security['identity_status']))
        forms = Counter(row['versions'][0]['form'] for row in rows if not row['metadata_conflict'])
        windows.append(dict(window=window['window'], held_securities=len(held),
            security_filings=len(rows), unique_issuer_filings=len({(row['cik'],row['accession']) for row in rows}),
            forms=dict(forms), metadata_conflicts=sum(row['metadata_conflict'] for row in rows),
            conflict_fields=dict(Counter(key for row in rows for key in row['conflicting_fields'])),
            missing_exact_time=sum(not row['exact_acceptance_present'] for row in rows),
            filings_with_fact_candidates=sum(row['has_extracted_fact_candidate'] for row in rows),
            no_submission_metadata=missing, rows=rows))
    return dict(windows=windows, source_hashes=references, limitations=[
        'Supplied SEC metadata only; not a complete news, original text, or first-publication corpus.',
        'All window filings for securities ever held; not limited to their holding dates.',
        '8-K/6-K include non-earnings disclosures; document inspection is required to classify.',
        'No review registry join: NOT_JOINED does not mean original text is unavailable.',
        'Identity leads and metadata conflicts retained; no automated trade admission.'])


if __name__ == '__main__':
    result = run()
    output = ROOT/'tmp/held_disclosure_inventory_20261027/manifest.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps([{key:value for key,value in row.items() if key != 'rows'} for row in result['windows']]))
