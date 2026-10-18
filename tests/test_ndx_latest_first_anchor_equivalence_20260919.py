import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_latest_first_anchor_equivalence_20260919 as m


def result(spec):
    value = dict.fromkeys(m.COMPARE, 0)
    value.update(weight_spec=spec, previous_target_weights={}, surviving_anchor_mass=0,
        effective_anchor_strength=0., targets={'s': {'target_weight': .25}})
    return value


class ProbeTests(unittest.TestCase):
    def test_exact_scope_and_not_all_aliases(self):
        canonical = result('constrained_fixed_shrinkage')
        anchored = result(m.ANCHORED)
        self.assertTrue(m.compare(canonical, anchored)['selected_task_exact_equivalence_verified'])
        self.assertFalse(m.compare(canonical, anchored)['all_aliases_equivalence_verified'])
        anchored['targets']['s']['target_weight'] += 1e-16
        self.assertFalse(m.compare(canonical, anchored)['selected_task_exact_equivalence_verified'])
        anchored['effective_anchor_strength'] = False
        with self.assertRaises(ValueError): m.compare(canonical, anchored)

    def test_raw_persists_before_audit_failure_and_no_retry(self):
        task = dict(task_id='task', cutoff='2026-09-17', selected={}, parameters={})
        panel = {'returns': [[.01]]}
        saved = {'result': result('constrained_fixed_shrinkage')}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'probe.json'
            with patch.object(m, 'prepare', return_value=({}, panel, task, saved, {})), \
                 patch.object(m.owner.panel_io, 'typed_encode', side_effect=lambda value: value), \
                 patch.object(m.owner, 'verify_sources', return_value={}), \
                 patch.object(m.owner.fitter, 'refit_dynamic_cutoff_weights', return_value=result(m.ANCHORED)) as fit, \
                 patch.object(m.owner, 'check_result', side_effect=ValueError('audit rejected')):
                with self.assertRaises(ValueError): m.run('p', 'h', 'c', 'h', target)
                self.assertTrue(Path(str(target)+'.raw.json').exists())
                self.assertTrue(Path(str(target)+'.failure.json').exists())
                self.assertFalse(target.exists())
                with self.assertRaises(ValueError): m.run('p', 'h', 'c', 'h', target)
                self.assertEqual(fit.call_count, 1)
                self.assertIsNone(fit.call_args.kwargs['previous_target_weights'])
                self.assertEqual(fit.call_args.kwargs['weight_spec'], m.ANCHORED)

    def test_prior_and_parameter_difference(self):
        a = result('constrained_fixed_shrinkage'); b = result(m.ANCHORED)
        b['declared_parameters'] = {'turnover_anchor_strength': .5}
        self.assertIn('declared_parameters', m.compare(a,b)['differing_fields'])
        b['previous_target_weights'] = {'s': 1.}
        with self.assertRaises(ValueError): m.compare(a,b)


if __name__ == '__main__': unittest.main()
