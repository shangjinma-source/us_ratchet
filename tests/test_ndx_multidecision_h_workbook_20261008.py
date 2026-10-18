"""Physical synthetic projection -> workbook -> independent every-cell XML readback."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


m=load('ndx_multidecision_h_workbook_export_20261008')
c=load('ndx_multidecision_h_workbook_inspection_20261008')
NAMES=['轨道与阻断','已存路径指标','到NAV的逐项距离','两种NAV参考','48个决策位置','已存归一轨迹','来源索引','范围与未晋级','候选原目标证券','已保存决策风险','决策逐SID原暴露','原身份与内部列分离','控制原目标','完整每日原记录','每日SID原持仓','每日原风险与缺口','未执行阻断轨道']


def environment(folder):
    bindings={}
    for role,prefix,status,names in [('presentation','MULTIDECISION_PATH_PRESENTATION','PASS_SAVED_EVIDENCE_PROJECTION',NAMES[:11]),('supplement','MULTIDECISION_HOLDINGS_SUPPLEMENT','PASS_SAVED_HOLDINGS_PROJECTION',NAMES[11:])]:
        parent=folder/role;parent.mkdir();auditdir=folder/(role+'_audit');auditdir.mkdir()
        reader=folder/(role+'_reader.py');reader.write_text('# synthetic source identity only',encoding='utf8')
        readerref=m.ref(str(reader),m.sha(reader.read_bytes()));sources={str(reader):readerref['sha256']}
        start=m.save(parent/'started.json',{'source_hashes':sources})
        tables=[dict(name=name,headers=['序号','真实ticker','原数值文本','原JSON','状态','来源'],rows=[[0,'REAL.X','0.1000000000000000000000000001','{"missing":null}','SAVED',None],[1,'00123','6222659648236112670','[]','SOURCE_BLOCKED','=NEVER_EXECUTE()'],[2,'名字','1/3','{}',False,'0'*64]]) for name in names]
        if role=='supplement': tables[3]['rows'] += [[n,'REAL.X',str(n)+'/7','{}','SAVED',None] for n in range(3,1003)]
        if role=='presentation': tables[4]['rows'][0][3]='{"exact":"'+'甲🙂'*18000+'"}'
        doc=m.save(parent/(role+'.json'),dict(schema=prefix+'_DOCUMENT_V1',started_reference=start,source_hashes=sources,point_in_time_verified=False,promotion_allowed=False,**{role:dict(tables=tables,full_h_delivery_complete=False)}))
        pub=m.save(parent/'publication.json',dict(schema=prefix+'_PUBLICATION_V1',started_reference=start,source_hashes=sources,point_in_time_verified=False,promotion_allowed=False,**{role+'_reference':doc}))
        audit_sources={**sources,doc['path']:doc['sha256'],pub['path']:pub['sha256']}
        m.save(auditdir/'started.json',dict(artifact_references={role:doc,'publication':pub}))
        audit=m.save(auditdir/'independent_readback.json',dict(schema=prefix+'_INDEPENDENT_READBACK_V1',status=status,reader_sha256=readerref['sha256'],publication_reference=pub,source_hashes=audit_sources,point_in_time_verified=False,promotion_allowed=False,**{role+'_reference':doc}))
        for key,value in [(role,doc),(role+'_publication',pub),(role+'_audit',audit),(role+'_reader',readerref)]:bindings[key]=(value['path'],value['sha256'])
    return dict(BOUND=bindings,BUILDER_SHA=m.sha(m.BUILDER.read_bytes()),CHECKER_SHA=m.sha(m.CHECKER.read_bytes()),OUTPUT=folder/'output')


class WorkbookTests(unittest.TestCase):
    def test_pending_and_failed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'never'
            with patch.object(m,'OUTPUT',out),self.assertRaisesRegex(ValueError,'Pending'):m.run(execute=True)
            self.assertFalse(out.exists())
            env=environment(Path(directory))
            (Path(env['BOUND']['supplement'][0]).parent/'failure.json').write_text('{}')
            with patch.multiple(m,**env),self.assertRaisesRegex(ValueError,'Failed'):m.run(execute=True)
            self.assertFalse(env['OUTPUT'].exists())

    def test_physical_full_cell_readback_and_late_cell_attack(self):
        # A retained synthetic artifact is intentional: it is visually reviewed,
        # never placed in the production research namespace.
        folder=Path(tempfile.mkdtemp(prefix='multidecision_h_workbook_synthetic_',dir=ROOT/'tmp'))
        env=environment(folder)
        with patch.multiple(m,**env):
            publication=m.run(execute=True)
            with self.assertRaisesRegex(ValueError,'Create-only'):m.run(execute=True)
        output=env['OUTPUT'];report=json.loads((output/'cell_readback.json').read_text(encoding='utf8'))
        self.assertEqual(report['sheets'],20);self.assertEqual(report['data_rows'][15],1003);self.assertEqual(report['data_rows'][-1],3)
        payload=json.loads((output/'workbook_input.json').read_text(encoding='utf8'))
        attacked=folder/'mutated.xlsx'
        with zipfile.ZipFile(output/'workbook.xlsx') as src,zipfile.ZipFile(attacked,'w') as dst:
            for entry in src.infolist():
                blob=src.read(entry.filename)
                if entry.filename=='xl/worksheets/sheet16.xml':
                    blob=blob.replace(b'1002',b'1001')
                dst.writestr(entry,blob)
        with self.assertRaises(ValueError):c.inspect_workbook(attacked,payload)
        self.assertEqual(m.sha(Path(publication['path']).read_bytes()),publication['sha256'])
        print('SYNTHETIC_WORKBOOK='+str(output))


if __name__=='__main__':unittest.main()
