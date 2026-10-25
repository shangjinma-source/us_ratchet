"""Capital reconfiguration at the actual cap/exit packet boundary, isolated state."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.monthly_cap_exit_packet import apply_cap_exit_packet
from data.monthly_peak_exit_store import MonthlyPeakExitStore

DAYS=['2026-10-20','2026-10-21','2026-10-22']

def target(equity, quantities):
    binding=dict(strategy_equity=str(equity),search_arguments=dict(
        entered_cash=str(equity),prices={sid:'100' for sid in quantities}))
    decision=dict(input_binding=binding,input_id=sha256(canonical(binding)).hexdigest(),target_quantities=quantities)
    payload=dict(account_id='isolated',target_month='2026-10',target_quantities=quantities,
        decision=dict(payload=decision,decision_id=sha256(canonical(decision)).hexdigest()))
    return dict(payload=payload,target_id=sha256(canonical(payload)).hexdigest())

def packet(selected, histories):
    return dict(base_target=dict(quantities=selected['payload']['target_quantities'],
        price_units={sid:'nominal' for sid in histories},monthly_decision_date=DAYS[0],origin_reference=selected['target_id']),
        signal_date=DAYS[-1],observed_at=DAYS[-1]+'T21:00:00+00:00',session_dates=DAYS,
        session_close_times=dict(review_reference='fixture',closes={d:d+'T20:00:00+00:00' for d in DAYS}),
        histories={sid:dict(source_reference='fixture',units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
            unit_asof=DAYS[-1],currency='USD',basis_id='nominal',review_reference='fixture'),
            closes=[dict(date=d,completed_at=d+'T20:00:00+00:00',close=str(v)) for d,v in zip(DAYS,prices)])
            for sid,prices in histories.items()})

class TopupPacketTests(unittest.TestCase):
    def test_new_capital_new_stock_keeps_exit_and_applies_new_cap(self):
        with TemporaryDirectory() as folder:
            store=MonthlyPeakExitStore(Path(folder)/'risk.sqlite')
            old=target(20000,{'A':180})
            apply_cap_exit_packet(target=old,inputs=packet(old,{'A':[100,80,110]}),risk_store=store,
                account_id='isolated',decision_date=DAYS[0],expected_previous_session=None)
            added=target(30000,{'A':200,'B':100});before=deepcopy(added)
            result=apply_cap_exit_packet(target=added,inputs=packet(added,{'A':[100,80,110],'B':[100,105,110]}),
                risk_store=MonthlyPeakExitStore(Path(folder)/'risk.sqlite'),account_id='isolated',
                decision_date=DAYS[0],expected_previous_session=DAYS[-1])
            self.assertEqual(result['monthly_cap_view']['target_quantities'],{'A':150,'B':100})
            self.assertEqual(result['effective_target_quantities'],{'A':0,'B':100})
            self.assertTrue(result['signal_explanations']['A']['exited'])
            self.assertEqual(added,before)
            saved=store.read('isolated')
            missing=packet(added,{'A':[100,80,110],'B':[100,105,110],'C':[100,101,102]})
            missing['histories']['C']['closes']=missing['histories']['C']['closes'][1:]
            with self.assertRaisesRegex(ValueError,'CAP_COMPLETE_MONTHLY_HISTORY_REQUIRED'):
                apply_cap_exit_packet(target=added,inputs=missing,risk_store=store,account_id='isolated',
                    decision_date=DAYS[0],expected_previous_session=DAYS[-1])
            self.assertEqual(store.read('isolated'),saved)

if __name__=='__main__':unittest.main()
