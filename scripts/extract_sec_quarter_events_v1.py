"""Offline calendar-quarter SEC candidates. No trading or earliest-release claim."""
import argparse
from calendar import monthrange
from datetime import date, datetime
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

CONCEPTS = ('RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'NetIncomeLoss')


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('EXACT_ACCEPTANCE_REQUIRED')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if 'T' not in value or result.utcoffset() is None:
        raise ValueError('EXACT_ACCEPTANCE_REQUIRED')
    return result


def extract(companyfacts, submissions, *, concepts=CONCEPTS, unit='USD', cutoff=None):
    """Strict calendar Q1-Q3 10-Q scope; comparative values from that accession.

    A current snapshot's frame/fy never selects a historical value. The optional
    cutoff admits only filings accepted by that instant; unknown acceptance is
    never imputed from filingDate. Quarterly 10-K derivation is out of scope.
    """
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
                if end.month not in (3, 6, 9) or end.day != monthrange(end.year, end.month)[1]:
                    raise ValueError('NON_CALENDAR_QUARTER')
                start = date(end.year, end.month-2, 1)
                if accepted.date() <= end:
                    raise ValueError('ACCEPTANCE_NOT_AFTER_PERIOD')
            except (ValueError, TypeError):
                reject('UNSUPPORTED_OR_INVALID_QUARTER', accession, concept); continue
            periods = ((start.isoformat(), end.isoformat()),
                       (start.replace(year=start.year-1).isoformat(), end.replace(year=end.year-1).isoformat()))
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
            events.append(dict(schema='SEC_DIRECT_QUARTER_CANDIDATE_V1', cik=companyfacts['cik'],
                accession=accession, acceptance=accepted.isoformat(), acceptance_raw=filing['acceptanceDateTime'],
                concept=concept, unit=unit, current_period=dict(start=periods[0][0], end=periods[0][1]),
                prior_period=dict(start=periods[1][0], end=periods[1][1]),
                current_value=str(current), prior_comparative_value=str(previous), absolute_change=str(delta),
                yoy_fraction=str(delta/previous) if previous > 0 else None,
                comparison_semantics='POSITIVE_BASE_GROWTH' if previous > 0 else
                    'NONPOSITIVE_BASE_ABSOLUTE_CHANGE_ONLY',
                prior_value_basis='COMPARATIVE_REPORTED_IN_SAME_ACCESSION',
                signal=False, original_filing_text_verified=False, earliest_publication_verified=False))
    return dict(schema='SEC_QUARTER_EXTRACTION_V1', events=events, rejected=rejected, cutoff=cutoff,
        coverage='Supplied companyfacts and accession metadata only; calendar Q1-Q3 direct 10-Q quarters.',
        limitations=['Acceptance is SEC submission time, not earliest earnings release or historical API availability.',
            'Current API observations may reflect later extraction changes; original filing context is unverified.',
            'Same-accession comparatives can be recast; do not mix them with original prior-year claims.',
            'No derived Q4, noncalendar periods, estimates, price reactions, trading signal or backtest.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--companyfacts', type=Path, required=True)
    parser.add_argument('--submissions', type=Path, action='append', required=True)
    parser.add_argument('--concept', action='append')
    parser.add_argument('--unit', default='USD')
    parser.add_argument('--cutoff')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = [args.companyfacts, *args.submissions]
    contents = [p.read_bytes() for p in paths]
    result = extract(json.loads(contents[0]), [json.loads(b) for b in contents[1:]],
                     concepts=args.concept or CONCEPTS, unit=args.unit, cutoff=args.cutoff)
    result['source_hashes'] = {str(p): sha256(raw).hexdigest() for p, raw in zip(paths, contents)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(events=len(result['events']), rejected=len(result['rejected']), output=str(args.output))))


if __name__ == '__main__':
    main()
