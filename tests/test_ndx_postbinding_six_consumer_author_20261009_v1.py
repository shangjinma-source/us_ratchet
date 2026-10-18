"""Physical initial-binding validation; existing prebinding evidence stays separate."""
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import nullcontext
from unittest.mock import patch
import json
import os
import unittest

from ndx_postbinding_six_consumer_fixture_20261009_v1 import (
    build_context, run_short_chain, assert_bound_sources, SEALED, reader,
    capture, capture_reader, writer, observer, gap, gap_reader, publisher, reference, roots)


def sealed_hashes():
    return {str(path): reference(path)['sha256'] for path in sorted(SEALED.rglob('*')) if path.is_file()}


class PostbindingSixConsumerAuthorTests(unittest.TestCase):
    def test_bound_sources_six_roles_and_saved_legacy_root_without_pin_patch(self):
        sources_before = assert_bound_sources()
        sealed_before = sealed_hashes()
        retained = os.environ.get('NDX_POSTBINDING_RETAINED_ROOT')
        workspace = nullcontext(retained) if retained else TemporaryDirectory(prefix='POSTBINDING_REAL_SIX_')
        with workspace as directory:
            context = build_context(Path(directory))
            trap = context['root'] / 'never_read_day_registration.json'
            trapref = dict(path=str(trap), sha256='a' * 64)
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('execute=False must perform no IO')):
                self.assertEqual(reader.inspect_host_continuation_family(
                    **{**context['host_args'], 'execute': False}), dict(status='NOT_EXECUTED'))
                with self.assertRaisesRegex(ValueError, 'Explicit continuation capture execution'):
                    capture.run(registration_path=str(trap), registration_sha256='a' * 64,
                        **{**context['host_args'], 'execute': False})
            original_read = Path.read_bytes
            for wrong_key in ('implementation_pair_binding_sha256', 'consumer_role_registry_sha256'):
                observed = []
                def guarded_read(path):
                    observed.append(str(path))
                    if path == trap:
                        raise AssertionError('Untrusted host digest must fail before day artifact IO')
                    return original_read(path)
                with roots(capture_reader, context), patch.object(Path, 'read_bytes', guarded_read):
                    with self.assertRaisesRegex(ValueError, 'Source bytes changed'):
                        capture_reader.readback(registration_path=str(trap), registration_sha256='a' * 64,
                            capture_reference=trapref, publication_reference=trapref,
                            output_directory=str(context['research'] / 'bad_host_no_output'),
                            **{**context['host_args'], wrong_key: '0' * 64})
                self.assertNotIn(str(trap), observed)
                self.assertFalse((context['research'] / 'bad_host_no_output').exists())
            completed = run_short_chain(context)
            actual = json.loads(Path(completed['actual']['reference']['path']).read_bytes())
            history = actual['history']
            self.assertEqual((history['typed_row_count'], history['observation_count'], history['gap_count']), (73, 3, 10))
            self.assertEqual(history['first_actual_observed_session_by_month']['2026-10'], '2026-10-02')
            receipt = json.loads(Path(completed['observation']['receipt_reference']['path']).read_bytes())
            self.assertIs(receipt['month_first_actual_observation'], False)
            observation_folder = Path(completed['observation']['receipt_reference']['path']).parent
            self.assertEqual({path.name for path in observation_folder.iterdir()}, {
                'started.json', 'observation_payload.json', 'receipt.json', 'reader_started.json', 'independent_readback.json'})
            verified = completed['replay']['sources']
            for path in observation_folder.iterdir():
                self.assertEqual(verified[str(path)], reference(path)['sha256'])
            for source, expected in sources_before.items():
                self.assertEqual(verified[source], expected)
            for refs, producer, independent in (
                    *((refs, capture, capture_reader) for refs in completed['captures']),
                    (completed['gap'], gap, gap_reader), (completed['actual'], publisher, reader)):
                for role, module in (('reference', producer), ('readback_reference', independent)):
                    value = json.loads(Path(refs[role]['path']).read_bytes())
                    for key, expected in module.FLAGS.items():
                        self.assertIs(value[key], expected)
            for role, module in (('receipt_reference', writer), ('audit_reference', observer)):
                value = json.loads(Path(completed['observation'][role]['path']).read_bytes())
                for key, expected in module.FLAGS.items():
                    self.assertIs(value[key], expected)
            self.assertEqual(sources_before, assert_bound_sources())
            self.assertEqual(sealed_before, sealed_hashes())
            result = dict(status='POSTBINDING_REAL_SIX_CONSUMERS_AND_PAIR_PASS_WITHOUT_MEMORY_PINS',
                scope='New short same-B/C actual13 chain; prebinding14-to15 evidence and author RED remain separate',
                parent=completed['parent'], actual=completed['actual'], observation=completed['observation'],
                gap=completed['gap'], captures=completed['captures'], pair=completed['pair'], consumer=completed['consumer'],
                verified=completed['replay'], production_hashes=sources_before,
                sealed_physical_hashes=sealed_before, source_pins_patched=False,
                loader_patched=False, arithmetic_patched=False, original_artifacts_changed=False,
                formal_binding_created=False, authority_authenticated=False)
            with (context['root'] / 'verified_context.json').open('x', encoding='utf-8') as stream:
                json.dump(result, stream, indent=2)


if __name__ == '__main__':
    unittest.main()
