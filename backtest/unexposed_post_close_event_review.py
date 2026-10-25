"""Establish whether a pending after-close event leaves risk prices unchanged.

This is only evidence classification. It neither places orders nor clears the
book's pending coordinate flag. Caller must retain its no-order waiting day.
"""


def review_unexposed_post_close(*, day, state, targets, tracked_securities, events):
    current = [event for event in events
               if event.get('effective_date') == day and event.get('timing') == 'AFTER_CLOSE']
    if not current:
        raise ValueError('AFTER_CLOSE_EVENT_EVIDENCE_REQUIRED')
    if state.get('distribution_rights') or state.get('merger_entitlements'):
        raise ValueError('PENDING_RIGHTS_REQUIRE_REVIEW')
    exposed = set(tracked_securities) | {sid for sid, quantity in targets.items() if quantity}
    exposed |= {sid for sid, quantity in state['shares'].items() if quantity}
    identities = set()
    for event in current:
        identifier = event.get('event_id')
        if not identifier or identifier in identities:
            raise ValueError('UNIQUE_EVENT_REQUIRED')
        identities.add(identifier)
        references = event.get('source_references')
        if not isinstance(references, list) or not references or not all(isinstance(r, str) and r for r in references):
            raise ValueError('EVENT_SOURCE_REQUIRED')
        affected = {event.get(key) for key in ('parent_sid', 'post_parent_sid', 'child_sid')}
        if None in affected or '' in affected:
            raise ValueError('COMPLETE_EVENT_IDENTITIES_REQUIRED')
        if affected & exposed:
            raise ValueError('EXPOSED_POST_CLOSE_EVENT_REQUIRES_REVIEW')
    return dict(status='UNEXPOSED_RISK_DOMAIN_UNCHANGED', event_ids=sorted(identities),
                decision_date=day, orders_permitted=False)
