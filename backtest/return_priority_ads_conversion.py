"""Conditional DTC ADS conversion; no IO, broker certification or cash settlement."""
from copy import deepcopy
from fractions import Fraction
from datetime import date

ACCOUNT_MODEL = 'DTC_BENEFICIAL_INTERESTS'
TARGET_POLICY = 'FLOOR_PROPORTIONAL_DESIRED_TARGET_RESEARCH_RULE_NOT_ASSET_ROUNDING'

def convert_dtc_ads(*, state, event, as_of, account_model):
    if account_model != ACCOUNT_MODEL or event.get('delivery_model') != ACCOUNT_MODEL:
        raise ValueError('EXPLICIT_DTC_DELIVERY_MODEL_REQUIRED')
    if date.fromisoformat(as_of).isoformat() != as_of or event['date'] != as_of:
        raise ValueError('CONVERSION_DATE_MISMATCH')
    refs = event.get('source_references')
    if not isinstance(refs, list) or not refs or not all(isinstance(x,str) and x for x in refs):
        raise ValueError('CONVERSION_EVIDENCE_REQUIRED')
    old, new, identifier = event['security_id'], event['new_security_id'], event['event_id']
    if not all(isinstance(x,str) and x for x in [old,new,identifier]) or old == new:
        raise ValueError('INVALID_CONVERSION_IDENTITIES')
    ratio = Fraction(str(event['new_shares'])) / Fraction(str(event['old_shares']))
    if ratio != Fraction(1,2): raise ValueError('ONLY_TWO_ADS_TO_ONE_ORDINARY_SUPPORTED')
    if state.get('pending_orders') or Fraction(str(state.get('reserved_cash',0))):
        raise ValueError('CANCEL_ORDERS_BEFORE_CONVERSION')
    r = deepcopy(state)
    applied = r.setdefault('applied_conversion_ids', [])
    if identifier in applied: raise ValueError('DUPLICATE_CONVERSION')
    q = r['shares'].get(old,0)
    if type(q) is not int or q < 0: raise ValueError('INVALID_ADS_QUANTITY')
    if r['shares'].get(new,0): raise ValueError('SUCCESSOR_HOLDING_CONFLICT')
    if any(x['security_id'] in (old,new) for x in r.get('distribution_rights',[])):
        raise ValueError('CONVERSION_OVERLAPS_PENDING_RIGHTS')
    total = q * ratio
    r['shares'][old] = 0
    r['shares'][new] = int(total)
    fraction = total - int(total)
    if fraction:
        r.setdefault('distribution_rights',[]).append(dict(event_id=identifier,
            kind='PARENT_FRACTIONAL_CASH_RIGHT', security_id=new, units=str(fraction),
            effective_date=as_of, source_references=list(refs), delivery_date=None,
            payment_date=None, tradable=False, origin='ADS_CONVERSION'))
    applied.append(identifier)
    r['last_conversion_audit'] = dict(event_id=identifier, old_sid=old,new_sid=new,
        ads_before=q,ordinary_delivered=int(total),fractional_cash_right_units=str(fraction),
        cash_credited='0',delivery_model=ACCOUNT_MODEL,source_references=list(refs))
    return r
