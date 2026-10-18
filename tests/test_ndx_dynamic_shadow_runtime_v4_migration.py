"""Independent readiness adversaries; OS and activation boundaries are mocked.

No test authorizes registration or claims a Scheduled Task smoke succeeded.
"""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backtest import ndx_dynamic_shadow_runtime_v4_migration as migration


ROOT = Path(__file__).resolve().parents[1]
TASKS = (
    "us_ratchet_ndx_dynamic_shadow_selection_daily",
    "us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted",
    "us_ratchet_ndx_dynamic_shadow_selection_daily_v3_reviewed_calendar",
)
NEW_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily_v4_accepted_receipts"


def inventory():
    names = ("ndx_dynamic_shadow_daily.py", "ndx_dynamic_shadow_daily_v2.py",
             "ndx_dynamic_shadow_daily_v3.py")
    return [dict(task_name=name, task_path="\\", enabled=index == 2,
                 state="Ready" if index == 2 else "Disabled",
                 execute=r"D:\python\python.exe",
                 arguments=f'-B "{ROOT / "scripts" / script}" --execute',
                 working_directory=str(ROOT))
            for index, (name, script) in enumerate(zip(TASKS, names))]


class RuntimeV4ReadinessTests(unittest.TestCase):
    def build(self, *, tasks=None, processes=None, openclaw=None, activation=None,
              task_reads=None):
        with ExitStack() as stack:
            stack.enter_context(patch.object(migration, "_recheck_activation_bindings"))
            stack.enter_context(patch.object(migration, "_activation_gate", return_value=(
                {"passed": True, "full_verifier_replayed": True}
                if activation is None else activation)))
            stack.enter_context(patch.object(migration, "_task_inventory",
                **({"side_effect": task_reads} if task_reads is not None else
                   {"return_value": inventory() if tasks is None else tasks})))
            stack.enter_context(patch.object(migration, "_process_inventory",
                return_value=[] if processes is None else processes))
            stack.enter_context(patch.object(migration, "_openclaw_duplicates",
                return_value=[] if openclaw is None else openclaw))
            return migration.build_runtime_v4_migration_readiness(repository_root=ROOT)

    def blocked(self, **kwargs):
        self.assertEqual(self.build(**kwargs)["status"], "BLOCKED_FAIL_CLOSED")

    def test_ready_means_review_only_not_authorization(self):
        result = self.build()
        self.assertEqual(result["status"], "READY_FOR_V4_MIGRATION_REVIEW_ONLY")
        for key in ("migration_performed", "task_mutation_performed",
                    "live_mutation_allowed", "orders_allowed"):
            self.assertIs(result[key], False)

    def test_missing_full_activation_cannot_be_replaced_by_truthy_values(self):
        for gate in ({}, {"passed": False}, {"passed": True},
                     {"passed": 1, "full_verifier_replayed": True},
                     {"passed": True, "full_verifier_replayed": 1}):
            with self.subTest(gate=gate):
                self.blocked(activation=gate)

    def test_legacy_enabled_running_or_missing_predecessor_blocks(self):
        for index in range(3):
            changed = inventory()
            changed[index]["enabled"] = not changed[index]["enabled"]
            self.blocked(tasks=changed)
            changed = inventory()
            changed[index]["state"] = "Running"
            self.blocked(tasks=changed)
        self.blocked(tasks=inventory()[:2])

    def test_duplicate_action_nonroot_and_preexisting_v4_block(self):
        changed = inventory()
        self.blocked(tasks=changed + [deepcopy(changed[2])])
        changed[2]["task_path"] = "\\Other\\"
        self.blocked(tasks=changed)
        new = dict(inventory()[2], task_name=NEW_TASK, enabled=False, state="Disabled")
        self.blocked(tasks=inventory() + [new])

    def test_predecessor_action_and_working_directory_are_exact(self):
        for key, value in (("execute", r"C:\other\python.exe"),
                           ("arguments", "-B other.py --execute"),
                           ("working_directory", str(ROOT.parent))):
            changed = inventory()
            changed[2][key] = value
            self.blocked(tasks=changed)

    def test_inconsistent_or_untyped_task_states_fail_closed(self):
        for index, key, value in ((2, "state", "Disabled"), (0, "state", "Ready"),
                (2, "state", "Queued"), (2, "state", "Unknown"),
                (2, "enabled", 1), (0, "enabled", 0), (0, "enabled", "false")):
            changed = inventory()
            changed[index][key] = value
            self.blocked(tasks=changed)

    def test_duplicate_nonroot_same_name_and_extra_arguments_block(self):
        duplicate = dict(inventory()[2], task_path="\\Other\\")
        self.blocked(tasks=inventory() + [duplicate])
        changed = inventory()
        changed[2]["arguments"] += " --other-policy"
        self.blocked(tasks=changed)

    def test_second_process_and_openclaw_observation_cannot_be_skipped(self):
        for name, later in (("_process_inventory", [{"process_id": 42,
                "command_line": "python ndx_dynamic_shadow_daily_v4.py --execute"}]),
                ("_openclaw_duplicates", [{"name": "new duplicate", "enabled": True}])):
            for observations in ([[], later], [[], OSError("second query failed")]):
                with ExitStack() as stack:
                    stack.enter_context(patch.object(migration, "_recheck_activation_bindings"))
                    stack.enter_context(patch.object(migration, "_activation_gate", return_value={
                        "passed": True, "full_verifier_replayed": True}))
                    for function, value in (("_task_inventory", inventory()),
                                             ("_process_inventory", []),
                                             ("_openclaw_duplicates", [])):
                        stack.enter_context(patch.object(migration, function,
                            **({"side_effect": observations} if function == name else {"return_value": value})))
                    result = migration.build_runtime_v4_migration_readiness(repository_root=ROOT)
                    self.assertEqual(result["status"], "BLOCKED_FAIL_CLOSED")

    def test_unexpected_windows_or_openclaw_schedulers_block(self):
        extra = dict(inventory()[2], task_name="OTHER",
                     arguments="NDX_DYNAMIC_SHADOW_FRESH_SEARCH_V4.PY --EXECUTE")
        self.blocked(tasks=inventory() + [extra])
        self.blocked(openclaw=[{"name": "duplicate", "enabled": True}])

    def test_all_new_and_legacy_runtime_processes_block(self):
        for script, flag in (("ndx_dynamic_shadow_daily_v4.py", "--execute"),
                             ("ndx_dynamic_shadow_daily_v3.py", "--execute"),
                             ("ndx_dynamic_shadow_fresh_search_v4.py", "--execute"),
                             ("ndx_dynamic_shadow_candidate_generator_v3.py", "--seal")):
            self.blocked(processes=[{"process_id": 42,
                "command_line": f'python "{ROOT / "scripts" / script}" {flag}'.upper()}])

    def test_module_launch_and_unreadable_command_line_block(self):
        for command in ("python -m scripts.ndx_dynamic_shadow_daily_v4 --execute",
                        "python scripts/ndx_dynamic_shadow_daily_v4.py --exec",
                        "python scripts/ndx_dynamic_shadow_candidate_generator_v3.py --se",
                        "python -m scripts.ndx_dynamic_shadow_candidate_generator_v3 --seal",
                        "", None):
            self.blocked(processes=[{"process_id": 42, "command_line": command}])

    def test_task_inventory_drift_cannot_return_ready(self):
        changed = inventory()
        changed[2]["state"] = "Running"
        self.blocked(task_reads=[inventory(), changed])

    def test_os_inspection_failure_is_fail_closed(self):
        self.blocked(task_reads=OSError("inventory unavailable"))

    def test_actual_activation_gate_calls_v5_full_verifier(self):
        from backtest import ndx_dynamic_shadow_activation_v5 as activation
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / migration.ACTIVATION_RELATIVE
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}", encoding="utf-8")
            daily = root / migration.DAILY_RELATIVE
            daily.parent.mkdir(parents=True)
            daily.write_text("# fixture", encoding="utf-8")
            value = {"manifest_type": "ndx_dynamic_shadow_activation_v5", "status": activation.STATUS,
                     "sources": {migration.DAILY_RELATIVE.as_posix(): {
                         "path": str(daily), "sha256": migration._digest(daily)}},
                     "boundaries": dict(activation.BOUNDARIES)}
            with patch.object(migration, "PYTHON", daily), \
                    patch.object(activation, "verify_activation_v5_manifest", return_value=value) as full:
                result = migration._activation_gate(root)
                full.assert_called_once_with(manifest, repository_root=root)
                self.assertIs(result["passed"], True)
                migration._recheck_activation_bindings(root, result)
                daily.write_text("# drift", encoding="utf-8")
                with self.assertRaises(migration.RuntimeV4MigrationError):
                    migration._recheck_activation_bindings(root, result)
                self.assertIs(migration._activation_gate(root)["passed"], False)

    def test_missing_bound_sources_cannot_skip_post_verification(self):
        with self.assertRaises(migration.RuntimeV4MigrationError):
            migration._recheck_activation_bindings(ROOT, {"passed": True})


if __name__ == "__main__":
    unittest.main()
