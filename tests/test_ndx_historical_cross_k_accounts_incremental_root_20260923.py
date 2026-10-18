import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import ndx_historical_cross_k_accounts_incremental_audit_20260923 as module


class RootIncrementalAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def read(reference):
            raw = Path(reference['path']).read_bytes()
            if module.independent.hashlib.sha256(raw).hexdigest() != reference['sha256']:
                raise AssertionError('Real fixture source drift')
            return json.loads(raw)
        seed, current, fit = (read(reference) for reference in (module.SEED, module.INDEX, module.FIT))
        cls.arguments = seed, read(seed['index_reference']), current, fit, read(fit['index_reference'])

    def test_actual_prefix_linkage_without_numerical_replay(self):
        with patch.object(module.independent.prefix, 'verify', side_effect=AssertionError('old fit audit replay')), \
                patch.object(module.independent.shared, 'verify', side_effect=AssertionError('old control audit replay')):
            module.validate_prefix(*self.arguments)

    def test_changed_fit_authority_and_bool_count_rejected(self):
        for mutation in ('authority', 'boolean_count', 'fit_order'):
            arguments = copy.deepcopy(self.arguments)
            if mutation == 'authority':
                arguments[2]['fit_prefix_audit_reference']['sha256'] = '0'*64
            elif mutation == 'boolean_count':
                arguments[2]['completed_account_task_count'] = True
            else:
                arguments[4]['entries'][:2] = reversed(arguments[4]['entries'][:2])
            with self.assertRaises(ValueError):
                module.validate_prefix(*arguments)

    def test_closed_publish_detects_changed_output(self):
        value = dict(archive_resolution={}, historical_expected_source_hashes={})
        with patch.object(module, 'build', return_value=value), \
                patch.object(module.independent.archive, 'load_contract', return_value={}), \
                patch.object(module.independent.archive, 'verify_expected_sources', return_value={}), \
                patch.object(module.independent, 'publish', return_value={'path':'x','sha256':'h'}), \
                patch.object(module.independent, 'read', return_value={'changed': True}):
            with self.assertRaisesRegex(ValueError, 'readback differs'):
                module.build_and_publish('unused')


if __name__ == '__main__':
    unittest.main()
