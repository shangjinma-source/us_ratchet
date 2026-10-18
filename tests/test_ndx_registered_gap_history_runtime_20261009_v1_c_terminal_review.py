"""Additional temporary IO attacks; never uses formal output directories."""
from pathlib import Path
from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_gap_history_runtime_20261009_v1 as module
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as reader
from test_ndx_registered_gap_history_runtime_20261009_v1_independent_review import physical_context,run_context

class AdditionalGapRuntimeReview(unittest.TestCase):
    def test_all_host_pins_fail_before_any_read(self):
        dependencies=deepcopy(module.DEPENDENCIES)
        dependencies['capture_checker']=(dependencies['capture_checker'][0],reader.LOADED_SHA)
        cases=[('DEPENDENCIES',dict(dependencies,**{role:(path,None)}))for role,(path,_)in dependencies.items()]
        cases += [(name,(getattr(module,name)[0],None))for name in ('REGISTRATION_CORE','REFERENCE_CORE','CSV_READER')]
        for name,value in cases:
            with self.subTest(name=name,value=value),patch.object(module,'DEPENDENCIES',dependencies),patch.object(module,name,value),patch.object(Path,'read_bytes',side_effect=AssertionError('Premature read')):
                with self.assertRaisesRegex(ValueError,'Pending immutable anchor'):
                    module.run(registration_path='E:/synthetic/registration.json',registration_sha256='a'*64,execute=True)

    def test_own_start_drift_and_namespace_extras_preserve_failure_and_block_retry(self):
        for attack in ('own_start','extra_file','extra_directory'):
            with self.subTest(attack=attack),TemporaryDirectory(prefix='SYNTHETIC_AUDITOR_GAP_')as folder:
                context=physical_context(Path(folder));output=context[0]/'gap_output';original=module.save
                def altered(path,value):
                    item=original(path,value)
                    if path.name=='history.json':
                        if attack=='own_start':
                            target=output/'started.json';target.write_bytes(target.read_bytes()+b'\n')
                        elif attack=='extra_file':(output/'unclaimed.json').write_bytes(b'{}')
                        else:(output/'unclaimed').mkdir()
                    return item
                with patch.object(module,'save',side_effect=altered),self.assertRaises(ValueError):run_context(context)
                self.assertTrue((output/'failure.json').is_file())
                self.assertTrue((output/'history.json').is_file())
                failure=module.decode((output/'failure.json').read_bytes())
                self.assertTrue(all(failure[key] is False for key in module.FLAGS))
                saved=(output/'started.json').read_bytes()
                with self.assertRaisesRegex(ValueError,'Create-only'):run_context(context)
                self.assertEqual((output/'started.json').read_bytes(),saved)

if __name__=='__main__':unittest.main()
