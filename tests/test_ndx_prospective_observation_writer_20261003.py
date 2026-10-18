from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_prospective_observation_writer_20261003 as m
from backtest import ndx_prospective_observation_receipt_research as core
from test_ndx_prospective_observation_receipt_research import fixture

def args():
    a=fixture();a.pop('writer_started_at_utc');a.pop('writer_completed_at_utc');return a

class Tests(unittest.TestCase):
    def test_pending_rejected_before_io(self):
        with patch.object(m,'BOUND',dict.fromkeys(m.BOUND)),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.load_inputs()
            read.assert_not_called()
    def test_payload_persists_if_postcheck_fails_and_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'first'),patch.object(m,'load_inputs',return_value=(args(),{}, {},core)),patch.object(m,'now',return_value='2026-10-02T20:00:03+00:00'),patch.object(m,'guard',side_effect=ValueError('source drift')):
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','observation_payload.json','failure.json'})
            with self.assertRaises(ValueError):m.run(execute=True)
    def test_late_publication_records_late_without_rewriting_payload(self):
        times=iter(['2026-10-02T20:00:02+00:00','2026-10-02T20:00:03+00:00','2026-10-05T13:30:00+00:00'])
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'first'),patch.object(m,'load_inputs',return_value=(args(),{}, {},core)),patch.object(m,'now',side_effect=lambda:next(times)),patch.object(m,'guard'):
            r=m.run(execute=True);receipt=m.load_json(Path(r['path']).read_bytes());payload=m.load_json((m.OUTPUT/'observation_payload.json').read_bytes())
            self.assertEqual(payload['timing_classification'],'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW');self.assertEqual(receipt['timing_classification'],'LATE_OBSERVATION');self.assertTrue(receipt['month_first_actual_observation']);self.assertTrue(all(receipt[k] is False for k in m.FLAGS))
    def test_source_conflict_fails_before_reads(self):
        with patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.guard({str(m.CORE):'0'*64})
            read.assert_not_called()

if __name__=='__main__':unittest.main()
