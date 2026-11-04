"""Model-only scheduled context binding; never extend a news or price deadline."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import re
from core.news_investment_review_v1 import moment, require


def attach_scheduled_context(payload, context, now):
    result = deepcopy(payload)
    if context is None:
        return result
    require(context.get('schema') == 'SCHEDULED_EARNINGS_CONTEXT_V1' and
            context.get('changes_strategy') is False and
            context.get('calendar_coverage_complete') is False and
            context.get('status') in {'CONTEXT_ONLY', 'REVIEW_REQUIRED'}, 'SCHEDULE_CONTEXT_REQUIRED')
    positions = {p['security_id']: p['ticker'] for p in payload['positions']}
    events = context['events']
    require(isinstance(events, list) and len(events) <= 4, 'SCHEDULE_CONTEXT_LIMIT')
    require(context['status'] != 'REVIEW_REQUIRED' or not events, 'SCHEDULE_CONFLICT_HAS_EVENTS')
    seen = set()
    current = moment(now)
    for event in events:
        require(event['security_id'] in positions and positions[event['security_id']] == event['ticker'],
                'SCHEDULE_POSITION_MISMATCH')
        require(event['source_id'] not in seen, 'SCHEDULE_DUPLICATE_EVENT')
        seen.add(event['source_id'])
        require(event['role'] == 'SCHEDULED_EVENT' and event['event_kind'] == 'EARNINGS_CALL' and
                event['timestamp_scope'] == 'ANNOUNCED_CALL_NOT_FIRST_REPORT_PUBLICATION' and
                event['eligible_as_new_trigger'] is False and event['may_refresh_event_window'] is False and
                event['executable'] is False and event['automatic_trade_action'] is None,
                'SCHEDULE_ROLE_INVALID')
        require(all(re.fullmatch('[a-f0-9]{64}', event[name]) for name in ('raw_sha256', 'text_sha256')),
                'SCHEDULE_SOURCE_HASH_REQUIRED')
        publication, observed, scheduled = (moment(event[name]) for name in
                                           ('published_at', 'observed_at', 'scheduled_at'))
        require(publication <= observed <= current < scheduled and
                current-observed <= timedelta(hours=24), 'SCHEDULE_CONTEXT_EXPIRED')
    result['scheduled_context'] = deepcopy(context)
    return result


def context_digest(context):
    return sha256(json.dumps(context, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':')).encode()).hexdigest()
