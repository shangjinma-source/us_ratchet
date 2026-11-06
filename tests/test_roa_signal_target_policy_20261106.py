import unittest
from docs.candidates.roa_signal_target_policy_20261106 import build_target_policy


class SignalTargetTests(unittest.TestCase):
    def arguments(self):
        return dict(signal=dict(market_state={'risk_on':True},selected_weights={'A':'1/10','B':'1/10'}),
            account=dict(cash_confirmation_valid=True,total_uninvested_cash='9600',shares={'A':4}),
            marks={'A':{'price':'100'}},execution_prices={'A':'100','B':'100'},
            stopped=set(),pending=set(),strategy_epoch='synthetic',signal_at='2026-11-05T21:00:00Z',
            valid_from='2026-11-06T14:30:00Z',valid_until='2026-11-06T21:00:00Z')

    def test_frozen_sizing_and_risk_priority(self):
        arguments=self.arguments()
        policy=build_target_policy(**arguments)
        self.assertEqual(policy['target_quantities'],{'A':9,'B':9})
        arguments['pending']={'A'}
        arguments['stopped']={'B'}
        self.assertEqual(build_target_policy(**arguments)['target_quantities'],{'A':4})
        arguments['signal']['market_state']['risk_on']=False
        self.assertEqual(build_target_policy(**arguments)['target_quantities'],{})
        # Pure builder neither manufactures fills nor mutates the earlier target.
        self.assertEqual(arguments['account']['shares'],{'A':4})
        self.assertEqual(policy['target_quantities'],{'A':9,'B':9})

    def test_rejects_unconfirmed_cash_and_overconcentration(self):
        arguments=self.arguments();arguments['account']['cash_confirmation_valid']=False
        with self.assertRaisesRegex(ValueError,'CASH_RECONFIRMATION_REQUIRED'):
            build_target_policy(**arguments)
        arguments=self.arguments();arguments['signal']['selected_weights']['A']='1/2'
        with self.assertRaisesRegex(ValueError,'WEIGHT_CAP'):
            build_target_policy(**arguments)


if __name__=='__main__':unittest.main()
