"""Physical synthetic supplement roundtrip; producer poisoned during readback."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_multidecision_holdings_supplement_20261008 as publisher
from scripts import ndx_multidecision_holdings_supplement_independent_readback_20261008 as reader
from backtest import ndx_multidecision_holdings_supplement_research as projection
import test_ndx_multidecision_holdings_supplement_source_20261008 as fixtures


def environment(directory):
    env = fixtures.environment(directory)
    with patch.multiple(publisher, **env):
        ref = publisher.run(execute=True)
    pub = env['OUTPUT'] / 'publication.json'
    artifacts = dict(supplement=(ref['path'], ref['sha256']), publication=(str(pub), reader.sha(pub.read_bytes())),
        publisher=(str(publisher.SOURCE), publisher.LOADED),
        checker=(reader.ARTIFACT_BOUND['checker'][0], reader.sha(Path(reader.ARTIFACT_BOUND['checker'][0]).read_bytes())))
    return dict(BOUND=env['BOUND'], PURE_SHA=env['PURE_SHA'], PARENT=env['OUTPUT'], OUTPUT=Path(directory)/'readback', ARTIFACT_BOUND=artifacts)


class Tests(unittest.TestCase):
    def test_complete_independent_saved_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.multiple(reader, **environment(directory)), patch.object(publisher,'run',side_effect=AssertionError('publisher')), patch.object(projection,'build_supplement',side_effect=AssertionError('projection')):
                ref=reader.readback(execute=True);doc=json.loads(Path(ref['path']).read_bytes())
                self.assertEqual(doc['status'],'PASS_SAVED_HOLDINGS_PROJECTION')
                self.assertFalse(doc['projection_core_called']);self.assertFalse(doc['risk_recomputed'])
                self.assertEqual({p.name for p in reader.OUTPUT.iterdir()},{'started.json','independent_readback.json'})

    def test_resigned_wrong_risk_and_parent_failure_rejected(self):
        for attack in ('risk','failure'):
            with self.subTest(attack=attack),tempfile.TemporaryDirectory() as directory:
                env=environment(directory)
                if attack=='failure':(env['PARENT']/'failure.json').write_text('{}')
                else:
                    path=Path(env['ARTIFACT_BOUND']['supplement'][0]);doc=json.loads(path.read_bytes())
                    doc['supplement']['tables'][4]['rows'][-1][7]='{}'
                    ref=fixtures.write(path,doc);pubpath=Path(env['ARTIFACT_BOUND']['publication'][0]);pub=json.loads(pubpath.read_bytes());pub['supplement_reference']=ref;pubref=fixtures.write(pubpath,pub)
                    env['ARTIFACT_BOUND']['supplement']=(ref['path'],ref['sha256']);env['ARTIFACT_BOUND']['publication']=(pubref['path'],pubref['sha256'])
                with patch.multiple(reader,**env):
                    with self.assertRaises(ValueError):reader.readback(execute=True)
                    if attack=='risk':self.assertTrue((reader.OUTPUT/'failure.json').exists())
                    else:self.assertFalse(reader.OUTPUT.exists())


if __name__=='__main__':unittest.main()
