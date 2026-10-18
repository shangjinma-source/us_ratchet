"""Independent snapshot formulas and disposable registered publisher/readback IO."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_registered_forward_capture_independent_readback_20261009_v1 as reader
from scripts import ndx_registered_forward_capture_runtime_20261009_v1 as producer
from backtest import ndx_forward_parent_capture_research_v4 as formula
import test_ndx_forward_parent_capture_research_v4 as fixtures
import test_ndx_forward_parent_capture_research_v4_independent_review as v3
import test_ndx_registered_forward_capture_runtime_20261009_v1_independent_review as physical
from scripts import ndx_prospective_observation_writer_v3_20261009 as writer


def checkers():
    path=reader.ROOT/reader.DEPENDENCIES['compact_helpers'][0]
    helper=reader.private_module(path,path.read_bytes(),reader.DEPENDENCIES['compact_helpers'][1])
    path=reader.ROOT/reader.DEPENDENCIES['parent_view'][0]
    parent=reader.private_module(path,path.read_bytes(),reader.DEPENDENCIES['parent_view'][1],[
        ('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',helper)])
    path,digest=reader.CSV_READER
    return parent,reader.private_module(path,path.read_bytes(),digest).csv_rows


def independent(args):
    parent,csv=checkers()
    return reader.reconstruct_plan(**args,parent_checker=parent,csv_rows=csv)


class RegisteredCaptureReaderTests(unittest.TestCase):
    def test_v3_v4_zero_one_and_late_exact_entire_plan(self):
        for fixture in (fixtures.arguments,v3.v3_arguments):
            for days in ((),('2026-10-09',)):
                args=fixture(days);before=deepcopy(args)
                self.assertEqual(independent(args),formula.plan_parent_capture(**args))
                self.assertEqual(args,before)
                args['capture_started_at']='2026-10-12T20:01:00+00:00'
                args['capture_completed_at']='2026-10-12T20:01:01+00:00'
                self.assertEqual(independent(args),formula.plan_parent_capture(**args))

    def test_multiday_asymmetry_revision_and_preclose_exact(self):
        cases=[fixtures.arguments(('2026-10-09','2026-10-12'))]
        args=fixtures.arguments(('2026-10-09',));args['source_bytes']['SPY']=args['accounted_baseline_bytes']['SPY'];fixtures.resign(args,'SPY');cases.append(args)
        args=fixtures.arguments(('2026-10-09',));args['source_bytes']['QQQ']=args['source_bytes']['QQQ'].replace(b',10,12,8,10,100',b',10,12,8,11,100',1);fixtures.resign(args,'QQQ');cases.append(args)
        args=fixtures.arguments(('2026-10-09',));args['capture_started_at']='2026-10-09T19:59:59+00:00';cases.append(args)
        for args in cases:
            plan=independent(args);self.assertEqual(plan,formula.plan_parent_capture(**args))
            self.assertEqual(plan['status'],'BLOCKED_SOURCE_DIAGNOSTICS')

    def test_hash_scope_clock_tzif_and_parent_authority_reject(self):
        for mutation in ('hash','scope','clock','tzif','authority'):
            args=fixtures.arguments(('2026-10-09',))
            if mutation=='hash':args['source_references']['QQQ']['sha256']='a'*64
            elif mutation=='scope':args['accounted_baseline_bytes']['QQQ']+=b'2026-10-09,10,12,8,10,100\n'
            elif mutation=='clock':args['capture_completed_at']='2026-10-08T20:00:00+00:00'
            elif mutation=='tzif':args['tzif_reference']['sha256']='a'*64
            else:args['parent']['document']['future_independent_oos']=True
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):independent(args)

    def test_pending_producer_and_no_execute_before_io(self):
        for execute in (False,True):
            with patch.object(reader,'PRODUCER_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
                with self.assertRaises(ValueError):reader.readback(registration_path='E:/notread.json',registration_sha256='a'*64,
                    capture_reference=dict(path='E:/capture.json',sha256='b'*64),publication_reference=dict(path='E:/publication.json',sha256='c'*64),output_directory='E:/output',execute=execute)

    def test_private_parent_checker_and_parser_ignore_sysmodules(self):
        with patch.dict('sys.modules',{'backtest.ndx_prospective_observation_parent_history_research_v4':SimpleNamespace(),
                'backtest.ndx_prospective_observation_parent_history_research':SimpleNamespace()}):
            self.assertEqual(independent(fixtures.arguments())['status'],'NO_NEW_SESSION')

    def test_full_physical_v3_zero_one_blocked_without_live_read(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_capture_reader_v3_') as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent=deepcopy(writer.PARENT_BOUND)
            for number,session in enumerate((None,'2026-10-08')):
                current=physical.current_files(root,parent,session)
                path,digest,value=physical.registered(root,research,parent,'capture_'+str(number))
                with patch.multiple(producer,RESEARCH=research,CURRENT=current),patch.object(producer,'now',side_effect=['2026-10-08T20:01:00+00:00','2026-10-08T20:01:01+00:00']):
                    result=producer.run(registration_path=str(path),registration_sha256=digest,execute=True)
                for live in current.values():live.write_bytes(b'changed after capture')
                original=Path.read_bytes
                def deny_live_read(p):
                    if p in current.values():raise AssertionError('Mutable cache read')
                    return original(p)
                with patch.multiple(reader,RESEARCH=research,CURRENT=current),patch.object(Path,'read_bytes',deny_live_read):
                    report=reader.readback(registration_path=str(path),registration_sha256=digest,**result,output_directory=str(research/('reader_'+str(number))),execute=True)
                    with self.assertRaisesRegex(ValueError,'create-only'):reader.readback(registration_path=str(path),registration_sha256=digest,**result,output_directory=str(research/('reader_'+str(number))),execute=True)
                audit=reader.decode(Path(report['path']).read_bytes())
                self.assertEqual(audit['counts']['status'],'NO_NEW_SESSION'if session is None else'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
                self.assertEqual(audit['counts']['parent_typed_row_count'],69)
                self.assertFalse(audit['current_live_cache_read_or_reverified'])
                self.assertFalse(audit['capture_core_called']);self.assertFalse(audit['producer_called'])

    def test_full_physical_v4_parent_and_re_signed_capture_mutation_reject(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_capture_reader_v4_') as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent=physical.compact_parent(root,research)
            current=physical.current_files(root,parent,'2026-10-09')
            path,digest,value=physical.registered(root,research,parent,'capture_v4')
            with patch.multiple(producer,RESEARCH=research,CURRENT=current),patch.object(producer,'now',side_effect=['2026-10-09T20:01:00+00:00','2026-10-09T20:01:01+00:00']):
                result=producer.run(registration_path=str(path),registration_sha256=digest,execute=True)
            with patch.multiple(reader,RESEARCH=research,CURRENT=current):
                report=reader.readback(registration_path=str(path),registration_sha256=digest,**result,output_directory=str(research/'reader_v4'),execute=True)
                self.assertEqual(reader.decode(Path(report['path']).read_bytes())['counts']['parent_typed_row_count'],70)
                capturepath=Path(result['capture_reference']['path']);document=reader.decode(capturepath.read_bytes())
                document['plan']['late_observation_classification_deferred_to_payload_core']=False;capturepath.write_bytes(reader.encode(document))
                changed=reader.reference(str(capturepath),reader.sha(capturepath.read_bytes()))
                pubpath=Path(result['publication_reference']['path']);pub=reader.decode(pubpath.read_bytes());pub['capture_reference']=changed;pubpath.write_bytes(reader.encode(pub))
                with self.assertRaises(ValueError):reader.readback(registration_path=str(path),registration_sha256=digest,capture_reference=changed,
                    publication_reference=reader.reference(str(pubpath),reader.sha(pubpath.read_bytes())),output_directory=str(research/'reader_tampered'),execute=True)
                self.assertFalse((research/'reader_tampered').exists())

    def test_create_only_save_and_resource_stop(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'started.json';reader.save(path,dict(ok=True))
            with self.assertRaises(FileExistsError):reader.save(path,{})
            with patch.object(reader.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                with self.assertRaises(ValueError):reader.save(path.parent/'independent_readback.json',{})
                reader.save(path.parent/'failure.json',dict(status='FAILED_DO_NOT_CONSUME'))


if __name__=='__main__':unittest.main()
