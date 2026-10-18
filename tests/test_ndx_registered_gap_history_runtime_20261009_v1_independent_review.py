"""Root whole physical gap review using independently reconstructed history."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import ndx_registered_gap_history_runtime_20261009_v1 as module
from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as capture
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as capture_reader
from backtest import ndx_gap_runtime_registration_research_v1 as registration
from backtest import ndx_forward_capture_runtime_registration_research_v2 as capture_registration
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from backtest import ndx_gap_history_independent_reconstruction_research_v1 as independent
from backtest import ndx_capture_source_csv_independent_reconstruction_research_v1 as csv_checker
from backtest import ndx_accounted_source_prefix_independent_reconstruction_research_v1 as prefix_checker
from ndx_v5_physical_parent_fixture import physical_gap_parent, envelope, reference
import test_ndx_registered_forward_capture_runtime_20261009_v2_independent_review as capture_physical


def physical_context(root):
    research = root / 'research'; research.mkdir()
    parent, _ = physical_gap_parent(root, research)
    current = capture_physical.current_files(root, parent, 'new_gap')
    deps = deepcopy(capture_reader.DEPENDENCIES)
    cap = dict(schema=capture_registration.SCHEMA, runtime_reference=reference(capture.SOURCE),
        dependency_references=capture.configured(deps), parent=parent,
        output_directory=str(research / 'new_capture'), **capture_registration.FLAGS)
    path = root / 'capture_registration.json'; path.write_bytes(module.encode(cap))
    with patch.multiple(capture, RESEARCH=research, CURRENT=current), patch.object(capture, 'now',
            side_effect=['2026-10-13T20:03:00+00:00', '2026-10-13T20:03:01+00:00']):
        captured = capture.run(registration_path=str(path), registration_sha256=reference(path)['sha256'], execute=True)
    with patch.multiple(capture_reader, RESEARCH=research, CURRENT=current, PRODUCER_SHA=capture.LOADED_SHA):
        audit = capture_reader.readback(registration_path=str(path), registration_sha256=reference(path)['sha256'],
            **captured, output_directory=str(research / 'new_capture_audit'), execute=True)
    capture_refs = dict(reference=captured['capture_reference'], publication_reference=captured['publication_reference'],
                        readback_reference=audit, reader_reference=reference(capture_reader.SOURCE))
    deps = deepcopy(module.DEPENDENCIES)
    deps['capture_checker'] = (deps['capture_checker'][0], capture_reader.LOADED_SHA)
    value = dict(schema=registration.SCHEMA, runtime_reference=reference(module.SOURCE),
        dependency_references={key: module.reference(str(module.ROOT / source), digest) for key, (source, digest) in deps.items()},
        parent=parent, capture=capture_refs, output_directory=str(research / 'gap_output'), **registration.FLAGS)
    path = root / 'gap_registration.json'; path.write_bytes(module.encode(value))
    args = dict(registration_path=str(path), registration_sha256=reference(path)['sha256'], execute=True)
    return research, parent, capture_refs, current, deps, args


def run_context(context, **extra):
    research, parent, capture_refs, current, deps, args = context
    private = module.private_module

    def synthetic_compile(path, raw, digest, replacements=()):
        if Path(path) == capture_reader.SOURCE and b'PRODUCER_SHA=None' in raw:
            if raw.count(b'PRODUCER_SHA=None') != 1:
                raise AssertionError('Exactly one synthetic future pin')
            raw = raw.replace(b'PRODUCER_SHA=None', ("PRODUCER_SHA='" + capture.LOADED_SHA + "'").encode())
            digest = module.digest(raw)
        return private(path, raw, digest, replacements)

    with patch.multiple(module, RESEARCH=research, CURRENT=current, DEPENDENCIES=deps), \
            patch.object(module, 'private_module', side_effect=synthetic_compile):
        return module.run(**dict(args, **extra))


class IndependentPhysicalGapTests(unittest.TestCase):
    def test_mixed_physical_output_whole_history_independent_and_no_live_read(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ROOT_GAP_INDEPENDENT_') as directory:
            context = physical_context(Path(directory))
            research, parent, capture_refs, current, _, _ = context
            for path in current.values(): path.write_bytes(b'changed after capture')
            original = Path.read_bytes

            def deny_live(path):
                if path in current.values(): raise AssertionError('Live cache read')
                return original(path)

            with patch.object(Path, 'read_bytes', deny_live):
                result = run_context(context)
            document = module.decode(Path(result['history_reference']['path']).read_bytes())
            history = document['history']; previous = view.inspect_parent_history_v5(envelope(parent))
            refs = history['full_capture_source_references']
            raw = {ticker: Path(item['path']).read_bytes() for ticker, item in refs.items()}
            expected = independent.reconstruct_gap_history(parent=envelope(parent), capture_references=capture_refs,
                source_bytes=raw, source_references=refs,
                accounted_baseline_bytes={ticker: Path(item['path']).read_bytes() for ticker, item in previous['accounted_baseline_references'].items()},
                actual_baseline_bytes={ticker: Path(item['path']).read_bytes() for ticker, item in previous['baseline_references'].items()},
                prefix_references=history['accounted_prefix_references'], prefix_evidence_references=history['accounted_prefix_evidence_references'],
                capture_started_at=history['capture_started_at'], capture_completed_at=history['capture_completed_at'],
                tzif_bytes=Path(history['tzif_reference']['path']).read_bytes(), tzif_reference=history['tzif_reference'],
                parent_checker=view, csv_rows=csv_checker.csv_rows, prefix_checker=prefix_checker)
            self.assertEqual(module.encode(history), module.encode(expected))
            self.assertEqual(history['new_missed_observation_count'], 1)
            self.assertEqual([item['session'] for item in history['pending_source_sessions']], ['2026-10-13'])
            for ticker in ('QQQ', 'SPY'):
                prefix, evidence = prefix_checker.reconstruct_accounted_prefix(source_bytes=raw[ticker], source_reference=refs[ticker],
                    accounted_sessions=[row['session'] for row in history['known_typed_rows']], scope_start=history['known_typed_rows'][0]['session'])
                self.assertEqual(Path(history['accounted_prefix_references'][ticker]['path']).read_bytes(), prefix)
                self.assertEqual(Path(history['accounted_prefix_evidence_references'][ticker]['path']).read_bytes(), independent.encode(evidence) + b'\n')
            with self.assertRaisesRegex(ValueError, 'Create-only'): run_context(context)

    def test_final_guard_rejects_saved_prefix_and_current_capture_start_drift(self):
        for attack in ('prefix', 'capture_start'):
            with self.subTest(attack=attack), TemporaryDirectory(prefix='SYNTHETIC_ROOT_GAP_DRIFT_') as directory:
                context = physical_context(Path(directory))
                output = context[0] / 'gap_output'
                original = module.save

                def save_with_drift(path, value):
                    result = original(path, value)
                    if path.name == 'history.json':
                        target = output / 'QQQ.accounted_prefix.csv' if attack == 'prefix' else Path(context[2]['reference']['path']).parent / 'started.json'
                        target.write_bytes(target.read_bytes() + b'\n')
                    return result

                with patch.object(module, 'save', side_effect=save_with_drift), self.assertRaises(ValueError):
                    run_context(context)
                self.assertTrue((output / 'failure.json').exists())
                self.assertTrue((output / 'history.json').exists())


if __name__ == '__main__':
    unittest.main()
