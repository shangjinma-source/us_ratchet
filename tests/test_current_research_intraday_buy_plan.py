import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from data.current_research_intraday_buy_plan import build_intraday_initial_buy_proposal
from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_journal import IntradayObservationJournal
from test_current_research_intraday_execution import NOW,payload,snapshot

class BuyProposalTests(unittest.TestCase):
    def fixture(self,root):
        service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:payload(),clock=lambda:NOW,journal=IntradayObservationJournal(root))
        response=service.preview('a'*24);receipt=response['observation_record']
        args=dict(journal_root=root,session='2026-10-15',event_path=receipt['event_path'],expected_event_hashes={receipt['event_path']:receipt['event_sha256']},research_snapshot=snapshot(None),available_cash='20000',shares={},reserved_cash='0',open_orders=[],account_id='proposed-new-account',account_revision='initial',expected_revision='initial',now=NOW,
            market_session=dict(date='2026-10-15',timezone='America/New_York',open_at='2026-10-15T09:30:00-04:00',close_at='2026-10-15T16:00:00-04:00',source_references=['calendar']),source_hashes={'calendar':'c'*64})
        args['research_snapshot']['budget']=20000.0
        return service,args
    def test_exact_initial_cash_and_immutable_proposal(self):
        with tempfile.TemporaryDirectory() as root:
            _,a=self.fixture(root);before=deepcopy(a);files={p:p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}
            r=build_intraday_initial_buy_proposal(**a)
            self.assertEqual(r['status'],'READY',r);self.assertEqual(r['quantity'],14)
            self.assertEqual(r['causal_inputs']['research_snapshot']['stocks'][0]['units'],13)
            self.assertIsNone(r['time_in_force']);self.assertFalse(r['legacy_ledger_compatible'])
            self.assertEqual(build_intraday_initial_buy_proposal(**a)['proposal_id'],r['proposal_id'])
            self.assertEqual(a,before);self.assertEqual(files,{p:p.read_bytes() for p in Path(root).rglob('*') if p.is_file()})
    def test_cash_revision_positions_time_and_session(self):
        with tempfile.TemporaryDirectory() as root:
            _,a=self.fixture(root)
            for delta in [dict(available_cash='19999'),dict(shares={'sndk':1}),dict(reserved_cash='1'),dict(open_orders=[{}]),dict(expected_revision='stale'),dict(now=NOW-timedelta(seconds=1)),dict(now=NOW+timedelta(seconds=120)),dict(source_hashes={})]:
                b=deepcopy(a);b.update(delta)
                self.assertEqual(build_intraday_initial_buy_proposal(**b)['status'],'BLOCKED',delta)
    def test_receipt_and_research_tamper(self):
        with tempfile.TemporaryDirectory() as root:
            _,a=self.fixture(root)
            b=deepcopy(a);b['research_snapshot']['selected_security']['ticker']='OTHER'
            self.assertEqual(build_intraday_initial_buy_proposal(**b)['status'],'BLOCKED')
            b=deepcopy(a);b['expected_event_hashes'][b['event_path']]='0'*64
            self.assertEqual(build_intraday_initial_buy_proposal(**b)['status'],'BLOCKED')
            raw=next((Path(root)/'raw').glob('*.bin'));raw.write_bytes(b'broken')
            self.assertEqual(build_intraday_initial_buy_proposal(**a)['status'],'BLOCKED')
    def test_display_budget_is_not_exact_cash_authority(self):
        with tempfile.TemporaryDirectory() as root:
            _,a=self.fixture(root)
            self.assertEqual(build_intraday_initial_buy_proposal(**a)['status'],'READY')
            for value in (float('nan'),float('inf'),True,19999.0):
                b=deepcopy(a);b['research_snapshot']['budget']=value
                self.assertEqual(build_intraday_initial_buy_proposal(**b)['status'],'BLOCKED')

    def test_superseded_reference_cannot_revive(self):
        with tempfile.TemporaryDirectory() as root:
            service,a=self.fixture(root);service.fetch=lambda _:(_ for _ in ()).throw(OSError('offline'));service.preview('a'*24)
            r=build_intraday_initial_buy_proposal(**a)
            self.assertEqual(r['status'],'BLOCKED',r);self.assertEqual(r['reason'],'REFERENCE_SUPERSEDED')

if __name__=='__main__':unittest.main()
