"""Stable genesis identity across two synthetic monthly target acceptances."""
from copy import deepcopy
import unittest
from test_current_quantity_v2_monthly_retarget import fixture
from data.current_quantity_v2_monthly_retarget import build_monthly_retarget
from data.current_quantity_v2_paper_chain import accept_monthly_retarget,record_chain_event
from data.current_quantity_v2_paper_service import compact


class CompactLineageTests(unittest.TestCase):
    def test_initial_identity_survives_two_active_months_and_events(self):
        state,args,now=fixture()
        first=compact(state);original=deepcopy(state['ledger']['acceptance'])
        self.assertEqual(first['initial_capital_decision_id'],first['capital_decision_id'])
        self.assertEqual(first['initial_research_id'],first['research_id'])
        self.assertNotIn('active_monthly_accepted_at',first)
        identities=[first['capital_decision_id']]
        for index,month in enumerate(('2026-11','2026-12')):
            before=deepcopy(state['ledger'])
            proposal=build_monthly_retarget(state,proposal_inputs=args,now=now)
            state=accept_monthly_retarget(state,proposal,acceptance_id='month-'+str(index),now=now)
            view=compact(state)
            self.assertEqual(view['initial_capital_decision_id'],first['capital_decision_id'])
            self.assertEqual(view['initial_research_id'],first['research_id'])
            self.assertEqual(view['capital_decision_id'],proposal['capital_decision_id'])
            self.assertEqual(view['research_id'],proposal['research_id'])
            self.assertEqual(view['target_month'],month)
            self.assertEqual(state['ledger']['acceptance'],original)
            for key in ('cash','shares','recorded_fees','events'):
                self.assertEqual(state['ledger'][key],before[key])
            identities.append(view['capital_decision_id'])
            if index==0:
                for oid in list(state['ledger']['orders']):
                    state=record_chain_event(state,dict(event_id='cancel-'+oid,type='CANCEL',order_id=oid,
                        expected_revision=state['ledger']['revision'],recorded_at=now,cancelled_at=now),now=now)
                self.assertGreater(len(state['ledger']['events']),len(before['events']))
                state,args,now=fixture((state,proposal['causal_inputs']),day='2026-11-30',at='2026-12-01T12:00:30-05:00')
        self.assertEqual(len(set(identities)),3)

if __name__=='__main__':unittest.main()
