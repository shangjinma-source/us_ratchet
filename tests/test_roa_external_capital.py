import unittest
from copy import deepcopy
from datetime import datetime,timezone
from core.strategy_account_ledger import create_account,apply_event
from core.broker_internal_transfers import create_transfers
from core.roa_external_capital import identify_external_capital

class CapitalTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,11,15,12,tzinfo=timezone.utc)
  self.current=create_account('fixture')
  self.add(dict(event_id='initial',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
  self.baseline=deepcopy(self.current);self.documents={};self.receipts={}
 def add(self,event):
  self.current,_=apply_event(self.current,event,expected_revision=self.current['revision'])
 def cash(self,key,amount,items):
  before=self.current['revision'];old=self.current['total_uninvested_cash']
  self.add(dict(event_id=key,kind='CASH_CONFIRM',amount=amount,cash_basis='TOTAL_UNINVESTED'))
  from fractions import Fraction as F
  self.documents[key]=dict(schema='CASH_CHANGE_CLASSIFICATION_V1',account_id='fixture',cash_event_id=key,before_revision=before,after_revision=self.current['revision'],net_change=str(F(amount)-F(old)),items=[dict(item_id=str(i),kind=kind,amount=value,effective_at='2026-11-15T11:00:00+00:00') for i,(kind,value) in enumerate(items)])
  self.receipts[key]='2026-11-15T11:30:00+00:00'
 def identify(self,cutoff='initial'):
  transfers=create_transfers('fixture')
  context=dict(transfer_state=transfers,expected_transfer_revision=transfers['revision'],baseline_at='2026-11-15T10:00:00+00:00',valued_at=self.now,links={},confirmation_times=self.receipts)
  return identify_external_capital(baseline=self.baseline,current=self.current,documents=self.documents,transfer_context=context,after_cash_event_id=cutoff,now=self.now)
 def test_deposit_stable_identity_and_no_account_write(self):
  self.cash('cash1','1500',[('DEPOSIT','500')]);before=deepcopy(self.current)
  first=self.identify();self.assertEqual(first,self.identify());self.assertEqual(first['positive_external_capital'],'500');self.assertFalse(first['executable']);self.assertEqual(before,self.current)
 def test_income_and_fees_are_not_new_principal(self):
  self.cash('cash1','1510',[('DEPOSIT','500'),('INCOME','20'),('FEE','-10')]);self.assertEqual(self.identify()['positive_external_capital'],'500')
 def test_withdrawal_offsets_principal(self):
  self.cash('cash1','1500',[('DEPOSIT','500')]);self.cash('cash2','900',[('WITHDRAWAL','-600')]);self.assertEqual(self.identify()['positive_external_capital'],'0')
 def test_unknown_increase_not_deposit(self):
  self.cash('cash1','1500',[('DEPOSIT','500')]);self.documents={}
  with self.assertRaisesRegex(ValueError,'UNCLASSIFIED_CASH_CHANGE'):self.identify()
 def test_cutoff_excludes_previously_included_deposit(self):
  self.cash('cash1','1500',[('DEPOSIT','500')]);self.assertEqual(self.identify('cash1')['items'],[])
 def test_repair_and_changed_amount_rejected(self):
  self.cash('cash1','1500',[('CORRECTION','500')])
  with self.assertRaisesRegex(ValueError,'ACCOUNT_FACT_REPAIR_REQUIRED'):self.identify()
  self.documents['cash1']['items'][0].update(kind='DEPOSIT',amount='600')
  with self.assertRaisesRegex(ValueError,'ITEM_TOTAL_MISMATCH'):self.identify()
 def test_future_receipt_fact_rejected(self):
  self.cash('cash1','1500',[('DEPOSIT','500')]);self.receipts['cash1']='2026-11-15T10:30:00+00:00'
  with self.assertRaisesRegex(ValueError,'FLOW_AFTER_CASH_CONFIRMATION'):self.identify()
 def test_prebaseline_flow_not_new_capital(self):
  self.cash('cash1','1500',[('DEPOSIT','500')]);self.documents['cash1']['items'][0]['effective_at']='2026-11-15T09:00:00+00:00'
  with self.assertRaisesRegex(ValueError,'PRE_BASELINE_FACT'):self.identify()
 def test_internal_transfer_arrival_is_not_external_deposit(self):
  from core.broker_internal_transfers import apply_transfer_event
  transfers=create_transfers('fixture')
  sent=dict(event_id='sent',transfer_id='move',kind='SENT',source='HSBC',destination='USMART',principal='600',fee='0',occurred_at='2026-11-15T10:10:00+00:00')
  arrived=dict(event_id='arrived',transfer_id='move',kind='RECEIVED',amount='600',occurred_at='2026-11-15T10:20:00+00:00')
  for event in (sent,arrived):transfers=apply_transfer_event(transfers,event,expected_revision=transfers['revision'],now=self.now)
  self.add(dict(event_id='out',kind='CASH_CONFIRM',amount='400',cash_basis='TOTAL_UNINVESTED'))
  self.add(dict(event_id='in',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
  context=dict(transfer_state=transfers,expected_transfer_revision=transfers['revision'],baseline_at='2026-11-15T10:00:00+00:00',valued_at=self.now,links={'out':['sent'],'in':['arrived']},confirmation_times={'out':'2026-11-15T10:15:00+00:00','in':'2026-11-15T10:25:00+00:00'})
  result=identify_external_capital(baseline=self.baseline,current=self.current,documents={},transfer_context=context,after_cash_event_id='initial',now=self.now)
  self.assertEqual(result['positive_external_capital'],'0');self.assertEqual(result['items'],[])
  context['links']={}
  with self.assertRaisesRegex(ValueError,'UNLINKED_TRANSFER_EVENTS'):
   identify_external_capital(baseline=self.baseline,current=self.current,documents={},transfer_context=context,after_cash_event_id='initial',now=self.now)
if __name__=='__main__':unittest.main()
