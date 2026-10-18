"""Author physical integration; run only after Root releases the source locks."""
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import nullcontext
import os
import unittest

from ndx_six_consumer_pair_continuation_fixture_20261009_v1 import (
    physical_six_consumer_pair_chain, CONSUMERS, LOCKS, reader, publisher,
    capture, capture_reader, writer, observer, gap, gap_reader, envelope, reference, bound)


class SixConsumerPairContinuationTests(unittest.TestCase):
    def test_same_original_b_c_six_real_consumers_actual14_then15(self):
        retained = os.environ.get('NDX_SIX_CONSUMER_AUTHOR_RETAINED_ROOT')
        workspace = nullcontext(retained) if retained else TemporaryDirectory(prefix='TEMPORARY_REAL_SIX_CONSUMER_PAIR_')
        with workspace as directory:
            context = physical_six_consumer_pair_chain(Path(directory))
            pair = reader.decode(context['original_host_bytes'][context['pair']['path']])
            consumer = reader.decode(context['original_host_bytes'][context['consumer']['path']])
            self.assertEqual(pair['publisher_reference'], reference(publisher.SOURCE))
            self.assertEqual(pair['independent_reader_reference'], reference(reader.SOURCE))
            self.assertEqual(consumer['consumer_references'], {
                role: reference(module.SOURCE) for role, module in CONSUMERS.items()})
            self.assertEqual(len(consumer['consumer_references']), 6)
            self.assertEqual(envelope(context['gaps'][1])['document']['history']['status'],
                'NO_EXPIRED_SESSION_TO_APPEND')
            self.assertEqual(envelope(context['final_capture'])['document']['plan']['status'], 'NO_NEW_SESSION')
            for index, refs in enumerate(context['actuals']):
                saved = envelope(refs)
                history = saved['document']['history']
                self.assertEqual((history['typed_row_count'], history['observation_count'], history['gap_count']),
                    (73 + index, 3 + index, 10))
                self.assertEqual(history['observations'][-1]['session'], '2026-10-' + str(13 + index))
                for value in (saved['document'], saved['publication'], saved['readback']):
                    self.assertEqual(value['implementation_pair_binding_reference'], context['pair'])
                    self.assertEqual(value['consumer_role_registry_reference'], context['consumer'])
                for key, expected in publisher.FLAGS.items():
                    self.assertIs(saved['document'][key], expected)
                for key, expected in reader.FLAGS.items():
                    self.assertIs(saved['readback'][key], expected)
            for observed in context['observations']:
                folder = Path(observed['payload_reference']['path']).parent
                self.assertEqual({item.name for item in folder.iterdir()}, {
                    'started.json', 'observation_payload.json', 'receipt.json',
                    'reader_started.json', 'independent_readback.json'})
                audit = reader.decode(Path(observed['audit_reference']['path']).read_bytes())
                receipt = reader.decode(Path(observed['receipt_reference']['path']).read_bytes())
                self.assertEqual(len(audit['reader_input_references']), 13)
                self.assertIn(str(folder / 'reader_started.json'), audit['source_hashes'])
                for key, expected in observer.FLAGS.items():
                    self.assertIs(audit[key], expected)
                for key, expected in writer.FLAGS.items():
                    self.assertIs(receipt[key], expected)
            for collection, producer, independent_reader in (
                    ('captures', capture, capture_reader), ('gaps', gap, gap_reader)):
                for refs in context[collection]:
                    saved = envelope(refs)
                    for key, expected in producer.FLAGS.items():
                        self.assertIs(saved['document'][key], expected)
                    for key, expected in independent_reader.FLAGS.items():
                        self.assertIs(saved['readback'][key], expected)
            sources = context['replay']['sources']
            for module, digest in LOCKS.items():
                self.assertEqual(sources[str(module.SOURCE)], digest)
            for collection in ('gaps', 'actuals', 'captures'):
                for refs in context[collection]:
                    for item in refs.values():
                        self.assertEqual(sources[item['path']], item['sha256'])
            for path, raw in context['original_host_bytes'].items():
                self.assertEqual(Path(path).read_bytes(), raw)
            for path, digest in sources.items():
                self.assertEqual(reference(path)['sha256'], digest)
            with bound(reader, context):
                context['replay']['final_guard']()


if __name__ == '__main__':
    unittest.main()
