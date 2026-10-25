"""Date-scoped historical identity validation; never infer aliases by ticker."""
from datetime import date


def canonical_day(value):
    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:
        raise ValueError('CANONICAL_ISO_DATE_REQUIRED')
    return value


def validate_records(records):
    """Records: ticker, issuer_id, security_id, start, end, source_references.

    Inclusive symbol intervals describe one traded security, not issuer returns.
    Different classes of one issuer must retain separate security identifiers.
    Corporate conversions require separate evidence and are not aliases here.
    """
    for row in records:
        if any(not isinstance(row.get(k),str) or not row[k].strip() for k in ('ticker','issuer_id','security_id')):
            raise ValueError('IDENTITY_FIELDS_REQUIRED')
        refs=row.get('source_references')
        if not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or not ref.strip() for ref in refs):
            raise ValueError('SOURCE_REFERENCE_LIST_REQUIRED')
        if canonical_day(row['start']) > canonical_day(row['end']):
            raise ValueError('INVALID_IDENTITY_INTERVAL')
    for index,left in enumerate(records):
        for right in records[index+1:]:
            if left['security_id']==right['security_id'] and left['issuer_id']!=right['issuer_id']:
                raise ValueError('SECURITY_ISSUER_CONFLICT')
            overlap=max(left['start'],right['start'])<=min(left['end'],right['end'])
            if overlap and left['ticker']==right['ticker']:
                raise ValueError('OVERLAPPING_SYMBOL_IDENTITY')
    return records


def resolve_identity(records, ticker, asof):
    validate_records(records)
    canonical_day(asof)
    matches=[r for r in records if r['ticker']==ticker and r['start']<=asof<=r['end']]
    if len(matches)!=1:
        raise ValueError('NO_UNIQUE_DATED_IDENTITY:'+ticker+':'+asof)
    return dict(matches[0])


def validate_claim(records, *, ticker, asof, issuer_id, security_id):
    resolved=resolve_identity(records,ticker,asof)
    if (resolved['issuer_id'],resolved['security_id'])!=(issuer_id,security_id):
        raise ValueError('DATED_IDENTITY_CLAIM_MISMATCH')
    return resolved
