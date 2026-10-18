"""Wire reviewed segmented quotes and dated distributions; no IO or search."""
from copy import deepcopy
from fractions import Fraction
from backtest.return_priority_monthly_execution_inputs import assemble_monthly_execution_inputs


def assemble_monthly_execution_inputs_v4(prepared):
    payload = deepcopy(prepared)
    pins = payload['source_hashes']
    provenance = payload['source_provenance']

    def references(sid, day):
        row = provenance[sid]
        segments = row.get('segments')
        if segments is None:
            return [row['whole_source']]
        matches = [segment for segment in segments if segment['start'] <= day <= segment['end']]
        if len(matches) != 1:
            raise ValueError('MISSING_OR_OVERLAPPING_SOURCE_SEGMENT:' + sid + ':' + day)
        source = matches[0]['source_path']
        if source not in pins:
            raise ValueError('UNPINNED_SOURCE_SEGMENT:' + source)
        return [source]

    for sid, row in provenance.items():
        for day in payload['ohlc'][sid]:
            references(sid, day)
        if 'segments' in row:
            if not row['segments']:
                raise ValueError('EMPTY_SOURCE_SEGMENTS')
            # Legacy validator needs one pin; this internal bridge is replaced
            # by the exact dated references below, never reported as one source.
            row['whole_source'] = row['segments'][0]['source_path']
    result = assemble_monthly_execution_inputs(payload)
    for window in result['monthly_inputs']:
        for quote in window['valuation_quotes']:
            quote['source_references'] = references(quote['security_id'], window['decision_date'])
    result['price_source_references'] = {
        sid: sorted({ref for day in payload['ohlc'][sid] for ref in references(sid, day)})
        for sid in provenance}
    result['source_provenance'] = deepcopy(prepared['source_provenance'])
    events = deepcopy(prepared['distribution_events'])
    fractions = deepcopy(prepared['distribution_fractional_cash_values'])
    for event_id, by_kind in fractions.items():
        for kind, value in by_kind.items():
            refs = value.get('source_references', [])
            if not refs or any(ref not in pins for ref in refs):
                raise ValueError('UNPINNED_DISTRIBUTION_FRACTION_VALUE:' + event_id + ':' + kind)
    ids = set()
    parent_days = set()
    for event in events:
        key = (event['effective_date'], event['parent_sid'])
        if event['event_id'] in ids or key in parent_days:
            raise ValueError('DUPLICATE_DISTRIBUTION')
        ids.add(event['event_id']); parent_days.add(key)
        if event['timing'] not in ('BEFORE_OPEN', 'AFTER_CLOSE'):
            raise ValueError('EXPLICIT_DISTRIBUTION_TIMING_REQUIRED')
        if event['effective_date'] not in result['session_dates'][1:]:
            raise ValueError('DISTRIBUTION_OUTSIDE_EXECUTION_SESSIONS')
        refs = event.get('source_references', [])
        if not refs or any(ref not in pins for ref in refs):
            raise ValueError('UNPINNED_DISTRIBUTION_EVENT')
        if any(event[sid] not in payload['metadata'] for sid in ('parent_sid', 'post_parent_sid', 'child_sid')):
            raise ValueError('MISSING_DISTRIBUTION_SECURITY')
        if isinstance(event['parent_ratio'], bool) or Fraction(event['parent_ratio']) <= 0:
            raise ValueError('INVALID_PARENT_RATIO')
        if any(a['date'] == event['effective_date'] and a['security_id'] == event['parent_sid'] for a in result['provider_actions']):
            raise ValueError('DOUBLE_APPLIED_PARENT_ACTION')
        result['provider_actions'].append(dict(type='distribution', date=event['effective_date'],
            security_id=event['parent_sid'], post_parent_sid=event['post_parent_sid'],
            parent_ratio=event['parent_ratio'], timing=event['timing'], source_references=refs))
    result.update(distribution_events=events, distribution_fractional_cash_values=fractions,
                  quote_source_scope='EXPLICIT_WHOLE_SOURCE_OR_NONOVERLAPPING_WHOLE_SEGMENTS')
    unsupported = deepcopy(prepared.get('unsupported_conversions', []))
    for event in unsupported:
        refs = event.get('source_references', [])
        if not refs or any(ref not in pins for ref in refs):
            raise ValueError('UNPINNED_UNSUPPORTED_CONVERSION')
        if event['old_sid'] not in payload['metadata'] or event['new_sid'] not in payload['metadata']:
            raise ValueError('MISSING_CONVERSION_SECURITY')
        guard = dict(date=event['date'], security_id=event['old_sid'],
                     type='UNSUPPORTED_SECURITY_CONVERSION', source_references=refs,
                     conversion_details=deepcopy(event))
        result['actions'].append(guard)
        result['provider_actions'].append(deepcopy(guard))
    result['unsupported_conversions'] = unsupported
    supported = deepcopy(prepared.get('supported_conversions', []))
    account_model = prepared.get('account_model')
    if supported and account_model != 'DTC_BENEFICIAL_INTERESTS':
        raise ValueError('EXPLICIT_DTC_ACCOUNT_MODEL_REQUIRED')
    for event in supported:
        refs = event.get('source_references', [])
        if not refs or any(ref not in pins for ref in refs):
            raise ValueError('UNPINNED_SUPPORTED_CONVERSION')
        if event.get('type') != 'ads_conversion' or event.get('delivery_model') != account_model:
            raise ValueError('UNSUPPORTED_CONVERSION_BINDING')
        if event['security_id'] not in payload['metadata'] or event['new_security_id'] not in payload['metadata']:
            raise ValueError('MISSING_CONVERSION_SECURITY')
        if any(a['date'] == event['date'] and a['security_id'] == event['security_id'] for a in result['provider_actions']):
            raise ValueError('DUPLICATE_CONVERSION_OR_OTHER_ACTION')
        result['actions'].append(deepcopy(event))
        result['provider_actions'].append(deepcopy(event))
    result.update(supported_conversions=supported, account_model=account_model)
    result['limitations'].append('Distribution timing and pending rights are mandatory v4 kernel inputs; segmented quotes retain dated source provenance.')
    return result
