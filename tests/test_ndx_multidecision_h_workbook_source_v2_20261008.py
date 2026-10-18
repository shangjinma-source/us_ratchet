import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_multidecision_h_workbook_display_v2_research import fixture

ROOT=Path(__file__).resolve().parents[1]


def loaded(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py');value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


m=loaded('ndx_multidecision_h_workbook_export_v2_20261008');io=loaded('ndx_multidecision_daily_chain_sources_20261008')


def environment(folder):
    args=fixture();bindings={}
    specs=[('supplement','MULTIDECISION_HOLDINGS_SUPPLEMENT','supplement','PASS_SAVED_HOLDINGS_PROJECTION','PUBLISHED_SAVED_HOLDINGS_PENDING_INDEPENDENT_READBACK'),('diagnostics','CANDIDATE_SAVED_RISK_DIAGNOSTIC','diagnostics','PASS','PUBLISHED_DERIVED_DIAGNOSTIC_NOT_ORIGINAL_RISK_PENDING_READBACK'),('presentation','MULTIDECISION_PATH_PRESENTATION','presentation','PASS_SAVED_EVIDENCE_PROJECTION','PUBLISHED_SAVED_EVIDENCE_PROJECTION_PENDING_INDEPENDENT_READBACK'),('chain','MULTIDECISION_DAILY_CHAIN','projection','PASS_MIXED_BASIS_DAILY_CHAIN_PROJECTION','PUBLISHED_MIXED_BASIS_CHAIN_PROJECTION_PENDING_READBACK')]
    for role,prefix,field,status,published in specs:
        parent=folder/role;parent.mkdir();auditdir=folder/(role+'_audit');auditdir.mkdir();code=folder/(role+'_reader.py');code.write_text('# synthetic source reader identity')
        reader=io.reference(str(code),io.sha(code.read_bytes()));sources={str(code):reader['sha256']};doc=args[role+'_document']
        if role=='chain':
            lower={key:dict(path=v[0],sha256=v[1])for key,v in bindings.items()if key.split('_')[0]in ('supplement','diagnostics')}
            doc['input_references']=lower;doc['projection']['references']={key:lower[key]for key in ('supplement','diagnostics')}
        inputs=doc.get('input_references',{});start=io.save(parent/'started.json',dict(input_references=inputs,source_hashes=sources))
        doc.update(input_references=inputs,started_reference=start,source_hashes=sources,point_in_time_verified=False,promotion_allowed=False)
        docref=io.save(parent/(field+'.json'),doc);pub=io.save(parent/'publication.json',dict(schema=prefix+'_PUBLICATION_V1',status=published,started_reference=start,source_hashes=sources,point_in_time_verified=False,promotion_allowed=False,**{field+'_reference':docref}))
        audit_start=io.save(auditdir/'started.json',dict(artifact_references={field:docref,'publication':pub})if role in ('supplement','presentation')else{field+'_reference':docref,'publication_reference':pub})
        audit=io.save(auditdir/'independent_readback.json',dict(schema=prefix+'_INDEPENDENT_READBACK_V1',status=status,started_reference=audit_start,reader_sha256=reader['sha256'],publication_reference=pub,source_hashes={**sources,docref['path']:docref['sha256'],pub['path']:pub['sha256']},point_in_time_verified=False,promotion_allowed=False,**{field+'_reference':docref}))
        for key,value in [(role,docref),(role+'_publication',pub),(role+'_audit',audit),(role+'_reader',reader)]:bindings[key]=(value['path'],value['sha256'])
    return dict(BOUND=bindings,OUTPUT=folder/'output',**{name+'_SHA':io.sha(getattr(m,name).read_bytes())for name in ('IO','PURE','DISPLAY_CHECKER','CELL_CHECKER','CHART_CHECKER','BUILDER')})


class Tests(unittest.TestCase):
    def test_pending_and_failed_before_namespace(self):
        with tempfile.TemporaryDirectory()as name:
            folder=Path(name);env=environment(folder)
            with patch.object(m,'IO_SHA',None),patch.object(m,'OUTPUT',folder/'none'),self.assertRaisesRegex(ValueError,'Pending'):m.run(execute=True)
            self.assertFalse((folder/'none').exists());(folder/'chain/failure.json').write_text('{}')
            with patch.multiple(m,**env),self.assertRaisesRegex(ValueError,'Failed'):m.run(execute=True)
            self.assertFalse(env['OUTPUT'].exists())

    def test_full_physical_four_sources_to_all_cell_and_chart_readback(self):
        folder=Path(tempfile.mkdtemp(prefix='multidecision_h_v2_source_synthetic_',dir=ROOT/'tmp'));env=environment(folder)
        with patch.multiple(m,**env):
            ref=m.run(execute=True)
            with self.assertRaisesRegex(ValueError,'Create-only'):m.run(execute=True)
        report=io.decode((env['OUTPUT']/'independent_readback.json').read_bytes())
        self.assertEqual(report['cell_inspection']['sheets'],43)
        self.assertEqual(io.sha(Path(ref['path']).read_bytes()),ref['sha256'])
        print('SYNTHETIC_V2_OUTPUT='+str(env['OUTPUT']))


if __name__=='__main__':unittest.main()
