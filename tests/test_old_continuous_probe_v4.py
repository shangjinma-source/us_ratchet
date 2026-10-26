import unittest
from scripts.run_old_continuous_probe_v4 import admit_split_liquidation

class SplitGateTests(unittest.TestCase):
    def setUp(self):
        self.event=dict(date='2024-10-01',security_id='old',new_security_id='new',new_shares='10',old_shares='1')
        self.arguments=dict(account_state=dict(shares={'old':1}))
        self.selected=dict(target_quantities={})
        self.gate=dict(unmapped_events=[dict(kind='IDENTITY_CONVERSION',security_id='old',date='2024-10-01',old_sid='old',new_sid='new',share_ratio='10')],missing_action_streams=[])

    def admit(self):
        return admit_split_liquidation(self.gate,self.arguments,self.selected,[self.event],'2024-10-01')

    def test_integer_full_liquidation(self):self.assertTrue(self.admit()['admitted'])

    def test_retained_position_rejected(self):
        self.selected['target_quantities']['new']=10
        with self.assertRaisesRegex(ValueError,'FULL_LIQUIDATION'):self.admit()

    def test_fraction_rejected(self):
        self.event['new_shares']='1';self.event['old_shares']='2'
        with self.assertRaisesRegex(ValueError,'FRACTIONAL'):self.admit()

    def test_unrelated_event_not_waived(self):
        self.gate['unmapped_events'].append(dict(kind='dividends',security_id='old',date='2024-10-01'))
        self.assertFalse(self.admit()['admitted'])

if __name__=='__main__':unittest.main()
