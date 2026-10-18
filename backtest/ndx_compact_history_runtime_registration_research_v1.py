"""Validate a compact-history run registration without IO or authority.

The host supplies trusted runtime/dependency references and research root.
This plan does not authenticate the registration, source bytes or directories.
"""
from copy import deepcopy
from pathlib import PureWindowsPath
import re

SCHEMA = "COMPACT_HISTORY_RUNTIME_REGISTRATION_V1"
PLAN_SCHEMA = "COMPACT_HISTORY_RUNTIME_PLAN_V1"
ANCHOR_ROLES = ("reference", "publication_reference", "readback_reference", "reader_reference")
OBSERVATION_ROLES = ("payload_reference", "receipt_reference", "audit_reference", "reader_reference")
DEPENDENCY_ROLES = ("history_core", "compact_helpers")
FLAGS = dict.fromkeys(("source_authenticity_verified", "clock_authenticity_verified",
    "filesystem_attempt_inventory_authenticated", "point_in_time_verified",
    "candidate_seal_allowed", "cohort_registration_allowed", "promotion_allowed",
    "live_mutation_allowed", "future_independent_oos", "observation_created"), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical_path(value):
    require(type(value) is str and value and value == value.strip(), "Explicit absolute path")
    path = PureWindowsPath(value)
    require(path.is_absolute() and re.fullmatch(r"[A-Za-z]:", path.drive) is not None,
        "Absolute local drive path; no UNC or device namespace")
    require(not any(part in (".", "..") for part in value.replace("\\", "/").split("/")),
        "No relative path components")
    require(not any(":" in part or part.endswith((" ", ".")) for part in path.parts[1:]),
        "No stream or ambiguous path components")
    reserved = {"con", "prn", "aux", "nul", *("com" + str(i) for i in range(1, 10)),
        *("lpt" + str(i) for i in range(1, 10))}
    for part in path.parts[1:]:
        require(not any(ord(char) < 32 or char in '<>"|?*' for char in part),
            "No Windows special path characters")
        require(part.split(".")[0].casefold() not in reserved, "No reserved device names")
    return path


def reference(value, claims):
    require(type(value) is dict and set(value) == {"path", "sha256"}, "Exact reference fields")
    path = canonical_path(value["path"])
    digest = value["sha256"]
    require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
        "Non-pending lowercase SHA256")
    key = str(path).casefold()
    require(key not in claims or claims[key]["sha256"] == digest, "Conflicting path aliases")
    claims[key] = deepcopy(value)
    return path


def reference_roles(value, roles, claims):
    require(type(value) is dict and set(value) == set(roles), "Complete exact reference roles")
    for role in roles:
        reference(value[role], claims)


def prepare_compact_history_runtime(*, registration, registration_reference,
        runtime_reference, dependency_references, research_root):
    """Return a create-only run plan after validating all supplied bindings.

    Runtime and dependency references are trusted host configuration, never
    accepted solely because the untrusted registration declares them.
    """
    claims = {}
    registration_path = reference(registration_reference, claims)
    reference(runtime_reference, claims)
    reference_roles(dependency_references, DEPENDENCY_ROLES, claims)
    root = canonical_path(research_root)
    expected = {"schema", "runtime_reference", "dependency_references", "parent",
        "observation", "output_directory", *FLAGS}
    require(type(registration) is dict and set(registration) == expected,
        "Exact compact runtime registration fields")
    require(registration["schema"] == SCHEMA, "Compact registration version")
    for key in FLAGS:
        require(registration[key] is False, "Strict false authority flag " + key)
    require(registration["runtime_reference"] == runtime_reference, "Host runtime binding")
    require(registration["dependency_references"] == dependency_references,
        "Host dependency bindings")
    reference_roles(registration["parent"], ANCHOR_ROLES, claims)
    reference_roles(registration["observation"], OBSERVATION_ROLES, claims)
    output = canonical_path(registration["output_directory"])
    require(output.parent == root and output != root, "Direct child of trusted research root")
    require(re.fullmatch(r"[a-z][a-z0-9_]{2,119}", output.name) is not None,
        "Explicit stable output namespace")
    for item in claims.values():
        source = canonical_path(item["path"])
        require(source != output and output not in source.parents, "Output aliases an input namespace")
    require(registration_path != output, "Registration cannot be output")
    return dict(schema=PLAN_SCHEMA, registration_reference=deepcopy(registration_reference),
        runtime_reference=deepcopy(runtime_reference),
        dependency_references=deepcopy(dependency_references),
        parent=deepcopy(registration["parent"]), observation=deepcopy(registration["observation"]),
        output_directory=str(output), create_only=True, automatic_retry_allowed=False,
        registration_bytes_verified=False, source_bytes_verified=False,
        output_namespace_verified=False, source_reference_claims={
            item["path"]: item["sha256"] for item in claims.values()}, **FLAGS)
