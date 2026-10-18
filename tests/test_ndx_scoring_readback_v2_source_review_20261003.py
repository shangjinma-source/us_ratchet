"""Independent bounded V2 lineage tests; no actual queue readback."""
from contextlib import contextmanager, ExitStack
from pathlib import Path
import tempfile, unittest
from unittest.mock import patch
from scripts import ndx_registered_scoring_queue_independent_readback_v2_20261003 as m


@contextmanager
def lineage():
    with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
        root=Path(temp); parent=root/'failed';parent.mkdir()
        sources={}
        for name in ('reader.py','inspector.py'):
            p=root/name;p.write_bytes(b'# original immutable source\n');sources[str(p)]=m.filehash(p)
        failure=dict(status='FAILED_NO_RETRY_NOT_FINAL_AUTHORITY',error='Complete saved recovery evidence',completed_shard_audits_are_diagnostic_until_final_readback=True,**m.FALSE)
        for name,value in [('started.json',{'schema':'saved start'}),('failure.json',failure)]+[(f'shard_{i:04d}.json',{'status':'DIAGNOSTIC_ONLY','index':i}) for i in range(53)]:
            (parent/name).write_bytes(m.enc(value))
        snapshot=dict(schema='FAILED_SCORING_READBACK_EVIDENCE_SNAPSHOT_V1',original_handle=20223,original_exit_code=1,failed_output_directory=str(parent),exact_output_names=sorted(p.name for p in parent.iterdir()),source_hashes=sources,diagnostic_shard_count=53,output_hashes={str(p):m.filehash(p) for p in parent.iterdir()},failure_preserved=failure,**dict.fromkeys(('original_failure_reclassified','partial_reports_are_final_authority','optimization_rerun','score_recomputed','selection_allowed'),False))
        path=root/'snapshot.json';path.write_bytes(m.enc(snapshot))
        for key,value in dict(FAILED_PARENT=parent,FAILED_SOURCE_HASHES=sources,FAILED_SNAPSHOT=path,FAILED_SNAPSHOT_SHA=m.filehash(path)).items():stack.enter_context(patch.object(m,key,value))
        yield root,parent,path,snapshot


class Tests(unittest.TestCase):
    def test_pending_inspector_blocks_before_any_filesystem_operation(self):
        with patch.object(m,'INSPECTOR_SHA',None),patch.object(Path,'exists',side_effect=AssertionError('IO')),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'inspector anchor pending'):m.readback(execute=True)

    def test_failed_inventory_and_sources_are_separate_and_rechecked(self):
        for mutation in ('report','source','extra','missing'):
            with self.subTest(mutation=mutation),lineage() as (root,parent,path,snapshot):
                original,sources=m.load_failed_predecessor()
                self.assertEqual(len(sources),58)
                self.assertIs(original['partial_reports_are_final_authority'],False)
                m.guard_failed_predecessor(sources)
                with self.assertRaisesRegex(ValueError,'Fixed source changed'):m.guard(sources)
                if mutation=='report':(parent/'shard_0052.json').write_bytes(b'{}')
                elif mutation=='source':(root/'inspector.py').write_bytes(b'# drift')
                elif mutation=='extra':(parent/'independent_readback.json').write_bytes(b'{}')
                else:(parent/'shard_0052.json').unlink()
                with self.assertRaises((ValueError,FileNotFoundError)):m.guard_failed_predecessor(sources)

    def test_resigned_snapshot_cannot_promote_or_shorten_failed_inventory(self):
        for mutation in ('authority','count','inventory','source'):
            with self.subTest(mutation=mutation),lineage() as (root,parent,path,snapshot):
                if mutation=='authority':snapshot['partial_reports_are_final_authority']=0
                elif mutation=='count':snapshot['diagnostic_shard_count']=52
                elif mutation=='inventory':snapshot['output_hashes'].pop(str(parent/'shard_0052.json'))
                else:snapshot['source_hashes']={str(root/'reader.py'):m.filehash(root/'reader.py')}
                path.write_bytes(m.enc(snapshot))
                with patch.object(m,'FAILED_SNAPSHOT_SHA',m.filehash(path)):
                    with self.assertRaises(ValueError):m.load_failed_predecessor()

if __name__=='__main__':unittest.main()
