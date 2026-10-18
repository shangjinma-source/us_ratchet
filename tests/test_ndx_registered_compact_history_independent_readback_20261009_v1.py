"""Synthetic formula and boundary tests; no actual registered readback."""
import base64
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_registered_compact_history_independent_readback_20261009_v1 as reader
from backtest import ndx_prospective_observation_parent_history_research_v4 as pure
from test_ndx_prospective_observation_parent_history_research_v4 import fixture,next_fixture
from test_ndx_prospective_observation_gap_parent_payload_20261009_v3 import arguments


def checkers():
    helper_path,helper_sha=reader.DEPENDENCIES['compact_helpers']
    helper=reader.private_module(helper_path,helper_path.read_bytes(),helper_sha)
    core_path,core_sha=reader.DEPENDENCIES['history_core']
    parent=reader.private_module(core_path,core_path.read_bytes(),core_sha,dict(compact=helper),
        'from backtest import ndx_prospective_observation_parent_history_research as compact')
    csvpath,csvsha=reader.CSV_READER
    return parent,reader.private_module(csvpath,csvpath.read_bytes(),csvsha).csv_rows


def blob_map(a):
    blobs={}
    p=a['observation']['payload']
    for parts in p['full_original_sources_preserved'].values():
        for part in parts.values():blobs[part['reference']['path']]=base64.b64decode(part['original_csv_bytes_base64'])
    blobs[p['tzif_reference']['path']]=base64.b64decode(p['tzif_bytes_base64'])
    _,data,_=arguments()
    h=a['parent']['document']['history']
    if h['schema']=='PROSPECTIVE_GAP_EXTENSION_HISTORY_V3':
        for ticker,item in h['baseline_references'].items():blobs[item['path']]=data['actual_baseline_bytes'][ticker]
    return blobs


def reconstruct(a,blobs=None):
    parent,csv_rows=checkers()
    return reader.reconstruct_history(**a,parent_checker=parent,csv_rows=csv_rows,blobs=blob_map(a)if blobs is None else blobs)


