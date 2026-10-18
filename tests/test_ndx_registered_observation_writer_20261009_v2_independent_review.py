"""Temporary V5 writer attacks; frozen production modules stay untouched."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ndx_registered_observation_writer_20261009_v2 as writer
from ndx_v5_physical_parent_fixture import envelope
from test_ndx_registered_observation_writer_20261009_v2 import physical_context,run_context

class IndependentV5WriterReview(unittest.TestCase):
    def test_full_v5_writer_private_execution_isolation_raw_baseline_and_authority(self):
        with TemporaryDirectory(prefix='SYNTHETIC_AUDITOR_V5_WRITER_')as folder:
            context=physical_context(Path(folder));research,parent,capture,current,_=context
            for path in current.values():path.write_bytes(b'live modified after immutable capture')
            original_read=Path.read_bytes;original_compile=writer.private_module
            forbidden={writer.ROOT/'backtest'/name for name in ('ndx_prospective_gap_history_research_v5.py','ndx_accounted_source_prefix_research_v1.py','ndx_forward_source_capture_scoped_research.py','ndx_forward_source_capture_research.py')}
            def immutable_read(path):
                if path in current.values():raise AssertionError('Live cache read')
                return original_read(path)
            def compile_guard(raw,path,expected,name,replacements=()):
                if Path(path)in forbidden:raise AssertionError('Forbidden production computation')
                module=original_compile(raw,path,expected,name,replacements)
                if Path(path)==writer.DEPENDENCIES['capture_checker'][0]:
                    module.readback=lambda **kwargs:(_ for _ in()).throw(AssertionError('Upstream entry executed'))
                return module
            hostile=SimpleNamespace()
            with patch.object(Path,'read_bytes',immutable_read),patch.object(writer,'private_module',side_effect=compile_guard),patch.dict('sys.modules',{
                    'backtest.ndx_prospective_observation_receipt_research':hostile,
                    'backtest.ndx_prospective_history_parent_view_research_v5':hostile,
                    'backtest.ndx_accounted_source_prefix_research_v1':hostile}):
                receipt_ref=run_context(context)
            receipt=writer.decode(Path(receipt_ref['path']).read_bytes());payload=writer.decode(Path(receipt['payload_reference']['path']).read_bytes())
            self.assertEqual((payload['session'],payload['sequence']),('2026-10-13',73))
            self.assertEqual(payload['first_actual_observed_session_of_month'],'2026-10-02');self.assertIs(payload['month_first_actual_observation'],False)
            self.assertEqual(payload['actual_parent_schema'],'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5')
            self.assertEqual(receipt['timing_classification'],'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
            h=envelope(parent)['document']['history'];c=writer.decode(Path(capture['reference']['path']).read_bytes())
            for ticker in ('QQQ','SPY'):
                self.assertEqual(payload['full_original_sources_preserved'][ticker]['sources']['reference'],c['captured_artifacts'][ticker])
                self.assertEqual(payload['full_original_sources_preserved'][ticker]['baseline_sources']['reference'],h['accounted_prefix_references'][ticker])
            for key in writer.FLAGS:self.assertIs(payload[key],False);self.assertIs(receipt[key],False)
            for path,digest in payload['source_hashes'].items():self.assertEqual(writer.sha(Path(path).read_bytes()),digest)
            self.assertEqual(set(Path(receipt_ref['path']).parent.iterdir()),{Path(receipt_ref['path']).parent/name for name in ('started.json','observation_payload.json','receipt.json')})

    def test_semantic_partial_attempts_cannot_escape_by_namespace_name_and_live_claim_pre_read(self):
        with TemporaryDirectory(prefix='SYNTHETIC_AUDITOR_V5_ATTEMPTS_')as folder:
            context=physical_context(Path(folder));research,parent,_,current,_=context;parent_doc=envelope(parent)
            cases=[('started.json',dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5')),
                ('observation_payload.json',dict(schema='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1')),
                ('receipt.json',dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1')),
                ('failure.json',dict(status='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY'))]
            for index,(name,value)in enumerate(cases):
                attempt=research/('arbitrary_unrelated_namespace_'+str(index));attempt.mkdir();path=attempt/name;path.write_bytes(writer.encode(value))
                with patch.object(writer,'RESEARCH',research),self.assertRaisesRegex(ValueError,'UNRESOLVED_PRIOR_ATTEMPT'):
                    writer.attempt_inventory(parent_doc,{},research/'future_attempt')
                path.unlink();attempt.rmdir()
            with patch.object(writer,'CURRENT',current),patch.object(Path,'read_bytes',side_effect=AssertionError('Mutable read')):
                with self.assertRaisesRegex(ValueError,'Mutable current cache'):writer.consume(dict(path=str(current['QQQ']),sha256='a'*64),{})

if __name__=='__main__':unittest.main()
