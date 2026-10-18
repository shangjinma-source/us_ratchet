import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ndx_cash_neighbor_selection_wrapper_20261003 import scenario_fixture, m, selector

class IndependentReview(unittest.TestCase):
    def test_authenticated_shard_metadata_cannot_change_task_order_or_pointer(self):
        for mutation in ('task_order', 'task_count_bool', 'audit_result', 'failed_namespace'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                a,d,r,desc,p,jr,c=scenario_fixture(Path(tmp))
                ar=d['full_audit']['shard_audit_references'][1]
                ap=Path(ar['path']); report=m.loads(ap.read_bytes())
                if mutation=='task_order':report['detail']['task_results'][0]['task_id']='0'*64
                elif mutation=='task_count_bool':report['detail']['task_count']=True
                elif mutation=='audit_result':report['result_reference']['sha256']='0'*64
                else:(Path(jr['path']).parent/'failure.json').write_text('{}')
                ap.write_bytes(m.enc(report));ar['sha256']=m.sha(ap.read_bytes())
                with self.assertRaises(ValueError):list(m.new_records(d,r,[desc],p,{},set(),{}))

    def test_late_journal_tail_failure_never_authorizes_emitted_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,d,r,desc,p,jr,c=scenario_fixture(Path(tmp))
            # A saved prefix may be emitted, but the full stream must finish before selection succeeds.
            jp=Path(jr['path']);jp.write_bytes(jp.read_bytes()+b'{}\n')
            emitted=[]; streamed=set()
            with self.assertRaisesRegex(ValueError,'extra journal'):
                selector.select_scenario_stream(**dict(a,new_records=m.new_records(d,r,[desc],p,{},streamed,{}),emit_ledger_row=emitted.append))
            self.assertEqual(len(emitted),3)
            self.assertEqual(streamed,set())

    def test_case_outputs_must_remain_pending_and_all_bytes_present(self):
        for mutation in ('grant','extra','missing','ledger','selection'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);start=m.save(root/'started.json',{})
                ledger=root/'ledger.jsonl';ledger.write_bytes(b'{}\n');lr=m.ref(ledger,m.sha(b'{}\n'))
                selection=dict(ledger_reference=lr,started_reference=start,consumption_status='PENDING_FINAL_SOURCE_CLOSURE',requires_final_publication=True,ledger_bytes=3,ledger_row_count=1)
                receipt=dict(ledger_reference=lr,started_reference=start,status='PENDING_FINAL_SOURCE_CLOSURE',requires_final_publication=True)
                if mutation=='grant':selection['requires_final_publication']=False
                sr=m.save(root/'selection.json',selection);receipt['selection_reference']=sr
                pr=m.save(root/'publication.json',receipt)
                if mutation=='extra':(root/'failure.json').write_text('{}')
                elif mutation=='missing':(root/'started.json').unlink()
                elif mutation=='ledger':ledger.write_bytes(b'[]\n')
                elif mutation=='selection':(root/'selection.json').write_bytes(b'{}')
                with self.assertRaises((ValueError,FileNotFoundError)):
                    m.verify_case_outputs([dict(selection_reference=sr,publication_reference=pr,ledger_reference=lr,ledger_row_count=1)])

    def test_future_anchors_reject_before_any_file_read(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('unexpected read')):
            with self.assertRaisesRegex(ValueError,'anchor'):m.prepare()

if __name__=='__main__':unittest.main()
