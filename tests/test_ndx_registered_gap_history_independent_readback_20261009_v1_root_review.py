"""Root physical tests: independent execution boundary and raw artifact identity."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_gap_history_independent_readback_20261009_v1 as reader
import test_ndx_registered_gap_history_independent_readback_20261009_v1 as fixtures


class RootGapReaderReview(unittest.TestCase):
    def test_entire_physical_readback_cannot_compile_production_algorithms(self):
        with TemporaryDirectory(prefix="SYNTHETIC_ROOT_GAP_READER_") as folder:
            context, result = fixtures.published_context(Path(folder))
            forbidden = {reader.PRODUCER, *(reader.ROOT / reader.DEPENDENCIES[key][0]
                for key in ("gap_core", "prefix_core", "scoped", "base"))}
            original = reader.private_module
            compiled = []
            def guard(path, raw, expected, replacements=()):
                self.assertNotIn(Path(path), forbidden)
                compiled.append(Path(path))
                return original(path, raw, expected, replacements)
            with patch.object(reader, "private_module", side_effect=guard):
                ref = fixtures.read_context(context, result)
            report = reader.decode(Path(ref["path"]).read_bytes())
            self.assertTrue(report["entire_history_independently_reconstructed"])
            for path in (reader.INDEPENDENT_GAP[0], reader.INDEPENDENT_PREFIX[0], reader.CSV_READER[0]):
                self.assertIn(path, compiled)
            self.assertFalse(report["publisher_called"])
            self.assertFalse(report["producer_prefix_core_called"])

    def test_resigned_raw_prefix_evidence_and_noncanonical_envelopes_rejected(self):
        with TemporaryDirectory(prefix="SYNTHETIC_ROOT_GAP_RAW_ATTACK_") as folder:
            context, result = fixtures.published_context(Path(folder))
            history_path = Path(result["history_reference"]["path"])
            publication_path = Path(result["publication_reference"]["path"])
            start_path = history_path.parent / "started.json"
            original = {path: path.read_bytes() for path in history_path.parent.iterdir()}
            document = reader.decode(original[history_path])
            def replace_digest(value, before, after):
                if isinstance(value, dict):
                    return {key: replace_digest(item, before, after) for key, item in value.items()}
                if isinstance(value, list):
                    return [replace_digest(item, before, after) for item in value]
                return after if value == before else value
            for attack in ("evidence_lf", "prefix_newline", "wrapper_whitespace", "start_whitespace"):
                with self.subTest(attack=attack):
                    for path, raw in original.items(): path.write_bytes(raw)
                    value = deepcopy(document)
                    publication = reader.decode(original[publication_path])
                    if attack in ("evidence_lf", "prefix_newline"):
                        role = "accounted_prefix_evidence_references" if attack == "evidence_lf" else "accounted_prefix_references"
                        target = Path(value["history"][role]["QQQ"]["path"])
                        changed = original[target].rstrip(b"\n") if attack == "evidence_lf" else original[target].replace(b"\n", b"\r\n")
                        self.assertNotEqual(changed, original[target])
                        target.write_bytes(changed)
                        old, new = reader.digest(original[target]), reader.digest(changed)
                        value = replace_digest(value, old, new)
                        publication = replace_digest(publication, old, new)
                        reader.consume(reader.reference(str(target), new), {})
                    elif attack == "start_whitespace":
                        changed = original[start_path] + b"\n"
                        start_path.write_bytes(changed)
                        old, new = reader.digest(original[start_path]), reader.digest(changed)
                        value = replace_digest(value, old, new)
                        publication = replace_digest(publication, old, new)
                    raw = reader.encode(value) + (b"\n" if attack == "wrapper_whitespace" else b"")
                    history_path.write_bytes(raw)
                    references = deepcopy(result)
                    references["history_reference"] = reader.reference(str(history_path), reader.digest(raw))
                    publication["history_reference"] = references["history_reference"]
                    publication_path.write_bytes(reader.encode(publication))
                    references["publication_reference"] = reader.reference(str(publication_path), reader.digest(publication_path.read_bytes()))
                    output_name = "rejected_" + attack
                    with self.assertRaises(ValueError):
                        fixtures.read_context(context, references, output_name)
                    self.assertFalse((context[0] / output_name).exists())


if __name__ == "__main__": unittest.main()
