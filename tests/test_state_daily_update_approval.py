from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backtest.state_daily_update_approval import (
    APPROVAL_PLAN_KEYS,
    StateDailyUpdateApprovalError,
    apply_approved_plan,
    canonical_sha256,
    refresh_approval_plan,
    verify_daily_update_preview,
)
from data.versioning import file_sha256


class StateDailyUpdateApprovalTests(unittest.TestCase):
    def test_preview_without_broker_hash_binding_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "data/cache/research/state_daily_update_preview_v1/manifest.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "schema_version": 1,
                "manifest_type": "state_daily_update_preview",
                "generated_at": "2026-09-05T00:00:00+00:00",
                "status": "USER_APPROVAL_REQUIRED_NOT_APPLIED",
                "latest_completed_session": "2026-09-03",
                "state_freshness": {}, "impact": {}, "approval_boundary": {},
                "inputs": {"state": {}, "config": {}}, "artifacts": {},
            }), encoding="utf-8")
            with self.assertRaisesRegex(StateDailyUpdateApprovalError, "bind state, config, and broker"):
                verify_daily_update_preview(path, repository_root=root)

    def test_default_plan_never_writes_state(self) -> None:
        token = "one-time-token"
        verified = {
            "plan": {
                "request_id": "request", "session_date": "2026-09-03",
                "approval_token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            },
            "preview": {}, "token": token, "consumed_marker": Path("unused"),
        }
        with patch(
            "backtest.state_daily_update_approval.verify_approval_plan",
            return_value=verified,
        ), patch("backtest.state_daily_update_approval.save_portfolio") as save:
            result = apply_approved_plan(
                "plan.json", repository_root=".", approval_token="", apply=False,
            )
        self.assertEqual(result["status"], "PLAN_VERIFIED_NOT_APPLIED")
        self.assertFalse(result["state_written"])
        save.assert_not_called()

    def test_wrong_one_time_token_fails_before_state_write(self) -> None:
        token = "one-time-token"
        verified = {
            "plan": {
                "request_id": "request", "session_date": "2026-09-03",
                "approval_token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            },
            "preview": {}, "token": token, "consumed_marker": Path("unused"),
        }
        with patch(
            "backtest.state_daily_update_approval.verify_approval_plan",
            return_value=verified,
        ), patch("backtest.state_daily_update_approval.save_portfolio") as save:
            with self.assertRaisesRegex(StateDailyUpdateApprovalError, "token mismatch"):
                apply_approved_plan(
                    "plan.json", repository_root=".", approval_token="wrong", apply=True,
                )
        save.assert_not_called()

    def test_post_write_failure_restores_approved_rollback_before_error(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state, proposed = root / "state.json", root / "proposed.json"
            rollback, config, broker = root / "rollback.json", root / "config.yaml", root / "broker.json"
            state.write_bytes(b"before-state\n")
            rollback.write_bytes(state.read_bytes())
            proposed.write_bytes(b"approved-after\n")
            config.write_bytes(b"config\n")
            broker.write_bytes(b"broker\n")
            token = "one-time-token"
            consumed = root / "consumed.json"
            plan = {
                "request_id": "request", "session_date": "2026-09-03",
                "approval_token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                "expected_live_inputs": {
                    "state": {"sha256": file_sha256(state)},
                    "config": {"sha256": file_sha256(config)},
                    "broker": {"sha256": file_sha256(broker)},
                },
            }
            verified = {
                "plan": plan,
                "preview": {
                    "expected_inputs": {"state": state, "config": config, "broker": broker},
                    "proposed": object(), "paths": {"proposed": proposed, "rollback": rollback},
                },
                "token": token, "consumed_marker": consumed,
            }
            def corrupt_write(*_args):
                state.write_bytes(b"corrupt-partial-state\n")
            with patch(
                "backtest.state_daily_update_approval.verify_approval_plan",
                return_value=verified,
            ), patch(
                "backtest.state_daily_update_approval.save_portfolio",
                side_effect=corrupt_write,
            ):
                with self.assertRaisesRegex(StateDailyUpdateApprovalError, "rollback restored"):
                    apply_approved_plan(
                        "plan.json", repository_root=root, approval_token=token, apply=True,
                    )
            self.assertEqual(state.read_bytes(), rollback.read_bytes())
            self.assertFalse(consumed.exists())

    def test_refresh_archives_expired_plan_and_publishes_new_pointer(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "data/cache/research/state_daily_update_approval_v1"
            output.mkdir(parents=True)
            old = {key: None for key in APPROVAL_PLAN_KEYS}
            old.update({
                "schema_version": 1,
                "manifest_type": "state_daily_update_one_time_approval_plan",
                "status": "AWAITING_EXPLICIT_USER_APPROVAL_NOT_APPLIED",
                "request_id": "old-request",
                "created_at_utc": "2026-09-01T00:00:00+00:00",
                "expires_at_utc": "2026-09-02T00:00:00+00:00",
            })
            unsigned = dict(old)
            unsigned.pop("manifest_sha256")
            old["manifest_sha256"] = canonical_sha256(unsigned)
            old_bytes = (json.dumps(old, sort_keys=True) + "\n").encode()
            (output / "approval_plan.json").write_bytes(old_bytes)
            (output / "approval_token.txt").write_text("old-token\n", encoding="utf-8")

            def publish(*_args, **_kwargs):
                (output / "approval_plan.json").write_text('{"new":true}\n', encoding="utf-8")
                (output / "approval_token.txt").write_text("new-token\n", encoding="utf-8")
                return ({"request_id": "new-request"}, "new-token")

            with patch(
                "backtest.state_daily_update_approval.verify_daily_update_preview",
                return_value={},
            ), patch(
                "backtest.state_daily_update_approval.build_approval_plan",
                side_effect=publish,
            ):
                result, _ = refresh_approval_plan(
                    "preview.json", repository_root=root, output_dir=output,
                )
            self.assertEqual(result["request_id"], "new-request")
            self.assertEqual(
                (output / "archive/old-request/approval_plan.json").read_bytes(),
                old_bytes,
            )
            self.assertEqual((output / "approval_plan.json").read_text(), '{"new":true}\n')


if __name__ == "__main__":
    unittest.main()
