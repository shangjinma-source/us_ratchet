import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_single_replacement_execution_independent_readback_20261003 as m
from scripts import ndx_single_replacement_preparation_independent_readback_20261003 as preparation_reader
from scripts import ndx_single_replacement_shard_worker_20261003 as worker
from test_ndx_single_replacement_preparation_independent_readback_20261003 import prepared


@contextmanager
def physical(root):
    with prepared(root/'parents') as (inputrefs,prep):
        audit=preparation_reader.readback(execute=True);a=json.loads(Path(audit['path']).read_bytes())
        pub=preparation_reader.PARENT/'publication.json';refs=dict(preparation=prep,publication=m.ref(pub,m.sha(pub.read_bytes())),audit=audit,reader=m.ref(preparation_reader.SOURCE,preparation_reader.LOADED))
        bound={k:(r['path'],r['sha256']) for k,r in refs.items()}
        sources={str(worker.SOURCE):worker.LOADED,**{str(worker.ROOT/p):h for p,h in worker.CODE.values()},**{r['path']:r['sha256'] for r in refs.values()},**a['source_hashes']}
        source_dirs=preparation_reader.namespaces(inputrefs);source_dirs[str(preparation_reader.OUTPUT)]={'started.json','independent_readback.json'}
        p=json.loads(Path(prep['path']).read_bytes())['preparation'];domain=worker.private('domain');evaluator=worker.private('evaluator',domain);registration=worker.private('registration')
        plan=registration.build_execution_registration(prepared=p,preparation_reference=refs['preparation'],preparation_audit_reference=refs['audit'],evaluator_reference=m.ref(worker.ROOT/worker.CODE['evaluator'][0],worker.CODE['evaluator'][1]),shard_size=512)
        c=dict(refs=refs,sources=sources,dirs=source_dirs,validated=evaluator.validate_prepared(p),plan=plan,evaluator=evaluator,journal=worker.private('journal'),small_sources={str(worker.SOURCE):worker.LOADED,**{str(worker.ROOT/v):h for v,h in worker.CODE.values()}})
        parent=root/'execution'
        with patch.object(worker,'OUTPUT',parent),patch.object(worker,'load_common',return_value=c),patch.object(worker,'resource'):
            request=worker.run(execute=True,max_shards=1)
        changes=dict(BOUND=bound,PARENT=parent,PREP=preparation_reader.PARENT,AUDIT=preparation_reader.OUTPUT,OUTPUT=root/'readback',REQUEST_PATH=Path(request['path']),REQUEST_SHA=request['sha256'],EXPECTED_INTEGER_COUNT=560)
        with patch.multiple(m,**changes):yield c


class Tests(unittest.TestCase):
    def test_full_physical_source_to_independent_saved512_prefix(self):
        with tempfile.TemporaryDirectory() as tmp,physical(Path(tmp)):
            with patch.object(worker,'run',side_effect=AssertionError('No producer')):
                result=m.readback(execute=True)
            report=json.loads(Path(result['path']).read_bytes())
            self.assertEqual(report['partition']['terminal_count'],512)
            self.assertEqual(report['partition']['undispatched_count'],48)
            self.assertEqual(report['shards'][0]['inspection']['arithmetic_checked_count'],512)
            self.assertFalse(report['full_domain_evaluated'])
            with self.assertRaises(ValueError):m.readback(execute=True)

    def test_final_source_and_reader_output_drift_preserves_failure(self):
        for mode in ('journal','output'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp,physical(Path(tmp)):
                original=m.save
                def save(name,value):
                    r=original(name,value)
                    if name=='independent_readback.json':
                        p=m.PARENT/'shard-0000'/'journal.jsonl' if mode=='journal' else m.OUTPUT/'started.json'
                        with p.open('ab') as f:f.write(b' ')
                    return r
                with patch.object(m,'save',save),self.assertRaises(ValueError):m.readback(execute=True)
                self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue((m.OUTPUT/'independent_readback.json').exists())

    def test_pending_before_io_and_resigned_worker_claim_rejected(self):
        with patch.object(m,'REQUEST_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('No IO')):
            with self.assertRaises(ValueError):m.load_inputs()
        with tempfile.TemporaryDirectory() as tmp,physical(Path(tmp)):
            p=m.REQUEST_PATH;v=json.loads(p.read_bytes());v['source_hashes']['fake.py']='a'*64;p.write_bytes(m.enc(v))
            with patch.object(m,'REQUEST_SHA',m.sha(p.read_bytes())),self.assertRaises(ValueError):m.readback(execute=True)
            self.assertFalse(m.OUTPUT.exists())


if __name__=='__main__':unittest.main()
