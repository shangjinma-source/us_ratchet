"""Pure cash-and-stock merger economic rights; no trading or payment simulation.

Caller binds identities and effective-time evidence. ANSS closing terms are
199.91 USD + 0.3399 SNPS per eligible share, not the original 197 + 0.345.
This generic component does not authenticate any merger or infer delivery.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction


def _amount(value, positive=False):
    if isinstance(value, bool):
        raise ValueError('Boolean economic amount')
    number = Fraction(str(value))
    if number < 0 or positive and number == 0:
        raise ValueError('Invalid economic amount')
    return number


def _date(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Canonical date required')
    return value


def _refs(value):
    if not isinstance(value, list) or not value or not all(value):
        raise ValueError('Explicit evidence references required')
    return deepcopy(value)


def convert_cash_stock_entitlement(*, state, event, as_of):
    """Return copied state. Never credit cash or delivered successor shares.

    state={cash, shares:{sid:int}, merger_entitlements:[], applied_event_ids:[]}
    event={event_id,old_sid,new_sid,effective_date,effective_time_confirmed,
           eligibility_confirmed,cash_per_share,new_shares_per_old_share,
           source_references}. Confirmation is caller-provided, not certified here.
    All eligible old shares in this state are one holder aggregation; no per-lot
    rounding. Unresolved fractional units remain economic rights, not stock.
    """
    as_of = _date(as_of)
    effective = _date(event['effective_date'])
    if effective > as_of:
        raise ValueError('Future event cannot convert holdings')
    if event.get('effective_time_confirmed') is not True or event.get('eligibility_confirmed') is not True:
        raise ValueError('Effective time and eligible holding confirmation required')
    references = _refs(event['source_references'])
    old, new = event['old_sid'], event['new_sid']
    if not old or not new or old == new or not event['event_id']:
        raise ValueError('Distinct explicit security IDs and event ID required')
    result = deepcopy(state)
    _amount(result['cash'])
    if any(type(q) is not int or q < 0 for q in result['shares'].values()):
        raise ValueError('Initial holdings must be whole nonnegative shares')
    identifiers = result.setdefault('applied_event_ids', [])
    if event['event_id'] in identifiers:
        raise ValueError('Duplicate event application forbidden')
    rights = result.setdefault('merger_entitlements', [])
    if any(r['event_id'] == event['event_id'] for r in rights):
        raise ValueError('Duplicate entitlement forbidden')
    held = result['shares'].get(old, 0)
    cash_rate = _amount(event['cash_per_share'])
    ratio = _amount(event['new_shares_per_old_share'], True)
    total = held * ratio
    whole = int(total)
    fraction = total - whole
    result['shares'][old] = 0
    identifiers.append(event['event_id'])
    rights.append(dict(event_id=event['event_id'], old_sid=old, new_sid=new,
                      effective_date=effective, converted_old_shares=held,
                      cash_per_share=str(cash_rate), new_shares_per_old_share=str(ratio),
                      cash_receivable=str(held * cash_rate), pending_whole_shares=whole,
                      fractional_share_entitlement=str(fraction),
                      fractional_shares_issued=False, cash_payment_date=None, stock_delivery_date=None,
                      source_references=references))
    result.update(research_only=True, execution_blocked=True, external_flow='0',
                  economic_conversion_asof=as_of)
    return result


def value_cash_stock_entitlements(*, state, marks, as_of, fractional_settlements=None):
    """Value rights separately from existing successor holdings, never settle them.

    marks[sid]={date:as_of, price, source_references} must be a same-date mark.
    fractional_settlements[event_id]={known_asof,fraction_reference_close:
       {date,price,source_references},reference_is_previous_closing_session:True,
       fraction_cash_rounding:'CEIL_CENT',source_references,payment_date(optional)}.
    Caller binds the contractual previous closing-session date and price basis.
    Unknown reference/rounding blocks valuation; unknown payment only prevents
    availability, not economic receivable valuation. Taxes/fees are not modelled.
    """
    as_of = _date(as_of)
    copied = deepcopy(state)
    cash = _amount(state['cash'])
    blockers, details = [], []
    stock_value, pending_value, cash_rights, fractional_cash = (Fraction(0) for _ in range(4))

    def marked(sid, units, component):
        if units == 0:
            return Fraction(0)
        try:
            mark = marks[sid]
            if _date(mark['date']) != as_of:
                raise ValueError('Same-date mark required')
            _refs(mark['source_references'])
            return units * _amount(mark['price'], True)
        except (KeyError, ValueError, TypeError, ZeroDivisionError) as error:
            blockers.append(dict(reason='MISSING_OR_INVALID_SAME_DATE_MARK', security_id=sid, component=component, detail=str(error)))
            return None

    for sid, held in state['shares'].items():
        if type(held) is not int or held < 0:
            raise ValueError('Whole nonnegative holdings required')
        value = marked(sid, held, 'EXISTING_TRADABLE_HOLDING')
        if value is not None:
            stock_value += value
    seen = set()
    for right in state.get('merger_entitlements', []):
        identifier = right['event_id']
        if identifier in seen:
            raise ValueError('Duplicate economic rights')
        seen.add(identifier)
        if _date(right['effective_date']) > as_of:
            raise ValueError('Future entitlement in state')
        _refs(right['source_references'])
        cash_rights += _amount(right['cash_receivable'])
        pending = right['pending_whole_shares']
        if type(pending) is not int or pending < 0:
            raise ValueError('Whole pending shares required')
        value = marked(right['new_sid'], pending, 'PENDING_UNDELIVERED_SHARES')
        if value is not None:
            pending_value += value
        fraction = _amount(right['fractional_share_entitlement'])
        if fraction >= 1:
            raise ValueError('Fractional entitlement must be below one share')
        fractional_value = Fraction(0) if fraction == 0 else None
        if fraction:
            settlement = (fractional_settlements or {}).get(identifier)
            try:
                available = settlement is not None and _date(settlement['known_asof']) <= as_of
            except (KeyError, ValueError, TypeError):
                available = False
            if not available:
                blockers.append(dict(event_id=identifier, reason='FRACTIONAL_REFERENCE_OR_ROUNDING_UNRESOLVED'))
            else:
                try:
                    _refs(settlement['source_references'])
                    if settlement['fraction_cash_rounding'] != 'CEIL_CENT' or settlement.get('reference_is_previous_closing_session') is not True:
                        raise ValueError('Contractual rounding and previous closing session required')
                    reference = settlement['fraction_reference_close']
                    if _date(reference['date']) >= right['effective_date']:
                        raise ValueError('Fraction reference must precede closing date')
                    _refs(reference['source_references'])
                    price = _amount(reference['price'], True)
                    unrounded = fraction * price
                    fractional_value = Fraction(-(-unrounded * 100 // 1), 100)
                    fractional_cash += fractional_value
                except (KeyError, ValueError, TypeError, ZeroDivisionError) as error:
                    blockers.append(dict(event_id=identifier, reason='FRACTIONAL_REFERENCE_OR_ROUNDING_UNRESOLVED', detail=str(error)))
        details.append(dict(event_id=identifier, pending_whole_shares=pending,
                            fractional_share_entitlement=str(fraction),
                            fractional_cash_value=str(fractional_value) if fractional_value is not None else None,
                            cash_payment_date=right['cash_payment_date'], stock_delivery_date=right['stock_delivery_date']))
    known = cash + stock_value + pending_value + cash_rights + fractional_cash
    return dict(status='BLOCKED' if blockers else 'VALUED_NONTRADABLE_RECEIVABLE', blockers=blockers,
                as_of=as_of, state=copied, available_cash=str(cash), existing_stock_value=str(stock_value),
                pending_stock_entitlement_value=str(pending_value), merger_cash_receivable=str(cash_rights),
                fractional_cash_receivable=str(fractional_cash), known_component_subtotal=str(known),
                total_equity=None if blockers else str(known), entitlements=details,
                execution_blocked=True, real_orders=False, external_flow='0', taxes_and_costs_modelled=False,
                limitations=['Cash payment and stock delivery are not simulated; receivables and rights remain unavailable.',
                             'Fractional rights never round away or become tradable stock.',
                             'Reference Close precision/provider basis remain caller evidence; no implicit cent rounding of reference price.',
                             'Same-date stock marks value economic rights, not guaranteed realization proceeds.'])
