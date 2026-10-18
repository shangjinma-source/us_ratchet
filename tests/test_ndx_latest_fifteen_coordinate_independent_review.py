"""No producer build, HTTP, fitting, or artifact publication."""
import copy,json,unittest
from scripts import ndx_latest_fifteen_coordinate_plan_20260919 as m

class CoordinateReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if m.sha(m.INVENTORY)!=m.INVENTORY_SHA:raise ValueError('Hard inventory differs')
        cls.rows={r['ticker']:r for r in json.loads(m.INVENTORY.read_bytes())['rows']}
    def test_nonempty_wrong_share_class_rejected(self):
        row=copy.deepcopy(self.rows['ADI'])
        row['dated_security_fact_candidates'][0]['fact']['security_class']='Class B Common Stock'
        with self.assertRaises(ValueError):m.row_plan(row)
    def test_unadjudicated_action_cannot_become_existing_security(self):
        row=copy.deepcopy(self.rows['LRCX'])
        row['dated_security_fact_candidates']=[{'source':'seven','fact':{'ticker':'LRCX','subject_cik':'0000707549','cusip':'512807306','security_id':'security:0000707549:512807306','security_class':'Common Stock'}}]
        with self.assertRaises(ValueError):m.row_plan(row)
    def test_all_proposals_retain_unverified_interval_and_risk(self):
        for ticker in m.TICKERS:
            row=m.row_plan(self.rows[ticker])
            for key in ('identity_assumption_approved','risk_assumption_approved','channel_producer_execution_authorized','legal_training_input_ready','point_in_time_verified','promotion_allowed'):
                self.assertIs(row[key],False)
            self.assertIn('HISTORICAL_RISK_CHAIN_LATEST_VALIDITY_UNVERIFIED',row['gaps'])
            self.assertIn('PROVIDER_CHANNEL_TO_SECURITY_BINDING_UNVERIFIED',row['gaps'])

if __name__=='__main__':unittest.main()
