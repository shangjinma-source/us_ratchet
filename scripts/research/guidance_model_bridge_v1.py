"""Offline bridge. Registries must be supplied by an independent reviewer, never the model.

Source registry keyed by model record id: url,text,original_bytes,original_sha256,
text_sha256,full_original_authenticated=True. Authentication and text extraction
fidelity are upstream review obligations; hashing alone does not prove either.
Metadata registry keyed by id: source_sha256,review_reference,fields mapping each
required field to {value,evidence_text}. Evidence must occur in the bound full text.
publication_datetime may instead reference separately reviewed availability evidence
bound to this original document hash. Model contributes ONLY quote/low/high.
"""
from hashlib import sha256
from scripts.research.guidance_numeric_comparator_v1 import compare_guidance, KEYS, _number

FIELDS = (*KEYS, 'status', 'publication_datetime')


def bind_model_row(row, source, metadata, availability_sources=None):
    if not isinstance(source, dict) or source.get('full_original_authenticated') is not True:
        raise ValueError('FULL_ORIGINAL_NOT_AUTHENTICATED')
    original = source.get('original_bytes')
    text = source.get('text')
    if (not isinstance(original, bytes) or not original or not isinstance(text, str)
            or sha256(original).hexdigest() != source.get('original_sha256')
            or sha256(text.encode()).hexdigest() != source.get('text_sha256')):
        raise ValueError('SOURCE_CONTENT_BINDING_FAILED')
    digest = source['text_sha256']
    if (not isinstance(metadata, dict) or metadata.get('source_sha256') != digest
            or not metadata.get('review_reference')):
        raise ValueError('INDEPENDENT_METADATA_REVIEW_REQUIRED')
    record = {}
    for name in FIELDS:
        item = metadata.get('fields', {}).get(name, {})
        evidence = item.get('evidence_text')
        evidence_body = text
        if name == 'publication_datetime' and item.get('availability_reference'):
            availability = (availability_sources or {}).get(item['availability_reference'], {})
            body = availability.get('text')
            if (not isinstance(body, str) or not body
                    or sha256(body.encode()).hexdigest() != availability.get('text_sha256')
                    or availability.get('original_sha256') != source['original_sha256']
                    or availability.get('document_url') != source['url']
                    or availability.get('reviewed_available_at') != item.get('value')
                    or not availability.get('review_reference')
                    or not str(availability.get('url', '')).startswith('https://')):
                raise ValueError('AVAILABILITY_EVIDENCE_BINDING_FAILED')
            evidence_body = body
        if not item.get('value') or not isinstance(evidence, str) or not evidence or evidence not in evidence_body:
            raise ValueError('REVIEWED_METADATA_MISSING_' + name.upper())
        record[name] = item['value']
    quote = row.get('quote')
    if not isinstance(quote, str) or not quote or text.count(quote) != 1:
        raise ValueError('UNIQUE_MODEL_QUOTE_REQUIRED')
    start = text.index(quote)
    record.update(source_url=source['url'], source_sha256=digest,
                  quote_start=start, quote_end=start + len(quote))
    for name in ('low', 'high'):
        token = row.get(name)
        _number(token)
        if quote.count(token) != 1:
            raise ValueError('UNIQUE_NUMERIC_LOCATION_REQUIRED')
        offset = start + quote.index(token)
        record[name] = token
        record[name + '_span'] = [offset, offset + len(token)]
    registered = dict(text=text, url=source['url'], issuer_cik=record['issuer_cik'],
                      publication_datetime=record['publication_datetime'])
    return record, {digest: registered}


def compare_model_rows(previous, current, sources, reviewed_metadata, availability_sources=None):
    try:
        old, old_sources = bind_model_row(previous, sources.get(previous['id']), reviewed_metadata.get(previous['id']), availability_sources)
        new, new_sources = bind_model_row(current, sources.get(current['id']), reviewed_metadata.get(current['id']), availability_sources)
        return compare_guidance(old, new, {**old_sources, **new_sources})
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        return {'status': 'UNKNOWN', 'reason': str(error), 'is_trading_signal': False}
