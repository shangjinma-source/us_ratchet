"""Offline direct fiscal-quarter SEC candidates. No trading or earliest-release claim."""
import argparse
from calendar import monthrange
from datetime import date, datetime
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

import sys
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.extract_sec_quarter_events_v1 import validate_submission_archives

CONCEPTS = ('RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'NetIncomeLoss')


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('EXACT_ACCEPTANCE_REQUIRED')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if 'T' not in value or result.utcoffset() is None:
        raise ValueError('EXACT_ACCEPTANCE_REQUIRED')
    return result


def extract(companyfacts, submissions, *, concepts=CONCEPTS, unit='USD', cutoff=None, archive_bindings=()):
    """Unique direct 70-105 day fiscal-quarter 10-Q scope; comparative values from that accession.

    A current snapshot's frame/fy never selects a historical value. The optional
    cutoff admits only filings accepted by that instant; unknown acceptance is
    never imputed from filingDate. Quarterly 10-K derivation is out of scope.
    """
    validate_submission_archives(companyfacts, submissions, archive_bindings)
    rejected, events = [], []
    until = timestamp(cutoff) if cutoff is not None else None
    filings, conflicts = {}, set()
    for document in submissions:
        if 'cik' in document and int(document['cik']) != int(companyfacts['cik']):
            raise ValueError('ISSUER_CIK_MISMATCH')
        recent = document.get('filings', {}).get('recent', document)
        accessions = recent.get('accessionNumber', [])
        for index, accession in enumerate(accessions):
            row = {key: values[index] for key, values in recent.items()
                   if isinstance(values, list) and index < len(values)}
            selected = {key: row.get(key) for key in
                        ('accessionNumber', 'acceptanceDateTime', 'reportDate', 'form')}
            if accession in filings and filings[accession] != selected:
                conflicts.add(accession)
            filings[accession] = selected
    facts = companyfacts.get('facts', {}).get('us-gaap', {})
    def reject(reason, accession=None, concept=None, **details):
        rejected.append(dict(reason=reason, accession=accession, concept=concept, **details))
    for concept in concepts:
        rows = facts.get(concept, {}).get('units', {}).get(unit)
        if rows is None:
            reject('CONCEPT_UNIT_UNAVAILABLE', concept=concept, unit=unit)
            continue
        by_accession = {}
        for row in rows:
            if row.get('form') == '10-Q':
                by_accession.setdefault(row.get('accn'), []).append(row)
        if not by_accession:
            reject('NO_10Q_FACTS_FOR_CONCEPT', concept=concept, unit=unit)
        for accession, group in sorted(by_accession.items()):
            filing = filings.get(accession)
            if accession in conflicts:
                reject('SUBMISSION_CONFLICT', accession, concept); continue
            if filing is None:
                reject('ACCESSION_METADATA_MISSING', accession, concept); continue
            if filing['form'] != '10-Q':
                reject('SUBMISSION_FORM_MISMATCH', accession, concept); continue
            try:
                accepted = timestamp(filing['acceptanceDateTime'])
            except (ValueError, TypeError):
                reject('EXACT_ACCEPTANCE_REQUIRED', accession, concept); continue
            if until is not None and accepted > until:
                reject('AFTER_CUTOFF', accession, concept, acceptance=accepted.isoformat()); continue
            try:
                end = date.fromisoformat(filing['reportDate'])
                if accepted.date() <= end:
                    raise ValueError('ACCEPTANCE_NOT_AFTER_PERIOD')
                spans = set()
                for row in group:
                    try:
                        first, last = date.fromisoformat(row['start']), date.fromisoformat(row['end'])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if 70 <= (last-first).days+1 <= 105:
                        spans.add((first, last))
                current = [span for span in spans if span[1] == end]
                if len(current) != 1:
                    reject('DIRECT_QUARTER_MISSING_OR_AMBIGUOUS', accession, concept); continue
                first, last = current[0]
                duration = (last-first).days+1
                previous = [span for span in spans if 350 <= (end-span[1]).days <= 380
                            and abs((span[1]-span[0]).days+1-duration) <= 7]
                if len(previous) != 1:
                    reject('PRIOR_QUARTER_MISSING_OR_AMBIGUOUS', accession, concept); continue
                periods = tuple((a.isoformat(), b.isoformat()) for a, b in (current[0], previous[0]))
            except (ValueError, TypeError):
                reject('UNSUPPORTED_OR_INVALID_QUARTER', accession, concept); continue
            values = []
            for first, last in periods:
                matching = [r for r in group if r.get('start') == first and r.get('end') == last]
                if not matching:
                    reject('DIRECT_QUARTER_MISSING_NO_YTD_DERIVATION', accession, concept,
                           start=first, end=last); break
                try:
                    if any(type(r['val']) not in (int, float) for r in matching):
                        raise ValueError('NONNUMERIC')
                    distinct = {Fraction(str(r['val'])) for r in matching}
                except (ValueError, KeyError, ZeroDivisionError):
                    reject('INVALID_FACT_VALUE', accession, concept, start=first, end=last); break
                if len(distinct) != 1:
                    reject('CONFLICTING_SAME_PERIOD_VALUES', accession, concept, start=first, end=last); break
                values.append(distinct.pop())
            if len(values) != 2:
                continue
            current, previous = values
            delta = current-previous
            events.append(dict(schema='SEC_DIRECT_FISCAL_QUARTER_CANDIDATE_V2', extraction_policy='UNIQUE_70_105_DAY_DIRECT_10Q_PRIOR_350_380_DAY_DURATION_DIFF_LE7', cik=companyfacts['cik'],
                accession=accession, acceptance=accepted.isoformat(), acceptance_raw=filing['acceptanceDateTime'],
                concept=concept, unit=unit, current_period=dict(start=periods[0][0], end=periods[0][1]),
                prior_period=dict(start=periods[1][0], end=periods[1][1]),
                current_value=str(current), prior_comparative_value=str(previous), absolute_change=str(delta),
                yoy_fraction=str(delta/previous) if previous > 0 else None,
                comparison_semantics='POSITIVE_BASE_GROWTH' if previous > 0 else
                    'NONPOSITIVE_BASE_ABSOLUTE_CHANGE_ONLY',
                prior_value_basis='COMPARATIVE_REPORTED_IN_SAME_ACCESSION',
                signal=False, original_filing_text_verified=False, earliest_publication_verified=False))
    return dict(schema='SEC_QUARTER_EXTRACTION_V2', events=events, rejected=rejected, cutoff=cutoff,
        coverage='Supplied companyfacts and accession metadata only; unique direct fiscal 10-Q quarters; 70-105 days, prior end 350-380 days earlier, duration difference at most 7 days.',
        limitations=['Acceptance is SEC submission time, not earliest earnings release or historical API availability.',
            'Current API observations may reflect later extraction changes; original filing context is unverified.',
            'Same-accession comparatives can be recast; do not mix them with original prior-year claims.',
            'No derived Q4, YTD subtraction, ambiguous periods, estimates, trading signal or backtest.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--companyfacts', type=Path, required=True)
    parser.add_argument('--submissions', type=Path, action='append', required=True)
    parser.add_argument('--concept', action='append')
    parser.add_argument('--unit', default='USD')
    parser.add_argument('--cutoff')
    parser.add_argument('--submission-receipts', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = [args.companyfacts, *args.submissions]
    contents = [p.read_bytes() for p in paths]
    bindings = []
    if args.submission_receipts:
        for ref in json.loads(args.submission_receipts.read_bytes()):
            for raw in contents[1:]:
                if ref.get('status') == 200 and sha256(raw).hexdigest() == ref.get('sha256'):
                    document = json.loads(raw)
                    bindings.append(dict(url=ref['url'], source_sha256=ref['sha256'], document_sha256=sha256(
                        json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()))
    result = extract(json.loads(contents[0]), [json.loads(b) for b in contents[1:]],
                     concepts=args.concept or CONCEPTS, unit=args.unit, cutoff=args.cutoff, archive_bindings=bindings)
    if args.submission_receipts:
        result['submission_receipts_sha256'] = sha256(args.submission_receipts.read_bytes()).hexdigest()
    result['source_hashes'] = {str(p): sha256(raw).hexdigest() for p, raw in zip(paths, contents)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(events=len(result['events']), rejected=len(result['rejected']), output=str(args.output))))


if __name__ == '__main__':
    main()
