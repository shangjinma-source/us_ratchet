import unittest
from datetime import date,timedelta
from copy import deepcopy
import json
from pathlib import Path
from data.current_quantity_v2_prospective_protocol import validate_decision_record,validate_protocol,METHOD


class ProtocolTests(unittest.TestCase):
    def test_unknown_fees_cannot_silently_become_zero(self):
        path = Path(__file__).resolve().parents[1] / 'research_contracts/monthly_quantity_v2_prospective_protocol_candidate_20261015_v2.json'
        protocol = json.loads(path.read_text(encoding='utf-8'))
        self.assertFalse(validate_protocol(protocol)['activated'])
        for key, value in [('other_fees', '0'), ('commission_bps', '100'), ('minimum_commission', '5')]:
            changed = deepcopy(protocol)
            changed['costs_and_comparator'][key] = value
            with self.assertRaises(ValueError):
                validate_protocol(changed)

    def record(self):
        # Synthetic dates only: validator never calls this a market calendar.
        days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(253)]
        return dict(method=METHOD,training_sessions=days,decision_date=days[-1],
            scenario_start_dates=days[::21][:-1],scenario_end_dates=days[21::21],
            completed_close_at=days[-1]+'T16:00:00-04:00',decision_recorded_at=days[-1]+'T16:10:00-04:00',
            source_received_at=[days[-1]+'T16:05:00-04:00'],active_open_at='2026-10-01T09:30:00-04:00',
            target_month='2026-10',previous_target_months=[],source_hashes={'fixture':'a'*64},
            full_domain_manifest_hash='b'*64,external_cash_flows=[])

    def test_valid_shape_is_not_calendar_or_source_certification(self):
        r=validate_decision_record(self.record())
        self.assertFalse(r['calendar_verified']);self.assertFalse(r['execution_authorized'])

    def test_late_source_duplicate_month_and_flow_reject(self):
        for key,value in [('source_received_at',['2026-10-02T12:00:00Z']),
                          ('previous_target_months',['2026-10']),('external_cash_flows',[{'amount':'20000'}])]:
            r=self.record();r[key]=value
            with self.assertRaises(ValueError):validate_decision_record(r)

    def test_wrong_training_and_naive_timestamp_reject(self):
        r=self.record();r['scenario_end_dates']=r['scenario_end_dates'][1:]
        with self.assertRaises(ValueError):validate_decision_record(r)
        r=self.record();r['decision_recorded_at']=r['decision_date']+'T16:10:00'
        with self.assertRaises(ValueError):validate_decision_record(r)


if __name__=='__main__':unittest.main()
