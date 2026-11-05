"""Exact AZN half-right zero-recovery research assumption; never cash settlement."""
from copy import deepcopy
from fractions import Fraction as F
OLD='security:0000901832:046353108';NEW='internal:issuer:0000901832:ORDINARY_USD025';DAY='2026-02-02';EVENT='azn-dtc-conversion-cap20-zero-recovery-20260202'
KIND='PARENT_FRACTIONAL_CASH_RIGHT'
SCOPE='EXPLICIT_ZERO_RECOVERY_RESEARCH_NOT_KNOWN_CASH_VALUE'
def require(ok,why):
 if not ok:raise ValueError(why)
def validate_rights(rights):
 require(len(rights)==1,'EXACT_ONE_AZN_HALF_RIGHT_REQUIRED');r=rights[0]
 require(r['event_id']==EVENT and r['kind']==KIND and r['security_id']==NEW and F(r['units'])==F(1,2) and r['effective_date']==DAY and r['origin']=='ADS_CONVERSION' and r['tradable'] is False and r['payment_date'] is None and r['delivery_date'] is None,'EXACT_AZN_UNPAID_HALF_RIGHT')
 return r
def value_zero_recovery(original,*,state,marks,as_of,fractional_cash_values=None):
 validate_rights(state.get('distribution_rights',[]));require(as_of>=DAY and not fractional_cash_values,'NO_KNOWN_SETTLEMENT_OR_BEFORE_EVENT');unresolved=original(state=state,marks=marks,as_of=as_of,fractional_cash_values=None)
 require(unresolved['status']=='BLOCKED' and unresolved['blockers']==[dict(reason='FRACTIONAL_CASH_VALUE_UNRESOLVED',event_id=EVENT,kind=KIND)],'ONLY_EXACT_FRACTION_UNKNOWN_CAN_BE_ASSUMED')
 view=deepcopy(state);view['distribution_rights']=[];valued=original(state=view,marks=marks,as_of=as_of,fractional_cash_values=None);require(valued['status']=='VALUED_NONTRADABLE_DISTRIBUTION','TRADABLE_MARKS_REQUIRED')
 valued.update(state=deepcopy(state),valuation_assumption=SCOPE,unresolved_fractional_rights=deepcopy(state['distribution_rights']),original_blockers=unresolved['blockers'],full_account_equity_certified=False,production_eligible=False,assumed_recovery_amount='0',payment_assumed=False)
 return valued
def sizing_view(state):
 view=deepcopy(state)
 if view.get('distribution_rights'):
  validate_rights(view['distribution_rights']);view['distribution_rights']=[]
 return view
def install_book_module(module):
 original_value=module.value_distributions;original_convert=module.convert_dtc_ads
 def valuation(**kwargs):return value_zero_recovery(original_value,**kwargs)
 def conversion(**kwargs):
  event=kwargs['event'];require(event['event_id']==EVENT and event['security_id']==OLD and event['new_security_id']==NEW and kwargs['state']['shares'].get(OLD)==49,'EXACT49_ADS_CONVERSION_ONLY')
  result=original_convert(**kwargs);validate_rights(result['distribution_rights']);require(result['shares'][OLD]==0 and result['shares'][NEW]==24 and result['cash']==kwargs['state']['cash'],'EXACT_CONVERSION_CASH_CONSERVED');return result
 module.value_distributions=valuation;module.convert_dtc_ads=conversion
 return module
