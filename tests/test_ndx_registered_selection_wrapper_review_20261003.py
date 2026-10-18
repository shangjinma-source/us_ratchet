from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest
from scripts import ndx_registered_scoring_selection_20261003 as m
import test_ndx_registered_scoring_selection_20261003 as author


class IndependentReview(unittest.TestCase):
    def test_eof_authentication_required_even_after_yielded_score(self):
        blob,r,e=author.record_fixture()
        it=m.read_scored_records(BytesIO(blob+b'{}\n'),r,e)
        self.assertEqual(next(it)[1]['weights'],[0,.25,.75])
        with self.assertRaises(ValueError):list(it)
        for field,value in (('byte_stop',e[0][1]['byte_stop']-1),('sequence',1.0),('stage','RAW_FIT')):
            bad=deepcopy(e);bad[0][1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):list(m.read_scored_records(BytesIO(blob),r,bad))

    def test_selection_none_is_saved_before_validation_and_retry_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'new';refs={k:{'path':'/x','sha256':'a'*64} for k in ('budget','budget_audit','policy')}
            args=({'budget':{'plan':{}}},refs,{},[],0)
            adapter=SimpleNamespace(assemble_registered_selector_inputs=lambda **_: {'registration':{},'records':[]})
            selector=SimpleNamespace(select_full_ndx_lanes=lambda **_:None)
            with patch.object(m,'BOUND',{'request':('/future','a'*64)}),patch.object(m,'OUTPUT',root),patch.object(m,'load_metadata',return_value=args),patch.object(m,'source_sets'),patch.object(m,'resource_gate'),patch.object(m,'project_scores',return_value=[]),patch.object(m,'compile_bound',side_effect=[adapter,selector]),patch.object(m,'validate_adapter'):
                with self.assertRaises(ValueError):m.run(execute=True)
                self.assertIsNone(m.loads((root/'raw_selection.json').read_bytes())['result'])
                self.assertTrue((root/'raw_inputs.json').exists());self.assertTrue((root/'failure.json').exists())
                self.assertFalse((root/'publication.json').exists())
                with self.assertRaisesRegex(ValueError,'immutable'):m.run(execute=True)

    def test_source_conflict_and_consume_same_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'s';p.write_bytes(b'old');r=m.ref(p,m.sha(b'old'));sources={}
            with patch.object(m.Path,'read_bytes',side_effect=[b'old',b'new']) as read:
                self.assertEqual(m.take(r,sources),b'old');self.assertEqual(read.call_count,1)
            with self.assertRaises(ValueError):m.merge(sources,m.ref(p,'b'*64))
            (p.parent/'failure.json').write_bytes(b'failure')
            with self.assertRaises(ValueError):m.take(r,{})


if __name__=='__main__':unittest.main()
