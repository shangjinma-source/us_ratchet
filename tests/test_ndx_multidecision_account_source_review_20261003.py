"""Independent publication failure and consumed-source checks; synthetic only."""
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_multidecision_account_inputs_20261003 as wrapper
from test_ndx_multidecision_account_inputs_20261003 import staged


class Review(unittest.TestCase):
    def test_pending_has_no_io_and_core_code_pin_is_real(self):
        self.assertEqual(wrapper.sha(wrapper.CORE.read_bytes()), wrapper.CORE_SHA)
        with patch.dict(wrapper.BOUND, {'outer_result': (wrapper.BOUND['outer_result'][0], None)}), patch.object(Path, 'read_bytes', side_effect=AssertionError('must not read pending inputs')):
            with self.assertRaisesRegex(ValueError, 'binding pending'):
                wrapper.read_inputs()

    def test_actual_return_retained_and_final_output_drift_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); context = staged(root); output = root/'invalid'
            context['core'] = SimpleNamespace(prepare_multidecision_account_inputs=lambda **kw: None)
            with patch.object(wrapper, 'OUTER_ROOT', root/'outer'), patch.object(wrapper, 'OUTPUT', output), patch.object(wrapper, 'read_inputs', return_value=context), patch.object(wrapper, 'resource'):
                with self.assertRaises(TypeError): wrapper.run(execute=True)
                self.assertIsNone(wrapper.decode((output/'inputs.json').read_bytes())['inputs'])
                self.assertTrue((output/'failure.json').exists())
                self.assertFalse((output/'publication.json').exists())
                with self.assertRaisesRegex(ValueError, 'Create only'): wrapper.run(execute=True)
            context = staged(root); output = root/'drift'; original = wrapper.save
            def write(name, obj, emergency=False):
                result = original(name, obj, emergency=emergency)
                if name == 'publication.json': (output/'inputs.json').write_bytes(b'changed after publication')
                return result
            with patch.object(wrapper, 'OUTER_ROOT', root/'outer'), patch.object(wrapper, 'OUTPUT', output), patch.object(wrapper, 'read_inputs', return_value=context), patch.object(wrapper, 'resource'), patch.object(wrapper, 'save', side_effect=write):
                with self.assertRaisesRegex(ValueError, 'output drift'): wrapper.run(execute=True)
            self.assertTrue((output/'failure.json').exists())
            context = staged(root); output = root/'parent-drift'; parent = root/'outer'
            parent.mkdir()
            def parent_changed(name, obj, emergency=False):
                result = original(name, obj, emergency=emergency)
                if name == 'publication.json': (parent/'unexpected').write_bytes(b'not in initial inventory')
                return result
            with patch.object(wrapper, 'OUTER_ROOT', parent), patch.object(wrapper, 'OUTPUT', output), patch.object(wrapper, 'read_inputs', return_value=context), patch.object(wrapper, 'resource'), patch.object(wrapper, 'save', side_effect=parent_changed):
                with self.assertRaisesRegex(ValueError, 'inventory drift'): wrapper.run(execute=True)
            self.assertTrue((output/'inputs.json').exists())
            self.assertTrue((output/'failure.json').exists())

    def test_envelope_bytes_bound_reader_never_executes_and_origin_is_retained(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); reader = root/'independent_reader.py'
            reader.write_bytes(b'raise RuntimeError("not allowed to execute")')
            refs = {'reader': wrapper.reference(reader, wrapper.sha(reader.read_bytes()))}
            for role in ('request', 'raw_result', 'postcheck', 'readback'):
                p = root/(role+'.json'); p.write_bytes(wrapper.enc({'role': role, 'source_hashes': {}}))
                refs[role] = wrapper.reference(p, wrapper.sha(p.read_bytes()))
            sources = {}
            with patch.object(wrapper, 'OUTER_READER', reader):
                e = wrapper.load_envelope({'references':refs, 'numerical_reuse_references':deepcopy(refs)}, sources, {})
                self.assertEqual(e['numerical_reuse_evidence']['references'], refs)
                self.assertEqual(len(sources), 5)
                wrong = deepcopy(refs); wrong['reader']['path'] = str(root/'other.py')
                with self.assertRaisesRegex(ValueError, 'reader role'): wrapper.load_envelope(wrong, {}, {})
                (root/'raw_result.json').write_bytes(b'{}')
                with self.assertRaisesRegex(ValueError, 'Consumed bytes'): wrapper.load_envelope(refs, {}, {})


if __name__ == '__main__': unittest.main()
