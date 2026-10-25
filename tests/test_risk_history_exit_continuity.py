"""Synthetic reviewed-packet boundary test; does not certify vendor sources."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.monthly_cap_exit_packet import apply_cap_exit_packet
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_monthly_risk_history_v1 import merge_risk_histories


class ExitContinuityTests(unittest.TestCase):
    def test_sold_exit_stays_latched_after_next_day_rebound_and_reselection(self):
        days=['2026-10-01','2026-10-02','2026-10-05']
        def target(quantities):
            binding=dict(strategy_equity='20000',search_arguments=dict(entered_cash='20000',prices={'A':'100','B':'100'}))
            decision=dict(input_binding=binding,input_id=sha256(canonical(binding)).hexdigest(),target_quantities=quantities)
            payload=dict(account_id='test',target_month='2026-10',target_quantities=quantities,
                decision=dict(payload=decision,decision_id=sha256(canonical(decision)).hexdigest()))
            return dict(payload=payload,target_id=sha256(canonical(payload)).hexdigest())
        def inputs(selected, end, securities):
            return dict(base_target=dict(quantities=selected['payload']['target_quantities'],
                price_units={sid:'nominal' for sid in securities},monthly_decision_date=days[0],origin_reference=selected['target_id']),
                signal_date=days[end-1],observed_at=days[end-1]+'T21:00:00+00:00',session_dates=days[:end],
                session_close_times=dict(review_reference='fixture',closes={d:d+'T20:00:00+00:00' for d in days}),
                histories={sid:dict(source_reference='fixture',units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
                    unit_asof=days[end-1],currency='USD',basis_id='nominal',review_reference='fixture'),
                    closes=[dict(date=d,completed_at=d+'T20:00:00+00:00',
                        close=('80' if d==days[1] else '120' if d==days[2] else '100') if sid=='A' else '100')
                        for d in days[:end]]) for sid in securities})
        with TemporaryDirectory() as directory:
            store=MonthlyPeakExitStore(Path(directory)/'risk.sqlite')
            old=target({'A':50,'B':50})
            apply_cap_exit_packet(target=old,inputs=inputs(old,2,{'A','B'}),risk_store=store,
                account_id='test',decision_date=days[0],expected_previous_session=None)
            previous=store.read('test');self.assertIn('A',previous['exited'])
            selected=target({'B':50});account=dict(account_id='test',revision='post-sale')
            full=inputs(selected,3,{'A'});raw=canonical(full)
            receipt=dict(account_id='test',account_revision='post-sale',target_id=selected['target_id'],
                monthly_history_inputs_path='risk-history.json',source_sha256={'risk-history.json':sha256(raw).hexdigest()})
            encoded=canonical(receipt)
            packets={'A':dict(receipt_bytes=encoded,trusted_receipt_sha256=sha256(encoded).hexdigest(),files={'risk-history.json':raw})}
            merged,_,_=merge_risk_histories(inputs=inputs(selected,3,{'B'}),packets=packets,
                account=account,target=selected,previous=previous)
            result=apply_cap_exit_packet(target=selected,inputs=merged,risk_store=store,account_id='test',
                decision_date=days[0],expected_previous_session=days[1])
            self.assertEqual(result['state']['last_closes']['A'],'120')
            self.assertIn('A',result['state']['exited'])
            self.assertEqual(result['effective_target_quantities']['A'],0)
            reselected=target({'A':20,'B':50})
            result=apply_cap_exit_packet(target=reselected,inputs=inputs(reselected,3,{'A','B'}),risk_store=store,
                account_id='test',decision_date=days[0],expected_previous_session=days[2])
            self.assertEqual(result['effective_target_quantities']['A'],0)
            self.assertEqual(result['effective_target_quantities']['B'],50)
