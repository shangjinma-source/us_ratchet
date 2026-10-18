import unittest
from copy import deepcopy
from datetime import date,timedelta
from backtest.annual_risk_clock_binder import bind_snapshot,BASIS
from backtest.current_quantity_v2_signal_history import build_signal_history_resolver

class Binder(unittest.TestCase):
    def setUp(self):
        self.days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(21)]
        self.schedule=dict(session_dates=self.days,review_reference='test-schedule',
            closes={d:d+'T16:00:00-05:00' for d in self.days})
        self.row=dict(ticker='A',security_id='A',status='CONDITIONAL_PRICE_CANDIDATE',reasons=[],
            unit_asof=self.days[-1],basis_id='unit',source_reference='prices',
            closes=[dict(date=d,close='10',source_security_id='A') for d in self.days])
        self.candidate=dict(schema='ANNUAL_RISK_PRICE_CANDIDATE_V1',count=21,
                            decision_date=self.days[-1],rows=[self.row])
    def bind(self):
        return bind_snapshot(candidate=self.candidate,schedule=self.schedule,
            expected_identities={r['ticker']:r['security_id'] for r in self.candidate['rows']},
            assumption=dict(timestamp_basis=BASIS),review_reference='assumption+source hashes')
    def test_assumed_early_close_and_resolver(self):
        self.schedule['closes'][self.days[-1]]=self.days[-1]+'T13:00:00-05:00'
        snapshot=self.bind()
        self.assertEqual(snapshot['observed_at'],self.days[-1]+'T13:01:00-05:00')
        self.assertFalse(snapshot['historical_receipt_verified'])
        resolve=build_signal_history_resolver(session_dates=self.days,
            session_close_times=self.schedule,snapshots={self.days[-1]:snapshot})
        result=resolve(decision_date=self.days[-1],target_quantities={'A':1},
                       monthly_decision_date=self.days[-1],count=20)
        self.assertEqual(len(result['histories']['A']['closes']),20)
    def test_blocked_retained_and_requested_fails(self):
        self.candidate['rows'].append(dict(ticker='TRI',security_id='T',status='BLOCKED',
                                          closes=None,reasons=['UNRESOLVED']))
        snapshot=self.bind();self.assertEqual(snapshot['blocked_rows'][0]['ticker'],'TRI')
        resolve=build_signal_history_resolver(session_dates=self.days,
            session_close_times=self.schedule,snapshots={self.days[-1]:snapshot})
        with self.assertRaises(KeyError):
            resolve(decision_date=self.days[-1],target_quantities={'T':1},
                    monthly_decision_date=self.days[-1],count=21)
    def test_missing_duplicate_and_identity_rejected(self):
        original=deepcopy(self.candidate)
        self.row['closes'][4]['date']=self.days[3]
        with self.assertRaises(ValueError):self.bind()
        self.candidate=deepcopy(original);self.candidate['rows'].append(deepcopy(original['rows'][0]))
        with self.assertRaises(ValueError):self.bind()
        self.candidate=original
        with self.assertRaises(ValueError):
            bind_snapshot(candidate=self.candidate,schedule=self.schedule,expected_identities={'A':'BAD'},
                          assumption=dict(timestamp_basis=BASIS),review_reference='review')
    def test_wrong_clock_and_unbound_identity(self):
        self.schedule['closes'][self.days[0]]=self.days[0]+'T16:00:00-04:00'
        with self.assertRaises(ValueError):self.bind()
        self.schedule['closes'][self.days[0]]=self.days[0]+'T16:00:00-05:00'
        self.row['closes'][0]['source_security_id']='OLD'
        with self.assertRaises(ValueError):self.bind()

if __name__=='__main__':unittest.main()
