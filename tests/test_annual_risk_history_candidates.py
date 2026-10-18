import unittest
from copy import deepcopy
from datetime import date,timedelta
from backtest.annual_risk_history_candidates import snapshot_candidate

class Candidates(unittest.TestCase):
    def setUp(self):
        self.days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(25)]
        self.record=dict(ticker='A',ordinary_start=self.days[0],
            identity_spans=[dict(start=self.days[0],end=self.days[-1],security_id='A')],
            nominal_closes={d:'100' if i<20 else '50' for i,d in enumerate(self.days)},
            true_share_events=[dict(date=self.days[20],ratio='2')],source_reference='test')
    def run_candidate(self,record=None):
        return snapshot_candidate(decision_date=self.days[20],session_dates=self.days,
                                  records=[record or self.record])['rows'][0]
    def test_split_only_once_and_future_ignored(self):
        row=self.run_candidate()
        self.assertEqual({x['close'] for x in row['closes']},{'50'})
        self.assertEqual(row['closes'][-1]['true_share_divisor'],'1')
        changed=deepcopy(self.record); changed['true_share_events'].append(dict(date=self.days[24],ratio='7'))
        changed['nominal_closes'][self.days[24]]='999'
        self.assertEqual(row,self.run_candidate(changed))
        self.assertNotIn('completed_at',str(row)); self.assertNotIn('observed_at',str(row))
    def test_null_and_ordinary_not_filled(self):
        record=deepcopy(self.record);record['nominal_closes']=None;record['blockers']=['TRI_NULL']
        self.assertIsNone(self.run_candidate(record)['closes'])
        record=deepcopy(self.record);record['ordinary_start']=self.days[2]
        self.assertEqual(self.run_candidate(record)['missing_sessions'],self.days[:2])
    def test_identity_link_must_match_true_event(self):
        record=deepcopy(self.record)
        record['identity_spans']=[dict(start=self.days[0],end=self.days[19],security_id='OLD'),
            dict(start=self.days[20],end=self.days[-1],security_id='NEW')]
        self.assertIn('CROSS_IDENTITY_LINK_UNBOUND',self.run_candidate(record)['reasons'])
        record['cross_identity_link']=dict(from_security_id='OLD',to_security_id='NEW',
            effective_date=self.days[20],share_ratio='2',source_reference='conditional-evidence')
        self.assertEqual(self.run_candidate(record)['status'],'CONDITIONAL_PRICE_CANDIDATE')
        record['cross_identity_link']['share_ratio']='3'
        self.assertIn('CROSS_IDENTITY_LINK_UNBOUND',self.run_candidate(record)['reasons'])
    def test_dates_and_missing_sessions_rejected(self):
        with self.assertRaises(ValueError):
            snapshot_candidate(decision_date='2026-1-2',session_dates=self.days,records=[])
        record=deepcopy(self.record);record['nominal_closes'].pop(self.days[7])
        self.assertEqual(self.run_candidate(record)['missing_sessions'],[self.days[7]])

if __name__=='__main__':unittest.main()
