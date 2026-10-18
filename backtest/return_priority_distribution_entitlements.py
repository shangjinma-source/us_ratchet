"""Pure parent-preserving distributions; no settlement, broker, IO or strategy."""
from copy import deepcopy
from datetime import date
from fractions import Fraction

def _day(v):
    if type(v) is not str or date.fromisoformat(v).isoformat()!=v:raise ValueError('Canonical date required')
    return v

def _number(v):
    if isinstance(v,bool):raise ValueError('Boolean amount')
    n=Fraction(str(v))
    if n<0:raise ValueError('Negative amount')
    return n

def _refs(v):
    if not isinstance(v,list) or not v or not all(isinstance(x,str) and x for x in v):raise ValueError('Evidence references required')
    return deepcopy(v)

def _capital_boundary(state):
    # This module values only delivered holdings and its own distribution rights.
    for key in ('merger_entitlements', 'receivables', 'pending_cash_flows', 'undelivered_rights', 'pending_orders'):
        if state.get(key):raise ValueError('Unsupported capital component: '+key)
    for key in ('receivable', 'reserved_cash'):
        if _number(state.get(key, '0')):raise ValueError('Unsupported capital component: '+key)


def apply_distribution(*, state, event, as_of):
    """Child entitlement first, then optional parent ratio/identity transformation.

    event: event_id/effective_date/parent_sid/child_sid/eligible_parent_quantity,
    child_ratio/parent_ratio/post_parent_sid/source_references and explicit
    eligibility_confirmed, ordered_steps_confirmed, parent_delivered_units_confirmed.
    Eligibility is caller-proven, not inferred from record date or current holdings.
    Caller must cancel pending orders/release reservations before conversion.
    Other unsettled capital components are unsupported and rejected.
    Child units are entirely nontradable. Parent whole units transform only with
    explicit confirmation; parent fractional rights never vanish or become cash.
    """
    _capital_boundary(state)
    _day(as_of)
    if _day(event['effective_date'])>as_of:raise ValueError('Future event')
    for flag in ('eligibility_confirmed','ordered_steps_confirmed','parent_delivered_units_confirmed'):
        if event.get(flag) is not True:raise ValueError('Explicit '+flag+' required')
    refs=_refs(event['source_references'])
    old,child,new=event['parent_sid'],event['child_sid'],event['post_parent_sid']
    if not all(isinstance(s,str) and s for s in (old,child,new)) or child in (old,new):raise ValueError('Distinct explicit child identity required')
    identifier=event['event_id']
    if not isinstance(identifier,str) or not identifier:raise ValueError('Event ID required')
    r=deepcopy(state);_number(r['cash'])
    if any(type(q) is not int or q<0 for q in r['shares'].values()):raise ValueError('Whole shares required')
    applied=r.setdefault('applied_distribution_ids',[])
    if identifier in applied:raise ValueError('Duplicate distribution')
    rights=r.setdefault('distribution_rights',[])
    if any(x['event_id']==identifier for x in rights):raise ValueError('Duplicate rights')
    eligible=event['eligible_parent_quantity']
    if type(eligible) is not int or eligible<0:raise ValueError('Whole explicit eligible quantity required')
    child_ratio,parent_ratio=_number(event['child_ratio']),_number(event['parent_ratio'])
    if child_ratio<=0 or parent_ratio<=0:raise ValueError('Positive ratios required')
    if new!=old and r['shares'].get(new,0):raise ValueError('Parent successor holding conflict')
    # A later action on still-pending distributed units needs its own resolution.
    if any(x['security_id'] in (old,new,child) and _number(x['units']) for x in rights):raise ValueError('Action overlapping pending rights unsupported')
    child_total=eligible*child_ratio
    parent_before=r['shares'].get(old,0);parent_total=parent_before*parent_ratio
    def right(kind,sid,units):
        if units:
            rights.append(dict(event_id=identifier,kind=kind,security_id=sid,units=str(units),effective_date=event['effective_date'],source_references=refs,delivery_date=None,payment_date=None,tradable=False))
    right('CHILD_PENDING_WHOLE',child,Fraction(int(child_total)))
    right('CHILD_FRACTIONAL_CASH_RIGHT',child,child_total-int(child_total))
    if new!=old:r['shares'][old]=0
    r['shares'][new]=int(parent_total)
    right('PARENT_FRACTIONAL_CASH_RIGHT',new,parent_total-int(parent_total))
    applied.append(identifier)
    r['last_distribution_audit']=dict(event_id=identifier,as_of=as_of,eligible_parent_quantity=eligible,parent_actual_quantity_before=parent_before,child_total_units=str(child_total),parent_total_units=str(parent_total),ordered_steps=['CREATE_CHILD_RIGHTS_FROM_ELIGIBILITY','TRANSFORM_EXISTING_PARENT'],cash_credited='0',child_shares_delivered=0,source_references=refs)
    r.update(research_only=True,external_flow='0',real_orders=False)
    return r

