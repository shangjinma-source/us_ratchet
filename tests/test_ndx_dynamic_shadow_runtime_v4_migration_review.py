from pathlib import Path
import ast
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backtest import ndx_dynamic_shadow_runtime_v4_migration_review as review

ROOT = Path(__file__).resolve().parents[1]


class MigrationReviewTests(unittest.TestCase):
    def test_local_import_sources_are_in_review_inventory(self):
        missing = set()
        inventory = set(review.SOURCES) | set(review.REQUIRED_COMPONENTS)
        for name in inventory:
            if not name.endswith(".py") or not (ROOT / name).is_file():
                continue
            for node in ast.walk(ast.parse((ROOT / name).read_text(encoding="utf-8"))):
                modules = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                           else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                for module in modules:
                    relative = module.replace(".", "/")
                    for candidate in (relative + ".py", relative + "/__init__.py", "tests/" + relative + ".py"):
                        if (ROOT / candidate).is_file() and candidate not in inventory:
                            missing.add(candidate)
        self.assertEqual(missing, set())

    def fixture(self, root):
        for relative in review.SOURCES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / relative).read_bytes())

    def test_draft_is_deterministic_and_never_authorizes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            draft = review.build_review_draft(root)
            self.assertEqual(draft, review.build_review_draft(root))
            self.assertEqual(draft["status"], "REVIEW_DRAFT_NOT_AUTHORIZATION")
            self.assertEqual(set(draft["missing_required_components"]), set(review.REQUIRED_COMPONENTS))
            self.assertTrue(all(value is False for value in draft["boundaries"].values()))
            self.assertFalse(draft["activation_snapshot"]["full_verification_performed"])

    def test_component_appearance_invalidates_previous_draft_not_auto_approval(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            path = root / review.REVIEW_PATH
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(review.build_review_draft(root)), encoding="utf-8")
            review.verify_review_draft(path, repository_root=root)
            component = root / review.REQUIRED_COMPONENTS[0]
            component.write_text("# incomplete installer", encoding="utf-8")
            with self.assertRaises(ValueError):
                review.verify_review_draft(path, repository_root=root)
            self.assertEqual(review.build_review_draft(root)["status"], "REVIEW_DRAFT_NOT_AUTHORIZATION")

    def test_resigned_authorization_or_numeric_false_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            path = root / review.REVIEW_PATH
            path.parent.mkdir(parents=True)
            for value in (True, 0):
                draft = review.build_review_draft(root)
                draft["boundaries"]["cutover_allowed"] = value
                draft.pop("review_sha256")
                draft["review_sha256"] = review._sha(review._canonical(draft).encode())
                path.write_text(json.dumps(draft), encoding="utf-8")
                with self.assertRaises(ValueError):
                    review.verify_review_draft(path, repository_root=root)

    def test_capture_drift_and_noncanonical_path_rejected(self):
        captured = {"sources": {}, "missing_required_components": [], "activation_snapshot": {}}
        with patch.object(review, "_capture", side_effect=[captured, {**captured, "sources": {"changed": {}}}]):
            with self.assertRaises(ValueError):
                review.build_review_draft(ROOT)
        with self.assertRaises(ValueError):
            review.verify_review_draft(ROOT / "other.json", repository_root=ROOT)


if __name__ == "__main__":
    unittest.main()
