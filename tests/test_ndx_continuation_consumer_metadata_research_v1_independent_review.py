"""Independent association-only attacks; no wrapper or IO authentication claim."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from backtest import ndx_continuation_consumer_metadata_research_v1 as metadata
from test_ndx_continuation_consumer_metadata_research_v1 import host_context, public_inputs, reference


class MetadataIndependentReviewTests(unittest.TestCase):
    def test_all_adapter_swaps_and_nested_reference_extras_reject(self):
        context = host_context()
        for role in metadata.ADAPTERS:
            original = metadata.expected_consumer_metadata(consumer_role=role, **context)
            for other, adapter in metadata.ADAPTERS.items():
                if other == role:
                    continue
                changed = deepcopy(original)
                changed['continuation_adapter_schema'] = adapter
                with self.subTest(role=role, other=other), self.assertRaises(ValueError):
                    metadata.inspect_consumer_metadata(changed, expected_role=role, **context)
            for key, value in original.items():
                if type(value) is dict:
                    changed = deepcopy(original)
                    changed[key]['extra_evidence'] = reference('trap')
                    with self.subTest(role=role, ref=key), self.assertRaises(ValueError):
                        metadata.inspect_consumer_metadata(changed, expected_role=role, **context)

    def test_public_extension_every_host_anchor_swapped_and_reader_runtime_reject(self):
        for role in metadata.REGISTERED_DEPENDENCY_ROLES:
            original, deps, context = public_inputs(role)
            extensions = metadata.continuation_input_references(
                registered_dependency_references=deps, consumer_role=role, **context)
            for key in extensions:
                if key == 'registration_dependency_references':
                    continue
                changed = deepcopy(original)
                changed[key] = reference('wrong_' + key)
                with self.subTest(role=role, key=key), self.assertRaises(ValueError):
                    metadata.inspect_producer_input_references(changed, consumer_role=role,
                        registered_dependency_references=deps, **context)
            for reader_role in metadata.PRODUCER_FOR_READER:
                changed = deepcopy(original)
                changed['runtime'] = context['consumer_registry_view']['consumer_references'][reader_role]
                with self.subTest(role=role, reader=reader_role), self.assertRaises(ValueError):
                    metadata.inspect_producer_input_references(changed, consumer_role=role,
                        registered_dependency_references=deps, **context)

    def test_reference_shape_nonfinite_and_host_claim_collision_reject(self):
        for bad in (float('nan'), float('inf'), 0, False, None, 'f' * 63, 'F' * 64):
            context = host_context()
            context['metadata_contract_reference']['sha256'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                metadata.expected_consumer_metadata(consumer_role='gap_publisher', **context)
        context = host_context()
        context['metadata_contract_reference'] = dict(context['bound_pair']['contract_reference'])
        context['metadata_contract_reference']['sha256'] = 'a' * 64
        with self.assertRaises(ValueError):
            metadata.expected_consumer_metadata(consumer_role='gap_publisher', **context)
        original, deps, context = public_inputs('observation_writer')
        for bad in (0, False, None, [], {'path': 'relative.csv', 'sha256': 'a' * 64}):
            altered = deepcopy(deps)
            altered['payload_core'] = bad
            with self.subTest(dependency=bad), self.assertRaises(ValueError):
                metadata.continuation_input_references(registered_dependency_references=altered,
                    consumer_role='observation_writer', **context)

    def test_literal_ref_spelling_is_association_not_identity_rewrite(self):
        context = host_context()
        value = metadata.expected_consumer_metadata(consumer_role='capture_publisher', **context)
        value['ancestry_contract_reference']['path'] = value['ancestry_contract_reference']['path'].lower()
        with self.assertRaises(ValueError):
            metadata.inspect_consumer_metadata(value, expected_role='capture_publisher', **context)

    def test_scope_boundary_extra_flags_reader_inputs_and_business_choices_not_authenticated(self):
        context = host_context()
        value = metadata.expected_consumer_metadata(consumer_role='observation_independent_reader', **context)
        value.update(source_bytes_authenticated=True, reader_input_references={'trap': reference('trap')},
            reader_started_at=float('nan'), schema='UNVERIFIED', raw_inner_history={'schema': 'UNCHANGED'})
        original = deepcopy(value)
        with patch('builtins.open', side_effect=AssertionError('No IO')), \
                patch('pathlib.Path.read_bytes', side_effect=AssertionError('No reads')):
            result = metadata.inspect_consumer_metadata(value,
                expected_role='observation_independent_reader', **context)
        self.assertEqual(value['raw_inner_history'], original['raw_inner_history'])
        for key in metadata.FLAGS:
            self.assertIs(result[key], False)
        self.assertNotIn('reader_input_references', result)
        self.assertEqual(len(result['namespace_files']), 5)
        inputs, deps, context = public_inputs('observation_writer')
        deps['payload_core'] = reference('different_host_selected_business_algorithm')
        inputs['dependencies'] = deepcopy(deps)
        inputs['registration_dependency_references'] = deepcopy(deps)
        accepted = metadata.inspect_producer_input_references(inputs, consumer_role='observation_writer',
            registered_dependency_references=deps, **context)
        self.assertEqual(accepted['registration_dependency_references'], deps)
        # The runtime must independently pin business algorithms and close wrappers/STARTs.


if __name__ == '__main__':
    unittest.main()
