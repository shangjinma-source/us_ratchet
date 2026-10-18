import unittest
from copy import deepcopy
from backtest import ndx_compact_history_runtime_registration_research_v1 as core


def ref(path, digit="a"):
    return dict(path=path, sha256=digit * 64)


def fixture():
    runtime = ref("E:/Git/us_ratchet/scripts/registered_compact_runtime.py")
    dependencies = {role: ref("E:/Git/us_ratchet/backtest/" + role + ".py")
        for role in core.DEPENDENCY_ROLES}
    parent = {role: ref("E:/Git/us_ratchet/data/cache/research/parent/" + role + ".json")
        for role in core.ANCHOR_ROLES}
    observation = {role: ref("E:/Git/us_ratchet/data/cache/research/actual/" + role + ".json")
        for role in core.OBSERVATION_ROLES}
    root = "E:/Git/us_ratchet/data/cache/research"
    registration = dict(schema=core.SCHEMA, runtime_reference=deepcopy(runtime),
        dependency_references=deepcopy(dependencies), parent=parent, observation=observation,
        output_directory=root + "/compact_history_example_v1", **core.FLAGS)
    return dict(registration=registration,
        registration_reference=ref("E:/Git/us_ratchet/research_contracts/compact_example.json"),
        runtime_reference=runtime, dependency_references=dependencies, research_root=root)


class RegisteredCompactRuntimeTest(unittest.TestCase):
    def test_complete_roles_plan_is_detached_and_grants_no_byte_authority(self):
        args = fixture(); plan = core.prepare_compact_history_runtime(**args)
        self.assertTrue(plan["create_only"])
        self.assertFalse(plan["registration_bytes_verified"])
        self.assertFalse(plan["source_bytes_verified"])
        self.assertFalse(plan["output_namespace_verified"])
        self.assertFalse(plan["automatic_retry_allowed"])
        for key in core.FLAGS: self.assertIs(plan[key], False)
        args["registration"]["parent"]["reference"]["path"] = "changed"
        self.assertNotEqual(plan["parent"]["reference"]["path"], "changed")

    def test_same_runtime_reused_for_later_actual_without_source_edit(self):
        first = fixture(); second = deepcopy(first)
        second["registration_reference"] = ref("E:/Git/us_ratchet/research_contracts/next.json", "b")
        second["registration"]["parent"] = {role: ref("E:/Git/us_ratchet/data/cache/research/next_parent/" + role + ".json", "c") for role in core.ANCHOR_ROLES}
        second["registration"]["observation"] = {role: ref("E:/Git/us_ratchet/data/cache/research/next_actual/" + role + ".json", "d") for role in core.OBSERVATION_ROLES}
        second["registration"]["output_directory"] = first["research_root"] + "/compact_history_next_v1"
        one = core.prepare_compact_history_runtime(**first)
        two = core.prepare_compact_history_runtime(**second)
        self.assertEqual(one["runtime_reference"], two["runtime_reference"])
        self.assertNotEqual(one["parent"], two["parent"])
        self.assertNotEqual(one["output_directory"], two["output_directory"])

    def test_registration_cannot_choose_its_own_runtime_or_dependency(self):
        for role in ["runtime_reference", *core.DEPENDENCY_ROLES]:
            with self.subTest(role=role):
                args=fixture()
                if role=="runtime_reference": args["registration"][role]["sha256"]="b"*64
                else: args["registration"]["dependency_references"][role]["sha256"]="b"*64
                with self.assertRaises(ValueError): core.prepare_compact_history_runtime(**args)

    def test_pending_missing_and_extra_upstream_roles_reject(self):
        for variant in ["pending", "missing", "extra"]:
            with self.subTest(variant=variant):
                args=fixture(); refs=args["registration"]["observation"]
                if variant=="pending": refs["audit_reference"]["sha256"]=None
                elif variant=="missing": del refs["audit_reference"]
                else: refs["fake"]=ref("E:/fake.json")
                with self.assertRaises(ValueError): core.prepare_compact_history_runtime(**args)

    def test_authority_and_unknown_registration_fields_reject(self):
        for flag in [*core.FLAGS, "execute_live"]:
            with self.subTest(flag=flag):
                args=fixture(); args["registration"][flag]=True
                with self.assertRaises(ValueError): core.prepare_compact_history_runtime(**args)

    def test_path_escape_stream_device_and_input_namespace_reject(self):
        args=fixture();root=args["research_root"]
        paths=["relative", "//server/share/output", root+"/../escape", root+"/nested/output",
            root+"/output:stream", root+"/con", root+"/nul.txt", root+"/output.",
            root+"/output ", root+"/bad?name", root+"/actual", root]
        for path in paths:
            with self.subTest(path=path):
                case=fixture();case["registration"]["output_directory"]=path
                with self.assertRaises(ValueError):core.prepare_compact_history_runtime(**case)

    def test_case_and_slash_alias_conflicting_digest_reject(self):
        args=fixture()
        args["registration"]["observation"]["reader_reference"]=ref(
            args["runtime_reference"]["path"].upper().replace("/", "\\"), "b")
        with self.assertRaisesRegex(ValueError,"Conflicting path aliases"):
            core.prepare_compact_history_runtime(**args)

    def test_non_boolean_false_reject(self):
        for value in [0,None,"false"]:
            args=fixture();args["registration"]["future_independent_oos"]=value
            with self.assertRaises(ValueError):core.prepare_compact_history_runtime(**args)


if __name__ == "__main__": unittest.main()
