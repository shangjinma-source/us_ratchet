from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.monthly_cap_exit_packet import apply_cap_exit_packet
from data.monthly_peak_exit_store import MonthlyPeakExitStore


class MonthlyPacketTests(unittest.TestCase):
    def test_twenty_day_window_rolls_without_losing_first_exit(self):
        days = [(date(2026,10,1)+timedelta(days=n)).isoformat() for n in range(30)
                if (date(2026,10,1)+timedelta(days=n)).weekday()<5]
        binding=dict(strategy_equity='20000', search_arguments=dict(entered_cash='20000',prices={'A':'100'}))
        decision=dict(input_binding=binding,input_id=sha256(canonical(binding)).hexdigest(),target_quantities={'A':150})
        payload=dict(account_id='test',target_month='2026-10',target_quantities={'A':150},
                     decision=dict(payload=decision,decision_id=sha256(canonical(decision)).hexdigest()))
        target=dict(payload=payload,target_id=sha256(canonical(payload)).hexdigest())
        def inputs(end, start):
            window=days[start:end]
            return dict(base_target=dict(quantities={'A':150},price_units={'A':'nominal'},
                monthly_decision_date=days[0],origin_reference=target['target_id']),
                signal_date=days[end-1],observed_at=days[end-1]+'T21:00:00+00:00',session_dates=days[:end],
                session_close_times=dict(review_reference='test',closes={d:d+'T20:00:00+00:00' for d in days}),
                histories={'A':dict(source_reference='test',units=dict(
                    schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',unit_asof=days[end-1],
                    currency='USD',basis_id='nominal',review_reference='test'),closes=[
                        dict(date=d,completed_at=d+'T20:00:00+00:00',close='80' if d==days[1] else '100') for d in window])})
        with TemporaryDirectory() as directory:
            store=MonthlyPeakExitStore(Path(directory)/'risk.sqlite')
            first=apply_cap_exit_packet(target=target,inputs=inputs(20,0),risk_store=store,
                account_id='test',decision_date=days[0],expected_previous_session=None)
            last=apply_cap_exit_packet(target=target,inputs=inputs(len(days),len(days)-20),risk_store=store,
                account_id='test',decision_date=days[0],expected_previous_session=days[19])
            self.assertEqual(first['effective_target_quantities'],{'A':0})
            self.assertEqual(last['effective_target_quantities'],{'A':0})
            self.assertEqual(last['state']['session_date'],days[-1])


if __name__=='__main__':
    unittest.main()
