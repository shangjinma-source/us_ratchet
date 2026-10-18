"""Independent boundary tests for the double-only account adapter."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_double_replacement_signed_paths_20261008 as publisher
from scripts import ndx_double_replacement_signed_paths_independent_readback_20261008 as reader
from backtest import ndx_double_replacement_path_requests_research as projection
from test_ndx_double_replacement_signed_paths_20261008 import fixture
from test_ndx_double_signed_paths_physical_20261008 import physical


class IndependentBoundaries(unittest.TestCase):
    def test_reader_never_compiles_request_or_account_producers(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            registration, constants = physical(root)
            with patch.multiple(publisher, **constants), patch.object(publisher, 'resource'):
                artifacts = publisher.run(registration_reference=registration, execute=True)
                original_private = publisher.private
                compiled_roles = []

                def compile_parsers_only(role, raw):
                    self.assertIn(role, ('stream', 'decoder'))
                    compiled_roles.append(role)
                    return original_private(role, raw)

                with patch.multiple(reader, OUTPUT=root / 'independent', PUBLISHER_SHA=publisher.LOADED), \
                        patch.object(publisher, 'private', side_effect=compile_parsers_only), \
                        patch.object(publisher, 'run', side_effect=AssertionError('No publisher dispatch')), \
                        patch.object(publisher, 'prepare_requests', side_effect=AssertionError('No request producer')), \
                        patch.object(publisher, 'preserve_call', side_effect=AssertionError('No fresh account call')):
                    reference = reader.readback(registration_reference=registration,
                                                result_reference=artifacts['result'],
                                                publication_reference=artifacts['publication'], execute=True)
                report = json.loads(Path(reference['path']).read_bytes())
                self.assertEqual(report['account_checked_count'], 40)
                self.assertEqual(set(compiled_roles), {'stream', 'decoder'})
                self.assertFalse(report['account_called'])

    def test_independent_projection_rejects_late_trade_and_final_slot_locator(self):
        arguments = fixture()
        saved = projection.prepare_double_replacement_path_requests(**arguments)
        for attack in ('late_trade', 'last_locator', 'bool_count'):
            changed = deepcopy(saved)
            if attack == 'late_trade':
                changed['rows'][0]['accounting_request']['sessions'][-1]['trade_shares'] = {'C': 1}
            elif attack == 'last_locator':
                changed['rows'][-1]['selection_reference']['json_pointer'] = '/selection/rows/0'
            else:
                changed['scenario_count'] = True
            with self.subTest(attack=attack), \
                    patch.object(projection, 'prepare_double_replacement_path_requests', side_effect=AssertionError('No producer replay')), \
                    self.assertRaises(ValueError):
                reader.inspect_requests(saved_requests=changed, **arguments)


if __name__ == '__main__':
    unittest.main()