def value_distributions(*, state, marks, as_of, fractional_cash_values=None):
    """Same-date marks value whole pending rights. Fractional cash needs explicit
    legally derived amount+source+known_asof, never guessed from current Close.
    Payment/delivery unknown does not prevent known economic value, but prevents
    availability. Sources/eligibility/settlement amounts authenticated by caller.
    """
    _capital_boundary(state)
    _day(as_of);cash=_number(state['cash']);stock=Fraction(0);pending=Fraction(0);fraction_cash=Fraction(0);blockers=[]
    def mark(sid,q,kind):
        if not q:return Fraction(0)
        try:
            m=marks[sid]
            if _day(m['date'])!=as_of:raise ValueError('Same-date mark required')
            _refs(m['source_references']);p=_number(m['price'])
            if p<=0:raise ValueError('Positive mark required')
            return q*p
        except (KeyError,ValueError,TypeError,ZeroDivisionError) as e:
            blockers.append(dict(reason='MISSING_VALID_MARK',security_id=sid,kind=kind,detail=str(e)));return Fraction(0)
    for sid,q in state['shares'].items():
        if type(q) is not int or q<0:raise ValueError('Whole holdings required')
        stock+=mark(sid,q,'DELIVERED')
    seen=set()
    for r in state.get('distribution_rights',[]):
        key=(r['event_id'],r['kind']);_refs(r['source_references'])
        if key in seen:raise ValueError('Duplicate right')
        seen.add(key)
        if _day(r['effective_date'])>as_of:raise ValueError('Future right')
        units=_number(r['units'])
        if r['kind']=='CHILD_PENDING_WHOLE':
            if units.denominator!=1:raise ValueError('Pending whole units required')
            pending+=mark(r['security_id'],units,r['kind'])
        elif r['kind'] in ('CHILD_FRACTIONAL_CASH_RIGHT','PARENT_FRACTIONAL_CASH_RIGHT'):
            if not 0<units<1:raise ValueError('Fraction required')
            value=(fractional_cash_values or {}).get(r['event_id'],{}).get(r['kind'])
            try:
                if value is None or _day(value['known_asof'])>as_of:raise ValueError('Fraction value unknown')
                if value['security_id']!=r['security_id'] or _number(value['units'])!=units:
                    raise ValueError('Fraction settlement entitlement mismatch')
                _refs(value['source_references']);fraction_cash+=_number(value['amount'])
            except (KeyError,TypeError,ValueError,ZeroDivisionError):blockers.append(dict(reason='FRACTIONAL_CASH_VALUE_UNRESOLVED',event_id=r['event_id'],kind=r['kind']))
        else:raise ValueError('Unsupported rights kind')
    known=cash+stock+pending+fraction_cash
    return dict(status='BLOCKED' if blockers else 'VALUED_NONTRADABLE_DISTRIBUTION',state=deepcopy(state),as_of=as_of,available_cash=str(cash),delivered_stock_value=str(stock),pending_child_value=str(pending),fractional_cash_receivable=str(fraction_cash),known_subtotal=str(known),total_equity=None if blockers else str(known),blockers=blockers,real_orders=False,settlement_simulated=False,external_flow='0',taxes_fees_modelled=False)
