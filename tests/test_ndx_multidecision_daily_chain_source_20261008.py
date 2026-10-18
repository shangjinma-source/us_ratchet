from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_multidecision_daily_chain_projection_research import fixture

ROOT=Path(__file__).resolve().parents[1]


def loaded(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py');value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


p=loaded('ndx_multidecision_daily_chain_projection_20261008')
r=loaded('ndx_multidecision_daily_chain_independent_readback_20261008')
io=loaded('ndx_multidecision_daily_chain_sources_20261008')


def environment(folder):
    args=fixture();bindings={}
    for role,prefix,status,published in [('supplement','MULTIDECISION_HOLDINGS_SUPPLEMENT','PASS_SAVED_HOLDINGS_PROJECTION','PUBLISHED_SAVED_HOLDINGS_PENDING_INDEPENDENT_READBACK'),('diagnostics','CANDIDATE_SAVED_RISK_DIAGNOSTIC','PASS','PUBLISHED_DERIVED_DIAGNOSTIC_NOT_ORIGINAL_RISK_PENDING_READBACK')]:
        parent=folder/role;parent.mkdir();auditdir=folder/(role+'_audit');auditdir.mkdir()
        code=folder/(role+'_reader.py');code.write_text('# synthetic independent reader identity')
        readerref=io.reference(str(code),io.sha(code.read_bytes()));sources={str(code):readerref['sha256']}
        doc=args[role+'_document'];inputs=doc.get('input_references',{})
        start=io.save(parent/'started.json',dict(source_hashes=sources,input_references=inputs))
        doc.update(source_hashes=sources,input_references=inputs,started_reference=start,point_in_time_verified=False,promotion_allowed=False)
        docref=io.save(parent/(role+'.json'),doc)
        pub=io.save(parent/'publication.json',dict(schema=prefix+'_PUBLICATION_V1',status=published,started_reference=start,source_hashes=sources,point_in_time_verified=False,promotion_allowed=False,**{role+'_reference':docref}))
        source_map={**sources,docref['path']:docref['sha256'],pub['path']:pub['sha256']}
        ast=io.save(auditdir/'started.json',dict(artifact_references={role:docref,'publication':pub})if role=='supplement'else dict(diagnostics_reference=docref,publication_reference=pub))
        audit=io.save(auditdir/'independent_readback.json',dict(schema=prefix+'_INDEPENDENT_READBACK_V1',status=status,started_reference=ast,publication_reference=pub,reader_sha256=readerref['sha256'],source_hashes=source_map,point_in_time_verified=False,promotion_allowed=False,**{role+'_reference':docref}))
        for key,value in [(role,docref),(role+'_publication',pub),(role+'_audit',audit),(role+'_reader',readerref)]:bindings[key]=(value['path'],value['sha256'])
    return dict(BOUND=bindings,IO_SHA=io.sha(p.IO.read_bytes()),PURE_SHA=io.sha(p.PURE.read_bytes()),AGGREGATOR_SHA=io.sha(p.AGGREGATOR.read_bytes()),OUTPUT=folder/'publisher')


def reader_environment(env):
    return dict(BOUND=env['BOUND'],IO_SHA=env['IO_SHA'],PURE_SHA=env['PURE_SHA'],AGGREGATOR_SHA=env['AGGREGATOR_SHA'],PUBLISHER_SHA=io.sha(p.SOURCE.read_bytes()),CHECKER_SHA=io.sha(r.CHECKER.read_bytes()),RESULT_SHA=io.sha((env['OUTPUT']/'projection.json').read_bytes()),PUBLICATION_SHA=io.sha((env['OUTPUT']/'publication.json').read_bytes()),PARENT=env['OUTPUT'],OUTPUT=env['OUTPUT'].parent/'reader')


class Tests(unittest.TestCase):
    def test_pending_before_output_and_failed_parent(self):
        with tempfile.TemporaryDirectory()as name:
            directory=Path(name);env=environment(directory)
            with patch.object(p,'IO_SHA',None),patch.object(p,'OUTPUT',directory/'none'),self.assertRaisesRegex(ValueError,'Pending'):p.run(execute=True)
            self.assertFalse((directory/'none').exists())
            (directory/'diagnostics/failure.json').write_text('{}')
            with patch.multiple(p,**env),self.assertRaisesRegex(ValueError,'Failed'):p.run(execute=True)
            self.assertFalse(env['OUTPUT'].exists())

    def test_physical_publication_then_independent_no_producer_readback(self):
        with tempfile.TemporaryDirectory()as name:
            env=environment(Path(name))
            with patch.multiple(p,**env):p.run(execute=True)
            re=reader_environment(env);realmodule=r.module
            def independent(path,digest):
                self.assertNotIn(path,(r.PURE,r.PUBLISHER,r.AGGREGATOR));return realmodule(path,digest)
            with patch.multiple(r,**re),patch.object(r,'module',side_effect=independent),patch.object(p,'run',side_effect=AssertionError('producer forbidden')):
                result=r.run(execute=True)
                with self.assertRaisesRegex(ValueError,'Create-only'):r.run(execute=True)
            report=io.decode(Path(result['path']).read_bytes());self.assertEqual(report['inspection']['day_count'],2880);self.assertEqual(report['inspection']['undefined_day_count'],108)

    def test_changed_projection_rejected_even_with_resigned_publication(self):
        with tempfile.TemporaryDirectory()as name:
            env=environment(Path(name))
            with patch.multiple(p,**env):p.run(execute=True)
            resultpath=env['OUTPUT']/'projection.json';doc=io.decode(resultpath.read_bytes())
            doc['projection']['paths'][8]['rows'][0]['chain_weights']={}
            resultpath.write_bytes(io.encode(doc));pubpath=env['OUTPUT']/'publication.json';pub=io.decode(pubpath.read_bytes());pub['projection_reference']['sha256']=io.sha(resultpath.read_bytes());pubpath.write_bytes(io.encode(pub))
            re=reader_environment(env)
            with patch.multiple(r,**re),self.assertRaisesRegex(ValueError,'mismatch'):r.run(execute=True)
            self.assertTrue((re['OUTPUT']/'failure.json').exists());self.assertFalse((re['OUTPUT']/'independent_readback.json').exists())


if __name__=='__main__':unittest.main()
