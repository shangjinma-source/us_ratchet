"""Smoke of real bound registered chain in a disposable temporary directory."""
import hashlib,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as capture
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as capture_reader
from scripts import ndx_registered_gap_history_runtime_20261009_v1 as gap
from scripts import ndx_registered_gap_history_independent_readback_20261009_v1 as gap_reader
from ndx_registered_v5_parent_fixture import physical_registered_gap_parent,envelope,reference

class RegisteredV5PhysicalParentSmoke(unittest.TestCase):
    def test_bound_registered_chain_exact_original_envelopes_and_source_closure(self):
        expected={capture.SOURCE:'915fda6119f9ba1ce4e966a6557c18e2d0840dd7f40269dadc22bf2fd30b530f',
            capture_reader.SOURCE:'461cbb0d792001a4096a4c5a4caa701685b245b4989c2aa685f2c03e34ac6ca1',
            gap.SOURCE:'05d2a8d216aabd031c1325f8b63ce2b21b3e4020d6b23c6c131e6afb563daeed',
            gap_reader.SOURCE:'cbf8f093a933ed07c8da541b5fb04ff0515a6850cd61dee3ce0a19bcfcf4e2eb'}
        self.assertEqual({path:reference(path)['sha256']for path in expected},expected)
        with TemporaryDirectory(prefix='REGISTERED_V5_PHYSICAL_SMOKE_ONLY_')as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            refs,context=physical_registered_gap_parent(root,research);full=envelope(refs);state=view.inspect_parent_history_v5(full);h=full['document']['history']
            self.assertEqual((state['typed_row_count'],state['observation_count'],state['gap_count']),(71,2,9))
            self.assertEqual((state['last_observed_session'],state['last_accounted_session']),('2026-10-08','2026-10-09'))
            self.assertEqual([item['session']for item in state['pending_source_sessions']],['2026-10-12'])
            self.assertEqual([item['session']for item in state['excluded_not_completed_source_sessions']],['2026-10-13'])
            self.assertEqual(h['known_typed_rows'][-1]['kind'],'MISSED_OBSERVATION');self.assertEqual(h['known_typed_rows'][-1]['session'],'2026-10-09')
            self.assertEqual(h['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
            original=envelope(context['capture']);self.assertEqual(original['document']['plan']['status'],'BLOCKED_SOURCE_DIAGNOSTICS')
            self.assertEqual([d['reason']for d in original['document']['plan']['diagnostics']],['MULTIPLE_UNACCOUNTED_SESSIONS'])
            self.assertEqual(h['capture_references'],context['capture']);self.assertEqual(h['parent_references'],context['parent'])
            self.assertEqual(full['readback']['status'],'PURE_GAP_HISTORY_READBACK_PASS');self.assertIs(full['readback']['entire_history_independently_reconstructed'],True)
            self.assertEqual({p.name for p in Path(refs['reference']['path']).parent.iterdir()},set(gap_reader.GAP_NAMES))
            self.assertEqual({p.name for p in Path(refs['readback_reference']['path']).parent.iterdir()},{'started.json','independent_readback.json'})
            for path,digest in full['readback']['source_hashes'].items():self.assertEqual(reference(path)['sha256'],digest)
            for key in gap.FLAGS:self.assertIs(full['document'][key],False);self.assertIs(full['readback'][key],False)
            self.summary=dict(typed_row_count=71,observation_count=2,gap_count=9,pending=['2026-10-12'],unfinished=['2026-10-13'],
                source_count=len(full['readback']['source_hashes']),capture_status=original['document']['plan']['status'],reader_status=full['readback']['status'])
        self.assertEqual({path:reference(path)['sha256']for path in expected},expected)

if __name__=='__main__':unittest.main()
