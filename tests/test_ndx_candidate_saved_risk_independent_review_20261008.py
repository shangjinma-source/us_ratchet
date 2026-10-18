"""Independent physical attacks against saved-risk closure and terminal cells."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_ndx_candidate_saved_risk_source_20261008 as fixtures


class IndependentTests(unittest.TestCase):
    def test_last_path_last_cell_and_authority_are_not_trusted(self):
        case = fixtures.Tests()
        for attack in ('terminal', 'permission', 'cash'):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as directory:
                constants, _, _ = case.fixture(Path(directory))
                case.publish(constants)
                path = constants['OUTPUT'] / 'diagnostics.json'
                body = json.loads(path.read_bytes())
                if attack == 'terminal':
                    body['paths'][-1]['projection']['rows'][-1]['diagnostic']['metrics']['hhi']['denominator'] = '1'
                elif attack == 'permission':
                    body['order_gate_evaluated'] = True
                else:
                    body['paths'][0]['projection']['rows'][0]['diagnostic']['metrics'] = {}
                path.write_bytes(fixtures.encode(body))
                pubpath = constants['OUTPUT'] / 'publication.json'
                publication = json.loads(pubpath.read_bytes())
                publication['diagnostics_reference']['sha256'] = fixtures.sha(path)
                pubpath.write_bytes(fixtures.encode(publication))
                with self.assertRaises(ValueError):
                    case.inspect(constants)

    def test_unselected_raw_drift_after_started_fails_closed(self):
        case = fixtures.Tests()
        with tempfile.TemporaryDirectory() as directory:
            constants, _, _ = case.fixture(Path(directory))
            original = fixtures.publisher.module

            def instrument(path, digest, *args):
                loaded = original(path, digest, *args)
                if Path(path) == fixtures.publisher.IO:
                    save = loaded.save

                    def drifting_save(output, body):
                        result = save(output, body)
                        if output.name == 'started.json':
                            # WHOLE is not a derived-risk path, but remains in
                            # the complete authenticated source closure.
                            (Path(directory) / 'execution/tracks/09/raw_result.json').write_text('{}')
                        return result

                    loaded.save = drifting_save
                return loaded

            with patch.object(fixtures.publisher, 'module', instrument):
                with self.assertRaises(ValueError):
                    case.publish(constants)
            self.assertTrue((constants['OUTPUT'] / 'failure.json').exists())
            self.assertFalse((constants['OUTPUT'] / 'publication.json').exists())
            with self.assertRaisesRegex(ValueError, 'Create-only'):
                case.publish(constants)


if __name__ == '__main__':
    unittest.main()
