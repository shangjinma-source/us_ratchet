from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch

from backtest import ndx_compact_implementation_pair_binding_research_v1 as module


def reference(name):
    return {"path": "E:/synthetic/pair/" + name + ".json",
        "sha256": hashlib.sha256(name.encode()).hexdigest()}


def arguments():
    dependencies = {role: {key: reference(key) for key in roles}
        for role, roles in module.DEPENDENCY_ROLES.items()}
    binding = dict(schema=module.SCHEMA, family=module.FAMILY,
        protocol=module.PROTOCOL, role=module.ROLE,
        publisher_reference=reference("publisher"),
        independent_reader_reference=reference("reader"),
        contract_reference=reference("contract"),
        publisher_dependency_references=deepcopy(dependencies["publisher"]),
        reader_dependency_references=deepcopy(dependencies["independent_reader"]),
        approved_legacy_binding_references=[], **module.FLAGS)
    return dict(binding=binding, binding_reference=reference("binding"),
        host_binding_reference=reference("binding"), self_role="publisher",
        self_reference=reference("publisher"), expected_contract_reference=reference("contract"),
        expected_algorithm_dependencies=dependencies)


class PairBindingTests(unittest.TestCase):
    def test_pair_both_roles_detached_and_no_io(self):
        for role, name in (("publisher", "publisher"), ("independent_reader", "reader")):
            value = arguments()
            value.update(self_role=role, self_reference=reference(name))
            original = deepcopy(value)
            with patch("builtins.open", side_effect=AssertionError("Pure module must not read")), \
                    patch("pathlib.Path.read_bytes", side_effect=AssertionError("No bytes")):
                result = module.inspect_pair_binding(**value)
            self.assertEqual(value, original)
            self.assertEqual(result["binding_reference"], value["host_binding_reference"])
            for key in module.FLAGS:
                self.assertIs(result[key], False)
            result["algorithm_dependency_references"][role].clear()
            self.assertEqual(value, original)

    def test_host_binding_and_self_are_independent(self):
        for key, substitute in (("binding_reference", reference("untrusted")),
                ("host_binding_reference", reference("untrusted")),
                ("self_reference", reference("reader")), ("self_role", "unknown"),
                ("expected_contract_reference", reference("untrusted"))):
            with self.subTest(key=key):
                value = arguments()
                value[key] = substitute
                with self.assertRaises(ValueError):
                    module.inspect_pair_binding(**value)

    def test_closed_fields_and_false_identity(self):
        for key in module.FLAGS:
            for bad in (True, 0, None, "false"):
                with self.subTest(key=key, bad=bad):
                    value = arguments()
                    value["binding"][key] = bad
                    with self.assertRaises(ValueError):
                        module.inspect_pair_binding(**value)
            value = arguments()
            del value["binding"][key]
            with self.assertRaises(ValueError):
                module.inspect_pair_binding(**value)
        for key in ("root_approved", "cash", "binding_reference"):
            value = arguments()
            value["binding"][key] = True
            with self.assertRaises(ValueError):
                module.inspect_pair_binding(**value)

    def test_dependencies_closed_and_not_self_authorizing(self):
        for role, roles in module.DEPENDENCY_ROLES.items():
            for key in roles:
                value = arguments()
                del value["expected_algorithm_dependencies"][role][key]
                with self.assertRaises(ValueError):
                    module.inspect_pair_binding(**value)
                value = arguments()
                field = "publisher_dependency_references" if role == "publisher" else "reader_dependency_references"
                value["binding"][field][key] = reference("other")
                with self.assertRaises(ValueError):
                    module.inspect_pair_binding(**value)
        for special in ("binding", "publisher", "reader", "contract"):
            value = arguments()
            value["expected_algorithm_dependencies"]["publisher"]["history_core"] = reference(special)
            value["binding"]["publisher_dependency_references"]["history_core"] = reference(special)
            with self.assertRaises(ValueError):
                module.inspect_pair_binding(**value)

    def test_references_pending_aliases_and_distinct_peers(self):
        for bad in (None, True, "f" * 63, "A" * 64, float("nan"), float("inf")):
            value = arguments()
            value["binding_reference"]["sha256"] = bad
            with self.assertRaises(ValueError):
                module.inspect_pair_binding(**value)
        for path in ("../binding.json", "E:/synthetic/../binding.json", "//host/share/x", "E:/con.json"):
            value = arguments()
            value["binding_reference"]["path"] = path
            with self.assertRaises(ValueError):
                module.inspect_pair_binding(**value)
        value = arguments()
        value["binding_reference"]["path"] = value["binding_reference"]["path"].upper()
        with self.assertRaises(ValueError):
            module.inspect_pair_binding(**value)
        for property in ("path", "sha256"):
            value = arguments()
            value["binding"]["independent_reader_reference"][property] = value["self_reference"][property]
            with self.assertRaises(ValueError):
                module.inspect_pair_binding(**value)
        value = arguments()
        value["self_reference"]["authority"] = True
        with self.assertRaises(ValueError):
            module.inspect_pair_binding(**value)

    def test_flat_host_selected_legacy_allowlist(self):
        value = arguments()
        legacy = [reference("old_binding")]
        value["approved_legacy_binding_references"] = legacy
        value["binding"]["approved_legacy_binding_references"] = deepcopy(legacy)
        self.assertEqual(module.inspect_pair_binding(**value)["approved_legacy_binding_references"], legacy)
        for bad in ([reference("binding")], legacy * 2, legacy * 129,
                [{"binding": reference("old_binding")}], [reference("publisher")]):
            value = arguments()
            value["approved_legacy_binding_references"] = deepcopy(bad)
            value["binding"]["approved_legacy_binding_references"] = deepcopy(bad)
            with self.assertRaises(ValueError):
                module.inspect_pair_binding(**value)
        value = arguments()
        value["binding"]["approved_legacy_binding_references"] = legacy
        with self.assertRaises(ValueError):
            module.inspect_pair_binding(**value)


if __name__ == "__main__":
    unittest.main()
