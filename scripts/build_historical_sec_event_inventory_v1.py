"""Offline SEC fact inventory over the entire supplied frozen price domain."""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import re
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.extract_sec_quarter_events_v1 import extract, timestamp


def merge_facts(cik, documents):
    """Union observations, never latest-wins; differing values remain conflicts."""
    merged = dict(cik=int(cik), facts={})
    seen = set()
    for document in documents:
        if int(document['cik']) != int(cik):
            raise ValueError('FACTS_ISSUER_MISMATCH')
        for taxonomy, concepts in document.get('facts', {}).items():
            for concept, fact in concepts.items():
                for unit, rows in fact.get('units', {}).items():
                    target = merged['facts'].setdefault(taxonomy, {}).setdefault(concept, dict(units={}))["units"].setdefault(unit, [])
                    for row in rows:
                        key = (taxonomy, concept, unit, json.dumps(row, sort_keys=True))
                        if key not in seen:
                            seen.add(key); target.append(deepcopy(row))
    return merged


def build(coverage, *, root=ROOT, supplements=(), fiscal_quarters=False, identity_candidates=None):
    coverage = deepcopy(coverage)
    identity_sources = {}
    if identity_candidates is not None:
        for ref in identity_candidates['source_hashes'].values():
            raw = (root/ref['path']).read_bytes()
            if sha256(raw).hexdigest() != ref['sha256']:
                raise ValueError('IDENTITY_CANDIDATE_SOURCE_CHANGED')
            identity_sources[ref['path']] = ref['sha256']
        for item in identity_candidates['rows']:
            for window in coverage['windows']:
                if window.get('inputs') != identity_candidates['source_hashes']['inputs']:
                    continue
                for row in window['rows']:
                    if row['security_id'] != item['research_security_id']:
                        continue
                    if row.get('cik') and row['cik'] != item['cik']:
                        raise ValueError('IDENTITY_CANDIDATE_CIK_CONFLICT')
                    row.update(cik=item['cik'], cik_mapping_status=item['mapping_status'],
                               cik_proven_in_frozen_identity=False)
                    name = 'data/cache/candidate_pools/ndx_fundamentals/raw_companyfacts/CIK'+item['cik']+'.json'
                    if (root/name).is_file():
                        digest = sha256((root/name).read_bytes()).hexdigest()
                        row.setdefault('companyfacts_sources', []).append(dict(path=name, sha256=digest, cik=item['cik']))
    extractor = extract
    if fiscal_quarters:
        from scripts.extract_sec_quarter_events_v2 import extract as extractor
    references, sources = {}, {}
    for window in coverage['windows']:
        for field in ('inputs', 'book'):
            ref = window.get(field)
            if ref and sha256((root/ref['path']).read_bytes()).hexdigest() != ref['sha256']:
                raise ValueError('FROZEN_WINDOW_SOURCE_CHANGED')
        for row in window['rows']:
            if not row.get('in_price_domain') or not row.get('cik'):
                continue
            selected = references.setdefault(row['cik'], dict(facts={}, submissions={}))
            for field, kind in [('companyfacts_sources', 'facts'), ('submissions_sources', 'submissions')]:
                for ref in row.get(field, []):
                    path, digest = ref['path'], ref['sha256']
                    if path in sources and sources[path] != digest:
                        raise ValueError('INPUT_REFERENCE_HASH_CONFLICT')
                    selected[kind][path] = digest; sources[path] = digest
    for ref in supplements:
        match = re.fullmatch(r'https://data\.sec\.gov/(api/xbrl/companyfacts|submissions)/CIK(\d{10})(-submissions-\d{3})?\.json', ref['url'])
        if not match or ref.get('status') != 200:
            raise ValueError('SUPPLEMENT_OFFICIAL_URL_REQUIRED')
        kind = 'facts' if match[1] == 'api/xbrl/companyfacts' else 'submissions'
        cik = match[2]
        if ref.get('cik', cik) != cik or cik not in references:
            raise ValueError('SUPPLEMENT_CIK_OUTSIDE_DOMAIN')
        path, digest = ref['path'], ref['sha256']
        if path in sources and sources[path] != digest:
            raise ValueError('INPUT_REFERENCE_HASH_CONFLICT')
        sources[path] = digest; references[cik][kind][path] = digest
    documents = {}
    for name, digest in sources.items():
        raw = (root/name).read_bytes()
        if sha256(raw).hexdigest() != digest:
            raise ValueError('INPUT_BYTES_CHANGED:' + name)
        documents[name] = json.loads(raw)
    for ref in supplements:
        match = re.fullmatch(r'https://data\.sec\.gov/(api/xbrl/companyfacts|submissions)/CIK(\d{10})(-submissions-\d{3})?\.json', ref['url'])
        document = documents[ref['path']]
        if match[3]:
            filename = ref['url'].rsplit('/', 1)[-1]
            known = [item['name'] for name in references[match[2]]['submissions']
                     for item in documents[name].get('filings', {}).get('files', [])]
            if filename not in known or 'accessionNumber' not in document:
                raise ValueError('SUPPLEMENT_ARCHIVE_PARENT_BINDING_REQUIRED')
        elif int(document.get('cik', -1)) != int(match[2]):
            raise ValueError('SUPPLEMENT_DOCUMENT_CIK_MISMATCH')
    issuers, acceptance_days = {}, {}
    for cik, refs in sorted(references.items()):
        submissions = [documents[name] for name in sorted(refs['submissions'])]
        days = {}
        for document in submissions:
            recent = document.get('filings', {}).get('recent', document)
            for i, acc in enumerate(recent.get('accessionNumber', [])):
                try:
                    accepted = timestamp(recent['acceptanceDateTime'][i])
                except (ValueError, TypeError, KeyError, IndexError):
                    continue
                days.setdefault(acc, set()).add(accepted.astimezone(ZoneInfo('America/New_York')).date().isoformat())
        acceptance_days[cik] = days
        if not refs['facts'] or not submissions:
            result = dict(events=[], rejected=[dict(reason='FACTS_OR_SUBMISSIONS_MISSING', accession=None)])
        else:
            merged = merge_facts(cik, [documents[name] for name in sorted(refs['facts'])])
            archive_bindings = [dict(url=ref['url'], source_sha256=ref['sha256'], document_sha256=sha256(
                json.dumps(documents[ref['path']], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest())
                for ref in supplements if ref['path'] in refs['submissions']]
            result = extractor(merged, submissions, archive_bindings=archive_bindings)
        issuers[cik] = dict(result, inputs=refs,
            rejected_counts=dict(Counter(r['reason'] for r in result['rejected'])))
    windows = []
    for window in coverage['windows']:
        start, end = window['start'], window['end']
        rows, event_keys, accession_keys, rejected_keys = [], set(), set(), set()
        covered_ciks, rejection_counts = set(), Counter()
        for source in window['rows']:
            if not source.get('in_price_domain'):
                continue
            cik = source.get('cik'); issuer = issuers.get(cik, dict(events=[], rejected=[]))
            indices = [i for i, event in enumerate(issuer['events']) if start <=
                       timestamp(event['acceptance']).astimezone(ZoneInfo('America/New_York')).date().isoformat() <= end]
            rejected = []
            unknown = 0
            for index, item in enumerate(issuer['rejected']):
                dates = acceptance_days.get(cik, {}).get(item.get('accession'), set())
                if not dates:
                    unknown += 1
                elif any(start <= day <= end for day in dates):
                    rejected.append(index)
                    if (cik, index) not in rejected_keys:
                        rejected_keys.add((cik, index)); rejection_counts[item['reason']] += 1
            for index in indices:
                event_keys.add((cik, index)); accession_keys.add((cik, issuer['events'][index]['accession']))
            if indices: covered_ciks.add(cik)
            rows.append(dict(security_id=source['security_id'], tickers=source.get('tickers'), cik=cik,
                identity_status=source.get('cik_mapping_status'),
                cik_proven_in_frozen_identity=source.get('cik_proven_in_frozen_identity', False),
                candidate_event_indices=indices, rejected_indices_in_window=rejected,
                rejected_without_assignable_acceptance=unknown,
                status='FACT_CANDIDATES_ONLY' if indices else 'NO_ADMITTED_QUARTER_CANDIDATE',
                signal=False, original_filing_text_verified=False))
        windows.append(dict(window=window['window'], start=start, end=end,
            interval_semantics='Inclusive New York calendar dates of exact SEC acceptance; not release/return dates.',
            frozen_inputs=window.get('inputs'), frozen_book=window.get('book'),
            price_domain_securities=len(rows), securities_with_candidates=sum(bool(r['candidate_event_indices']) for r in rows),
            unique_ciks_with_candidates=len(covered_ciks), unique_fact_candidates=len(event_keys),
            unique_accessions=len(accession_keys), rejection_counts=dict(rejection_counts),
            unsupported_calendar_quarter_count=rejection_counts['UNSUPPORTED_OR_INVALID_QUARTER'], rows=rows))
    return dict(schema='HISTORICAL_SEC_FACT_INVENTORY_V1', quarter_policy='FISCAL_DIRECT_V2' if fiscal_quarters else 'CALENDAR_DIRECT_V1', source_hashes=sources, identity_source_hashes=identity_sources, issuers=issuers, windows=windows,
        issuer_count=len(issuers), extracted_ciks=sum(bool(i['events']) for i in issuers.values()),
        limitations=['Full supplied price domain, not a holdings or performance-based subset.',
            'Ticker-derived historical CIK matches remain leads; facts are not admitted security-level trading signals.',
            'Multiple cache facts are unioned; value/submission conflicts are rejected rather than latest-wins.',
            'Quarter policy is explicit; unsupported count is concept/accession rejection count, not unique filings.',
            'Unknown acceptance exclusions cannot be assigned to a historical window; shown separately per row.',
            'Original filing text, earliest release time and historical API availability remain unverified.',
            'No network, model invocation, trading, economic backtest or production mutation.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coverage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--supplements', type=Path, action='append', default=[])
    parser.add_argument('--identity-candidates', type=Path)
    parser.add_argument('--fiscal-quarters', action='store_true')
    args = parser.parse_args()
    raw = args.coverage.read_bytes()
    extra = [(p, p.read_bytes()) for p in args.supplements]
    identity = args.identity_candidates.read_bytes() if args.identity_candidates else None
    result = build(json.loads(raw), supplements=[ref for _, data in extra for ref in json.loads(data)],
                   fiscal_quarters=args.fiscal_quarters, identity_candidates=json.loads(identity) if identity else None)
    result['supplement_manifests'] = [dict(path=str(p), sha256=sha256(data).hexdigest()) for p, data in extra]
    if identity:
        result['identity_manifest'] = dict(path=str(args.identity_candidates), sha256=sha256(identity).hexdigest())
    result['coverage_input'] = dict(path=str(args.coverage), sha256=sha256(raw).hexdigest())
    extractor = 'scripts/extract_sec_quarter_events_v2.py' if args.fiscal_quarters else 'scripts/extract_sec_quarter_events_v1.py'
    result['extractor_source'] = dict(path=extractor, sha256=sha256((ROOT/extractor).read_bytes()).hexdigest())
    result['extractor_dependency_source'] = dict(path='scripts/extract_sec_quarter_events_v1.py',
        sha256=sha256((ROOT/'scripts/extract_sec_quarter_events_v1.py').read_bytes()).hexdigest())
    result['builder_sha256'] = sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('issuer_count', 'extracted_ciks')}))
    for window in result['windows']:
        print(json.dumps({k: v for k, v in window.items() if k != 'rows'}))


if __name__ == '__main__': main()
