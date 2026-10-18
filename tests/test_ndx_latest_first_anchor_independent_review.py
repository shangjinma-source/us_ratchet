"""Isolated probe tests; never call the numerical fitter or real prepare."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_latest_first_anchor_equivalence_20260919 as m

def diagnostic(spec):
    value=dict.fromkeys(m.COMPARE,0)
    value.update(weight_spec=spec,previous_target_weights={},surviving_anchor_mass=0.,effective_anchor_strength=0.,targets={'s':{'target_weight':.25}})
    return value

class AnchorReview(unittest.TestCase):
    def test_no_prior_mass_cannot_be_boolean(self):
        a=diagnostic('constrained_fixed_shrinkage');b=diagnostic(m.ANCHORED)
        a['surviving_anchor_mass']=b['surviving_anchor_mass']=False
        with self.assertRaises(ValueError):m.compare(a,b)

    def test_saved_canonical_memory_cannot_be_changed_during_probe(self):
        task=dict(task_id='task',cutoff='2026-09-17',selected={},parameters={});panel={'returns':[[.01]]}
        saved={'result':diagnostic('constrained_fixed_shrinkage')}
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'probe.json'
            def changed(**kwargs):
                saved['result']['targets']['s']['target_weight']=.5
                result=copy.deepcopy(saved['result']);result['weight_spec']=m.ANCHORED
                return result
            with patch.object(m,'prepare',return_value=({},panel,task,saved,{})),patch.object(m.owner.panel_io,'typed_encode',side_effect=lambda x:x),patch.object(m.owner,'verify_sources',return_value={}),patch.object(m.owner,'check_result',return_value=None),patch.object(m.owner.fitter,'refit_dynamic_cutoff_weights',side_effect=changed) as fit:
                with self.assertRaises(ValueError):m.run('p','h','c','h',target)
                self.assertEqual(fit.call_count,1);self.assertFalse(target.exists())
                self.assertTrue(Path(str(target)+'.raw.json').exists())
                with self.assertRaises(ValueError):m.run('p','h','c','h',target)
                self.assertEqual(fit.call_count,1)

if __name__=='__main__':unittest.main()