class RegisteredReadbackTests(unittest.TestCase):
    def test_independent_formula_exact_v3_migration_and_repeat_v4(self):
        a=fixture();expected=pure.append_observation_history_v4(**a);before=deepcopy(a)
        with patch.object(pure,'append_observation_history_v4',side_effect=AssertionError('New append called')):
            actual=reconstruct(a)
        reader.exact(actual,expected);self.assertEqual(a,before)
        b=next_fixture(expected,a['observation']);reader.exact(reconstruct(b),pure.append_observation_history_v4(**b))
        self.assertEqual([e['sequence']for e in actual['observations']],[66,70])

    def test_saved_csv_and_actual_prefix_must_match_independently(self):
        a=fixture();blobs=blob_map(a);key=a['observation']['payload']['full_original_sources_preserved']['QQQ']['sources']['reference']['path']
        blobs[key]+=b'changed'
        with self.assertRaises(ValueError):reconstruct(a,blobs)
        a=fixture();a['observation']['payload']['full_original_sources_preserved']['SPY']['sources']['rows'][-1]['Close']='11'
        with self.assertRaises(ValueError):reconstruct(a)

    def test_full_history_exact_not_counts_only(self):
        expected=reconstruct(fixture())
        for mutate in [lambda h:h['observations'][-1].update(sequence=67),lambda h:h['parent_attempt_inventory'].clear(),
            lambda h:h['first_actual_observed_session_by_month'].update({'2026-10':'2026-10-08'}),
            lambda h:h['baseline_references']['QQQ'].update(sha256='f'*64),lambda h:h.update(raw_source_bytes_embedded=True)]:
            changed=deepcopy(expected);mutate(changed)
            with self.assertRaises(ValueError):reader.exact(changed,expected)

    def test_late_and_known_optional_authority_boundaries(self):
        a=fixture();a['observation']['receipt']['timing_classification']='LATE_OBSERVATION';a['observation']['audit']['counts']['timing_classification']='LATE_OBSERVATION'
        reader.exact(reconstruct(a),pure.append_observation_history_v4(**a))
        for role,key in [('payload','receipt_published'),('receipt','seal_status_event_created'),('audit','final_durable_completion_time_verified')]:
            a=fixture();a['observation'][role][key]=True
            with self.assertRaises(ValueError):reconstruct(a)

    def test_parent_actual_attempt_bijection_and_pending_reject(self):
        for mutate in [lambda p:p['document']['history']['parent_attempt_inventory'].clear(),
            lambda p:p['document']['history'].update(pending_source_sessions=[{'session':'2026-10-08'}]),
            lambda p:p['readback'].update(status='PASS')]:
            a=fixture();mutate(a['parent'])
            with self.assertRaises(ValueError):reconstruct(a)

    def test_pending_producer_before_any_io(self):
        with patch.object(reader,'PRODUCER_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'Pending immutable'):
                reader.readback(registration_path='E:/pending.json',registration_sha256='a'*64,
                    history_reference={'path':'E:/h.json','sha256':'b'*64},publication_reference={'path':'E:/p.json','sha256':'c'*64},
                    output_directory='E:/pending_output',execute=True)

    def test_private_closure_rejects_wrong_bytes_and_ignores_sysmodules(self):
        with self.assertRaises(ValueError):reader.private_module(reader.CSV_READER[0],b'bad',reader.CSV_READER[1])
        with patch.dict('sys.modules',{'backtest.ndx_prospective_observation_parent_history_research_v4':None}):
            self.assertEqual(reconstruct(fixture())['observation_count'],2)

    def test_createonly_save_and_duplicate_json(self):
        with tempfile.TemporaryDirectory()as folder:
            path=Path(folder)/'started.json'
            with patch.object(reader.shutil,'disk_usage',return_value=type('Space',(),{'free':10*1024**3})()):
                item=reader.save(path,{'schema':'TEST'});self.assertEqual(reader.sha(path.read_bytes()),item['sha256'])
                with self.assertRaises(FileExistsError):reader.save(path,{})
        with self.assertRaises(ValueError):reader.decode(b'{"a":1,"a":2}')

    def test_full_physical_temporary_publication_and_readback(self):
        from scripts import ndx_registered_compact_history_runtime_20261009_v1 as runtime
        from test_ndx_registered_compact_history_runtime_20261009_v1_independent_review import physical_observation,registration
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_reader_')as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            observation=physical_observation(root);path,digest,value=registration(root,research,observation)
            with patch.object(runtime,'RESEARCH',research):
                result=runtime.run(registration_path=str(path),registration_sha256=digest,execute=True)
            output=research/'independent_compact_pass'
            with patch.object(reader,'RESEARCH',research):
                report=reader.readback(registration_path=str(path),registration_sha256=digest,
                    history_reference=result['history_reference'],publication_reference=result['publication_reference'],
                    output_directory=str(output),execute=True)
                with self.assertRaisesRegex(ValueError,'create-only'):
                    reader.readback(registration_path=str(path),registration_sha256=digest,
                        history_reference=result['history_reference'],publication_reference=result['publication_reference'],
                        output_directory=str(output),execute=True)
            audit=reader.decode(Path(report['path']).read_bytes())
            self.assertEqual(audit['status'],'PURE_COMPACT_HISTORY_READBACK_PASS')
            self.assertEqual((audit['counts']['typed_row_count'],audit['counts']['observation_count']),(70,2))
            self.assertFalse(audit['append_algorithm_called'])
            self.assertEqual({p.name for p in output.iterdir()},{'started.json','independent_readback.json'})
            for source,digest in audit['source_hashes'].items():self.assertEqual(reader.sha(Path(source).read_bytes()),digest)


if __name__=='__main__':unittest.main()
