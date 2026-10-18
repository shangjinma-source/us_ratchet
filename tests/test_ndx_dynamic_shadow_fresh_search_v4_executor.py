"""Executor provenance regression with real final artifacts and role ledger.

The small search panel is a synthetic fixture, not a candidate-input replay.
Candidate public validation and controller execution are deliberately outside
this test; no final or role-ledger verifier is replaced by a mock.
"""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd
import test_ndx_dynamic_shadow_fresh_search as fixture
from scripts import ndx_dynamic_shadow_fresh_search_v2 as controller
from scripts import ndx_dynamic_shadow_fresh_search_v4 as v4
from backtest import ndx_dynamic_shadow_fresh_search as engine


class FinalExecutorBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        adjusted, nominal, target, liquidity = fixture._panels()
        cls.jobs = fixture._jobs()
        cls.frames = []
        for row in cls.jobs.itertuples(index=False):
            results, _ = engine.execute_fresh_shard(
                row._asdict(), eligible=fixture._eligible(),
                adjusted_close=adjusted, nominal_close=nominal,
                target_aligned=target, liquidity=liquidity,
                incumbent=fixture.INCUMBENT, incumbent_weights=fixture._weights(),
                contract=fixture._contract(),
            )
            cls.frames.append(results)

    def _check_final(self, stale_executor=False, stale_original8=False):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve()
            stack.enter_context(patch.object(v4, "ROOT", root))
            stack.enter_context(patch.object(controller, "ROOT", root))
            for name in v4.CODE_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"executor fixture source\n")
            expected = controller._executor_hash()
            executor = "f" * 64 if stale_executor else expected
            binding = dict(snapshot_sha256="d" * 64,
                           snapshot_fingerprint="a" * 64,
                           snapshot_path=(root / "input.json").as_posix(),
                           candidate_source_versions={"frozen_original8_manifest_sha256": "c" * 64},
                           wrapper_sources={name: v4.digest(root / name) for name in v4.CODE_FILES})
            snapshot = dict(decision_date="2026-10-01", source_versions=binding["candidate_source_versions"])
            original8 = "e" * 64 if stale_original8 else "c" * 64
            stack.enter_context(patch.object(
                v4.candidate.v1, "_verify_manifest_seal_record",
                return_value={"record_sha256": "8" * 64},
            ))
            frames = []
            for row, original in zip(self.jobs.itertuples(index=False), self.frames):
                frame = original.copy(deep=True)
                frame["coordinate_hash"] = engine.coordinate_hash(
                    row._asdict(), snapshot_manifest_sha256=binding["snapshot_sha256"],
                    executor_sha256=executor, original_8_sha256=original8,
                )
                frames.append(frame)
            candidates, roles = engine.freeze_cross_k_roles(pd.concat(frames, ignore_index=True))
            final_root = root / v4.SEARCH / "final"
            final_dir = final_root / snapshot["decision_date"]
            engine.write_final_candidate_snapshot(
                final_dir, candidates, roles, self.jobs,
                snapshot_manifest_sha256=binding["snapshot_sha256"],
                snapshot_fingerprint=binding["snapshot_fingerprint"],
                executor_sha256=executor, original_8_sha256=original8,
                snapshot_seal_record_sha256="8" * 64,
            )
            path = final_dir / "manifest.json"
            ledger = root / v4.SEARCH / "role_seals.jsonl"
            engine.append_role_seal_record(ledger, path, expected_final_root=final_root)
            # The legacy validators accept both internally consistent versions.
            engine.verify_final_candidate_snapshot(path)
            engine.verify_final_role_seal_record(path, ledger, expected_final_root=final_root)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            if stale_executor:
                with self.assertRaisesRegex(ValueError, "executor"):
                    v4.final_binding(snapshot, binding)
            elif stale_original8:
                with self.assertRaisesRegex(ValueError, "original.?8"):
                    v4.final_binding(snapshot, binding)
            else:
                self.assertEqual(v4.final_binding(snapshot, binding)["sha256"], v4.digest(path))
            after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertFalse((root / v4.ACCEPTANCE).exists())

    def test_current_executor_final_passes_real_verifiers(self):
        self._check_final(False)

    def test_self_consistent_stale_executor_final_is_rejected(self):
        self._check_final(True)

    def test_self_consistent_different_original8_final_is_rejected(self):
        self._check_final(stale_original8=True)
