from copy import deepcopy
import unittest
from unittest.mock import patch

from data.current_research_fill_ledger import activate_paper_plan, apply_paper_fill, apply_paper_order_event
from data.current_research_successor_plan import roll_research_plan
import test_current_research_successor_plan as fixtures


class RollTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.SuccessorTests()
        fixture.setUp()
        self.fixture = fixture

    def roll(self, state, quotes, declarations, pins=None):
        with patch('data.current_research_successor_plan.decide_quantity_for_account', side_effect=AssertionError('NO SEARCH')):
            return roll_research_plan(state, expected_revision=state['revision'], decision_date='2026-10-15',
                active_date='2026-10-16', calendar=['2026-10-15','2026-10-16'], valuation_quotes=quotes,
                source_hashes=pins or {'new':'d'*64}, held_unit_continuity=declarations)['plan']

    def close(self,state,kind='EXPIRE'):
        event=dict(event_id='closed',mode='PAPER_MANUAL_FILL',event_type=kind,plan_id=state['plan']['plan_id'],
            order_id=state['plan']['orders'][0]['order_id'],expected_revision=state['revision'])
        if kind=='EXPIRE':event['completed_session']='2026-10-15'
        return apply_paper_order_event(state,event)

    def quotes(self, entries):
        return [dict(security_id=sid,price=price,as_of='2026-10-15',price_basis='UNIT',source_references=['new']) for sid,price in entries]

    def continuity(self, sids, first='2026-10-14'):
        return {sid:dict(from_date=first,to_date='2026-10-15',price_basis='UNIT',status='NO_UNPROCESSED_ACTIONS',source_references=['new']) for sid in sids}

    def test_sell_fill_then_roll_buys_original_target_without_search(self):
        f=self.fixture;plan=f.build()['plan']
        state=activate_paper_plan(f.state,plan,dict(event_id='activate',mode='PAPER_MANUAL_FILL',event_type='ACTIVATE_PLAN',plan_id=plan['plan_id'],expected_revision=f.state['revision']))
        state=apply_paper_fill(state,dict(event_id='sold',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],order_id=plan['orders'][0]['order_id'],qty=2,price='50',fees='0',session='2026-10-15',expected_revision=state['revision']))
        before=deepcopy(state)
        rolled=self.roll(state,self.quotes([('B','19')]),self.continuity(['B']))
        self.assertEqual(rolled['target_quantities'],{'B':5})
        self.assertEqual(rolled['orders'][0]['quantity'],5)
        self.assertEqual(rolled['reserved_cash'],'95')
        self.assertEqual(rolled['research_id'],plan['research_id'])
        self.assertEqual(rolled['causal_inputs']['selection_as_of'],plan['causal_inputs']['selection_as_of'])
        self.assertEqual(state,before)
        self.assertEqual(rolled['causal_inputs']['source_hashes']['new'],'d'*64)
        self.assertEqual(rolled['causal_inputs']['research_snapshot']['roll_parent_plan_id'],plan['plan_id'])

    def test_expiry_reposts_and_partial_only_reposts_difference(self):
        f=self.fixture
        for partial in (False,True):
            state=deepcopy(f.initial);order=state['plan']['orders'][0]
            if partial:
                state=apply_paper_fill(state,dict(event_id='part',mode='PAPER_MANUAL_FILL',plan_id=state['plan']['plan_id'],order_id=order['order_id'],qty=1,price='50',fees='0',session='2026-10-14',expected_revision=state['revision']))
            state=self.close(state)
            rolled=self.roll(state,self.quotes([('X','49')]),self.continuity(['X'],first='2026-10-13'))
            self.assertEqual(rolled['target_quantities'],{'X':2})
            self.assertEqual(rolled['orders'][0]['quantity'],1 if partial else 2)

    def test_target_only_units_missing_declaration_conflicts_and_stale_revision(self):
        state=self.close(deepcopy(self.fixture.initial))
        quotes=self.quotes([('X','49')]);declaration=self.continuity(['X'],first='2026-10-13')
        with self.assertRaises(ValueError):self.roll(state,quotes,{})
        changed=deepcopy(quotes);changed[0]['price_basis']='SPLIT_UNIT'
        with self.assertRaises(ValueError):self.roll(state,changed,declaration)
        with self.assertRaises(ValueError):self.roll(state,quotes,declaration,{'new':'d'*64,'q':'f'*64})
        with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_REVISION'):
            roll_research_plan(state,expected_revision='stale',decision_date='2026-10-15',active_date='2026-10-16',
                calendar=['2026-10-15','2026-10-16'],valuation_quotes=quotes,source_hashes={'new':'d'*64},held_unit_continuity=declaration)


if __name__=='__main__':unittest.main()
