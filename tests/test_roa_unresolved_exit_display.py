import unittest
from data.roa_strategy_service import unresolved_exit_ids


class UnresolvedExitDisplayTests(unittest.TestCase):
    def test_defensive_partial_exit_and_completed_position(self):
        event=dict(phase='OPEN',risk_on=False,targets={})
        self.assertEqual(unresolved_exit_ids({},event,{'A':5,'B':0},False),{'A'})

    def test_new_risk_on_does_not_revive_old_defensive_exit(self):
        event=dict(phase='OPEN',risk_on=False,targets={})
        self.assertEqual(unresolved_exit_ids({},event,{'A':5},True),set())

    def test_unmaterialized_plan_is_not_confirmed_exit(self):
        event=dict(phase='OPEN',risk_on=False,targets=None)
        self.assertEqual(unresolved_exit_ids({},event,{'A':5},False),set())

    def test_stop_exit_persists_only_for_actual_holdings(self):
        state={'missed_exits':['A','B']}
        self.assertEqual(unresolved_exit_ids(state,None,{'A':2,'B':0},True),{'A'})
        self.assertEqual(state,{'missed_exits':['A','B']})


if __name__=='__main__':
    unittest.main()
