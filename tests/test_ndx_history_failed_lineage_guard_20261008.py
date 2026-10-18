import hashlib
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_history_failed_lineage_guard_20261008 as h
from scripts import ndx_outer_lane_refit_worker_v2_20261008 as worker
from scripts import ndx_outer_lane_refit_independent_readback_v2_20261008 as reader
from scripts import ndx_outer_lane_refit_coordinator_v2_20261008 as coordinator

class Tests(unittest.TestCase):
    def fixture(self,root):
        directory=root/'failed';directory.mkdir();audit=root/'success'/'audit.json';audit.parent.mkdir()
        def save(path,value):path.write_bytes(h.encode(value));return hashlib.sha256(path.read_bytes()).hexdigest()
        started=dict(schema='MULTIDECISION_SCORING_HISTORY_READBACK_STARTED_V1',reader_sha256=h.OLD_READER_SHA,retry_allowed=False,index_reference={'path':'index','sha256':'a'*64},publication_reference={'path':'publication','sha256':'b'*64})
        failure=dict(completed_channel_count=6,remaining_channel_count=71,error='Reference',error_type='ValueError',retry_allowed=False,status='FAILED_DO_NOT_CONSUME')
        pins={str(directory/'started.json'):save(directory/'started.json',started),str(directory/'failure.json'):save(directory/'failure.json',failure)}
        document=dict(schema='MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V2',status='PASS',reader_sha256=h.READER_SHA,previous_failed_counts_reused=False,previous_failed_attempt_references={key:dict(path=str(directory/(key+'.json')),sha256=pins[str(directory/(key+'.json'))]) for key in ('started','failure')},source_hashes=pins,index_reference=started['index_reference'],publication_reference=started['publication_reference'])
        digest=save(audit,document)
        return directory,audit,pins,digest
    def test_exact_two_file_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as temp:
            directory,audit,pins,digest=self.fixture(Path(temp))
            with patch.multiple(h,DIRECTORY=directory,AUDIT=audit,PINS=pins,AUDIT_SHA=digest):
                sources={**pins,str(audit):digest}
                self.assertEqual(h.diagnostic_members(sources),frozenset(pins))
                for attack in ('single','no_audit','wrong_sha'):
                    changed=dict(sources)
                    if attack=='single':changed.pop(str(directory/'started.json'))
                    elif attack=='no_audit':changed.pop(str(audit))
                    else:changed[str(directory/'failure.json')]='0'*64
                    with self.subTest(attack=attack),self.assertRaises(ValueError):h.diagnostic_members(changed)
                (directory/'extra.json').write_text('{}')
                with self.assertRaises(ValueError):h.diagnostic_members(sources)
    def test_success_audit_failure_and_diagnostic_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory,audit,pins,digest=self.fixture(Path(temp))
            with patch.multiple(h,DIRECTORY=directory,AUDIT=audit,PINS=pins,AUDIT_SHA=digest):
                sources={**pins,str(audit):digest};(audit.parent/'failure.json').write_text('{}')
                with self.assertRaises(ValueError):h.diagnostic_members(sources)
                (audit.parent/'failure.json').unlink();(directory/'failure.json').write_text('{}')
                with self.assertRaises(ValueError):h.diagnostic_members(sources)
    def test_unrelated_failed_namespace_is_never_a_diagnostic_member(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'data.json';p.write_text('{}');(root/'failure.json').write_text('{}');reference=worker.ref(p,worker.filehash(p))
            self.assertEqual(h.diagnostic_members({reference['path']:reference['sha256']}),frozenset())
            for module in (worker,reader,coordinator):
                with self.subTest(module=module.__name__),self.assertRaises(ValueError):module.guard({reference['path']:reference['sha256']})
    def test_actual_fixed_lineage_guard_only_without_loading_success_roles(self):
        sources={**h.PINS,str(h.AUDIT):h.AUDIT_SHA}
        self.assertEqual(h.diagnostic_members(sources),frozenset(h.PINS))
        for module in (worker,reader,coordinator):module.guard(sources)

    def test_diagnostic_never_becomes_success_role_input(self):
        path=next(iter(h.PINS));reference=worker.ref(path,h.PINS[path])
        with self.assertRaises(ValueError):worker.take(reference,{})
        with self.assertRaises(ValueError):reader.take(reference,{})
        with self.assertRaises(ValueError):coordinator.read(reference)

if __name__=='__main__':unittest.main()
