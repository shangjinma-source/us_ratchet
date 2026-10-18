"""Smoke the immutable registered actual chain; temporary directories only."""
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from scripts import ndx_registered_observation_writer_20261009_v2 as writer
from ndx_registered_v5_parent_fixture import envelope,reference
from ndx_registered_v5_observation_fixture import physical_registered_v5_observation

class RegisteredV5ObservationSmoke(unittest.TestCase):
    def test_full_registered_chain_original_rows_source_closure_and_complete_starts(self):
        with TemporaryDirectory(prefix='REGISTERED_V5_OBSERVATION_SMOKE_ONLY_')as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            parent,observation,context=physical_registered_v5_observation(root,research)
            parent_env=envelope(parent);state=view.inspect_parent_history_v5(parent_env)
            payload=writer.decode(Path(observation['payload_reference']['path']).read_bytes());receipt=writer.decode(Path(observation['receipt_reference']['path']).read_bytes())
            audit=writer.decode(Path(observation['audit_reference']['path']).read_bytes())
            self.assertEqual((state['typed_row_count'],state['observation_count'],state['gap_count']),(72,2,10))
            self.assertEqual([item['session']for item in state['pending_source_sessions']],['2026-10-13']);self.assertEqual(state['excluded_not_completed_source_sessions'],[])
            self.assertEqual((payload['session'],payload['sequence']),('2026-10-13',73));self.assertIs(payload['month_first_actual_observation'],False)
            self.assertEqual(payload['first_actual_observed_session_of_month'],'2026-10-02');self.assertEqual(payload['actual_parent_schema'],'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5')
            self.assertEqual(audit['status'],'PASS');self.assertEqual(audit['reader_sha256'],observation['reader_reference']['sha256'])
            candidate=envelope(context['capture'])['document'];self.assertEqual(candidate['plan']['status'],'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
            for ticker in ('QQQ','SPY'):
                parts=payload['full_original_sources_preserved'][ticker]
                for part in parts.values():self.assertEqual(base64.b64decode(part['original_csv_bytes_base64']),Path(part['reference']['path']).read_bytes())
                self.assertEqual(parts['sources']['reference'],candidate['captured_artifacts'][ticker])
                self.assertEqual(parts['baseline_sources']['reference'],state['accounted_baseline_references'][ticker])
                self.assertEqual(payload['selected_original_rows'][ticker],parts['sources']['rows'][-1])
                self.assertEqual(payload['source_row_locations'][ticker],dict(original_data_row_index=len(parts['sources']['rows'])-1,reference=parts['sources']['reference']))
            for path,digest in audit['source_hashes'].items():self.assertEqual(reference(path)['sha256'],digest)
            starts=[]
            for path in research.rglob('started.json'):
                self.assertEqual(audit['source_hashes'].get(str(path)),reference(path)['sha256']);starts.append(str(path))
            for entry in state['observations']:
                path=Path(entry['payload_reference']['path']).parent/'started.json'
                self.assertEqual(audit['source_hashes'].get(str(path)),reference(path)['sha256'])
            for key in writer.FLAGS:self.assertIs(payload[key],False);self.assertIs(receipt[key],False);self.assertIs(audit[key],False)
            self.assertEqual({p.name for p in Path(observation['payload_reference']['path']).parent.iterdir()},
                {'started.json','observation_payload.json','receipt.json','independent_readback.json'})
            self.summary=dict(parent_typed_row_count=72,sequence=73,parent_actual_count=2,parent_gap_count=10,session='2026-10-13',month_first_actual='2026-10-02',
                source_count=len(audit['source_hashes']),local_start_count=len(starts),status=audit['status'])

if __name__=='__main__':unittest.main()
