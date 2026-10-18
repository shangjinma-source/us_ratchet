"""Independent V5 plan formulas and disposable registered IO; never actual."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as reader
from backtest import ndx_forward_parent_capture_research_v5 as producer_formula
from test_ndx_forward_parent_capture_research_v5 import arguments,repin
from test_ndx_forward_parent_capture_research_v4 import arguments as v4_arguments
from test_ndx_forward_parent_capture_research_v4_independent_review import v3_arguments


def checkers():
    raw={key:(reader.ROOT/path).read_bytes()for key,(path,_)in reader.DEPENDENCIES.items()if key in ('parent_view','legacy_view','compact_helpers')}
    parent=reader.private_parent_checker(raw)
    path,digest=reader.CSV_READER
    return parent,reader.private_module(path,path.read_bytes(),digest).csv_rows


def independent(args):
    parent,csv=checkers()
    return reader.reconstruct_plan(**args,parent_checker=parent,csv_rows=csv)


class V5CaptureIndependentPlanTests(unittest.TestCase):
    def test_v3_v4_v5_complete_plan_exact_and_input_detached(self):
        cases=[v3_arguments(),v3_arguments(('2026-10-09',)),v4_arguments(),v4_arguments(('2026-10-09',)),arguments()]
        for args in cases:
            before=deepcopy(args);result=independent(args)
            self.assertEqual(result,producer_formula.plan_parent_capture(**args));self.assertEqual(args,before)
            self.assertTrue(all(result[key]is False for key in reader.PURE_FALSE))
        self.assertEqual(independent(arguments())['actual_parent_schema'],'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5')

    def test_multi_asymmetry_accounted_revision_and_withdrawn_pending_exact(self):
        cases=[arguments(('2026-10-12','2026-10-13'))]
        args=arguments();args['source_bytes']['SPY']+=b'2026-10-13,10,12,8,10,100\n';repin(args,'SPY');cases.append(args)
        args=arguments();args['source_bytes']['QQQ']=args['source_bytes']['QQQ'].replace(b',10,12,8,10,100',b',10,12,8,11,100',1);repin(args,'QQQ');cases.append(args)
        for date in ('2026-10-12','2026-10-13'):
            args=arguments(('2026-10-12','2026-10-13'))
            for ticker in ('QQQ','SPY'):
                args['source_bytes'][ticker]=args['source_bytes'][ticker].replace((date+',10,12,8,10,100\n').encode(),b'');repin(args,ticker)
            cases.append(args)
        for args in cases:
            self.assertEqual(independent(args),producer_formula.plan_parent_capture(**args))
            self.assertEqual(independent(args)['status'],'BLOCKED_SOURCE_DIAGNOSTICS')

    def test_provisional_price_update_allowed_and_late_fact_is_only_candidate(self):
        args=arguments()
        for ticker in ('QQQ','SPY'):
            args['source_bytes'][ticker]=args['source_bytes'][ticker].replace(b'2026-10-12,10,12,8,10,100',b'2026-10-12,10,12,8,11,100');repin(args,ticker)
        args['capture_started_at']='2026-10-14T20:00:00+00:00';args['capture_completed_at']='2026-10-14T20:00:01+00:00'
        result=independent(args);self.assertEqual(result,producer_formula.plan_parent_capture(**args))
        self.assertEqual(result['candidate_session'],'2026-10-12');self.assertFalse(result['future_independent_oos'])

    def test_clock_reversal_prior_clock_rollback_bad_hash_and_tzif_reject(self):
        for mode in ('clock_reversal','prior_clock','hash','tzif','parent_authority'):
            args=arguments()
            if mode=='clock_reversal':args['capture_completed_at']='2026-10-12T20:00:00+00:00'
            elif mode=='prior_clock':args['capture_started_at']='2026-10-12T20:02:00+00:00'
            elif mode=='hash':args['source_references']['QQQ']['sha256']='f'*64
            elif mode=='tzif':args['tzif_reference']['sha256']='f'*64
            else:args['parent']['publication']['promotion_allowed']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):independent(args)

    def test_preclose_unique_candidate_blocked(self):
        args=v4_arguments(('2026-10-09',));args['capture_started_at']='2026-10-09T19:59:59+00:00'
        result=independent(args);self.assertEqual(result,producer_formula.plan_parent_capture(**args));self.assertIsNone(result['candidate_session'])

    def test_private_checker_closure_does_not_execute_capture_or_trust_sysmodules(self):
        private=reader.private_module
        def guarded(path,raw,digest,replacements=()):
            if Path(path)==reader.ROOT/reader.DEPENDENCIES['capture_core'][0]:raise AssertionError('Capture core executed')
            result=private(path,raw,digest,replacements)
            if hasattr(result,'append_observation_history_v4'):result.append_observation_history_v4=lambda **k:(_ for _ in()).throw(AssertionError('Append executed'))
            return result
        with patch.object(reader,'private_module',side_effect=guarded),patch.dict('sys.modules',{
            'backtest.ndx_prospective_history_parent_view_research_v5':SimpleNamespace(),
            'backtest.ndx_prospective_observation_parent_history_research_v4':SimpleNamespace()}):
            self.assertEqual(independent(arguments())['candidate_session'],'2026-10-12')

    def test_pending_publisher_precedes_io_and_no_actual_entry(self):
        with patch.object(reader,'PRODUCER_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            self.assertEqual(reader.readback(registration_path='E:/r.json',registration_sha256='a'*64,capture_reference={},publication_reference={},output_directory='E:/output'),dict(status='NOT_EXECUTED'))
            with self.assertRaises(ValueError):reader.readback(registration_path='E:/r.json',registration_sha256='a'*64,
                capture_reference=dict(path='E:/capture.json',sha256='b'*64),publication_reference=dict(path='E:/publication.json',sha256='c'*64),output_directory='E:/output',execute=True)


class V5CaptureReadbackPhysicalTests(unittest.TestCase):
    def test_physical_v5_parent_original_artifacts_and_tzif_classifications(self):
        from tempfile import TemporaryDirectory
        from ndx_v5_physical_parent_fixture import physical_gap_parent,envelope
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_parent_guard_v5_')as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            refs,_=physical_gap_parent(root,research,'gap_parent')
            parent=envelope(refs);checker,csv=checkers();sources={}
            raw={key:(reader.ROOT/path).read_bytes()for key,(path,_)in reader.DEPENDENCIES.items()}
            prefix=reader.private_prefix_checker(raw,sources)
            reader.verify_parent_chain(parent,checker,prefix,csv,sources)
            original=reader.decode(Path(parent['document']['history']['accounted_prefix_evidence_references']['QQQ']['path']).read_bytes())
            self.assertEqual(original['schema'],'ACCOUNTED_SOURCE_BYTE_PREFIX_EVIDENCE_V1')
            for path,digest in sources.items():self.assertEqual(reader.sha(Path(path).read_bytes()),digest)

    def test_physical_v3_and_v5_source_closure_and_no_live_cache_read(self):
        from tempfile import TemporaryDirectory
        from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as producer
        from scripts import ndx_prospective_observation_writer_v3_20261009 as oldwriter
        from backtest import ndx_forward_capture_runtime_registration_research_v2 as registration
        from ndx_v5_physical_parent_fixture import physical_gap_parent,envelope
        import test_ndx_registered_forward_capture_runtime_20261009_v1_independent_review as oldphysical
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_capture_v5_readback_')as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            for version in ('v3','v3_blank','v5'):
                if version!='v5':
                    inputs=root/version;inputs.mkdir()
                    parent=deepcopy(oldwriter.PARENT_BOUND);current=oldphysical.current_files(inputs,parent,'2026-10-08')
                    if version=='v3_blank':
                        for live in current.values():live.write_bytes(live.read_bytes().replace(b'2026-10-08,',b'\n'*21000+b'2026-10-08,'))
                else:
                    parent,previous=physical_gap_parent(root,research,'gap_parent')
                    h=envelope(parent)['document']['history'];current={}
                    for ticker in ('QQQ','SPY'):
                        current[ticker]=root/(ticker+'_v5_current.csv')
                        current[ticker].write_bytes(Path(h['full_capture_source_references'][ticker]['path']).read_bytes())
                deps=deepcopy(reader.DEPENDENCIES)
                value=dict(schema=registration.SCHEMA,runtime_reference=reader.reference(str(producer.SOURCE),producer.LOADED_SHA),
                    dependency_references={k:reader.reference(str(reader.ROOT/path),digest)for k,(path,digest)in deps.items()},
                    parent=parent,output_directory=str(research/('capture_'+version)),**registration.FLAGS)
                path=root/('registration_'+version+'.json');path.write_bytes(reader.encode(value))
                with patch.multiple(producer,RESEARCH=research,CURRENT=current,DEPENDENCIES=deps,
                        REGISTRATION_CORE=reader.REGISTRATION_CORE),patch.object(producer,'now',side_effect=[
                            '2026-10-12T20:03:00+00:00','2026-10-12T20:03:01+00:00']):
                    captured=producer.run(registration_path=str(path),registration_sha256=reader.sha(path.read_bytes()),execute=True)
                for live in current.values():live.write_bytes(b'changed after capture')
                original=Path.read_bytes
                def no_cache_read(item):
                    if item in current.values():raise AssertionError('Live cache read')
                    return original(item)
                with patch.multiple(reader,RESEARCH=research,CURRENT=current,PRODUCER_SHA=producer.LOADED_SHA),patch.object(Path,'read_bytes',no_cache_read):
                    report=reader.readback(registration_path=str(path),registration_sha256=reader.sha(path.read_bytes()),
                        **captured,output_directory=str(research/('audit_'+version)),execute=True)
                audit=reader.decode(Path(report['path']).read_bytes())
                self.assertEqual(audit['schema'],'FORWARD_CAPTURE_INDEPENDENT_READBACK_V5')
                self.assertTrue(audit['entire_plan_independently_reconstructed'])
                self.assertEqual(audit['csv_reader_reference'],dict(path=str(reader.CSV_READER[0]),sha256=reader.CSV_READER[1]))
                self.assertIn('BLANK_RECORDS_EXCLUDED',audit['csv_resource_semantics'])
                self.assertFalse(audit['current_live_cache_read_or_reverified'])
                self.assertEqual(audit['actual_parent_schema'],envelope(parent)['document']['history']['schema'])
                for source,digest in audit['source_hashes'].items():self.assertEqual(reader.sha(Path(source).read_bytes()),digest)


if __name__=='__main__':unittest.main()
