"""Real temporary account valuations, internal transfers and external cash flows."""
import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from api.strategy_account import StrategyAccountService
from core.broker_internal_transfers import create_transfers, apply_transfer_event
from data.roa_cash_flow.profit import amount_profit

class TransferProfitTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.now=datetime(2026,11,14,0,tzinfo=timezone.utc)
        self.account=StrategyAccountService(database_path=Path(self.directory.name)/'a.sqlite',
            account_id='fixture',resolver=lambda _:None,clock=lambda:self.now,valuation_provider=lambda _: {})
        self.account.initialize({'event_id':'init'})
        self.cash('initial','1000')
        self.old=self.account.store.read()
        value=self.account.valuation()
        self.baseline=dict(initial_equity='1000',cash='1000',effective_at=value['valued_at'],
            account_revision=self.old['revision'],holdings=[],valuation_evidence=value)
        self.transfers=create_transfers('fixture')
        self.links={};self.times={};self.documents={}

    def cash(self,key,amount):
        self.account.append(dict(expected_revision=self.account.store.read()['revision'],
            event=dict(event_id=key,kind='CASH_CONFIRM',amount=amount,cash_basis='TOTAL_UNINVESTED')))

    def event(self,event):
        self.transfers=apply_transfer_event(self.transfers,event,
            expected_revision=self.transfers['revision'],now=self.now)

    def send(self,balance='395'):
        self.now=datetime(2026,11,14,1,tzinfo=timezone.utc)
        self.event(dict(event_id='sent',transfer_id='t',kind='SENT',source='HSBC',
            destination='USMART',principal='600',fee='5',occurred_at=self.now.isoformat()))
        before=self.account.store.read()['revision']
        self.cash('cash-sent',balance)
        self.links['cash-sent']=['sent'];self.times['cash-sent']=self.now.isoformat()
        return before

    def profit(self):
        current=self.account.audit_state()
        before=copy.deepcopy(current)
        result=amount_profit(baseline=self.baseline,baseline_account=self.old,
            current_account=current,valuation=self.account.valuation(),classifications=self.documents,
            now=self.now,transfer_context=dict(transfer_state=self.transfers,
                expected_transfer_revision=self.transfers['revision'],links=self.links,confirmation_times=self.times))
        self.assertEqual(self.account.audit_state(),before)
        return result

    def test_send_partial_and_complete_receipt_fee_once(self):
        self.send()
        self.assertEqual(self.profit()['profit_amount'],'-5')
        for hour,amount,balance in [(2,'200','595'),(3,'400','995')]:
            self.now=datetime(2026,11,14,hour,tzinfo=timezone.utc)
            key=f'arrival-{hour}'
            self.event(dict(event_id=key,transfer_id='t',kind='RECEIVED',amount=amount,occurred_at=self.now.isoformat()))
            self.cash(key,balance);self.links[key]=[key];self.times[key]=self.now.isoformat()
            self.assertEqual(self.profit()['profit_amount'],'-5')
        self.assertEqual(self.profit()['transfer_reconciliation']['current_in_transit'],'0')

    def test_simultaneous_deposit_classifies_only_residual(self):
        before=self.send(balance='495')
        self.documents['cash-sent']=dict(schema='CASH_CHANGE_CLASSIFICATION_V1',
            account_id='fixture',cash_event_id='cash-sent',before_revision=before,
            after_revision=self.account.store.read()['revision'],net_change='100',items=[
                dict(item_id='deposit',kind='DEPOSIT',amount='100',effective_at=self.now.isoformat())])
        result=self.profit()
        self.assertEqual(result['net_external_flow'],'100')
        self.assertEqual(result['profit_amount'],'-5')
        self.documents['cash-sent']['net_change']='-505'
        with self.assertRaisesRegex(ValueError,'NET_CHANGE_MISMATCH'):self.profit()

    def test_unconfirmed_links_and_residual_block_profit(self):
        self.send(balance='390')
        with self.assertRaisesRegex(ValueError,'UNCLASSIFIED_CASH_CHANGE'):self.profit()
        self.links={}
        with self.assertRaisesRegex(ValueError,'UNLINKED_TRANSFER_EVENTS'):self.profit()

    def test_existing_transit_at_restart_is_not_profit(self):
        self.send()
        self.old=self.account.store.read();value=self.account.valuation()
        self.baseline=dict(initial_equity='395',cash='395',effective_at=value['valued_at'],
            account_revision=self.old['revision'],holdings=[],valuation_evidence=value)
        self.links={};self.times={}
        self.now=datetime(2026,11,14,2,tzinfo=timezone.utc)
        self.event(dict(event_id='arrive',transfer_id='t',kind='RECEIVED',amount='600',occurred_at=self.now.isoformat()))
        self.cash('arrive','995');self.links['arrive']=['arrive'];self.times['arrive']=self.now.isoformat()
        self.assertEqual(self.profit()['profit_amount'],'0')

if __name__=='__main__':unittest.main()
