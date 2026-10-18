"""Independent control audit v2: exact empty-account risk, without engine replay."""
from decimal import localcontext
from types import FunctionType
from backtest import ndx_fixed_control_accounting_independent_audit_research as prior


def observed_risk(saved,shares,marks,chains,contract):
    prior.counts(shares)
    # The frozen engine emits its ordinary all-cash snapshot before its private
    # control risk callback is ever called. Zero-valued slots are NOT empty.
    if not shares and prior.exact(saved,{'all_passed':False,'checks':{'ALL_CASH':False}}):
        if marks!={}:raise ValueError('Empty account cannot carry security marks')
        return
    return prior.observed_risk(saved,shares,marks,chains,contract)


def audit(*,execution,calendar,schedule,prices,risk_chains_by_decision,contract):
    namespace=dict(prior._audit.__globals__)
    namespace['observed_risk']=observed_risk
    bound=FunctionType(prior._audit.__code__,namespace,prior._audit.__name__,prior._audit.__defaults__,prior._audit.__closure__)
    with localcontext() as context:
        context.prec=50
        result=bound(execution,calendar,schedule,prices,risk_chains_by_decision,contract)
    result['schema']='FIXED_CONTROL_127_SESSION_INDEPENDENT_DECIMAL_AUDIT_V2'
    result['ordinary_all_cash_snapshot_allowed_only_for_empty_slots']=True
    result['frozen_oracle_global_modified']=False
    return result
