"""Root independent economic-row and row-location forgery review."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts import ndx_registered_observation_independent_readback_20261009_v2 as reader
from test_ndx_registered_observation_independent_readback_20261009_v2 import saved_context, read_context


class CoordinatedObservationForgeryReview(unittest.TestCase):
    def test_resigned_selected_price_and_source_row_location_cannot_be_promoted(self):
        for attack in ("selected_price", "row_location"):
            with self.subTest(attack=attack), TemporaryDirectory(prefix="SYNTHETIC_ROOT_V5_OBSERVER_FORGERY_") as directory:
                context, payload_ref, receipt_ref = saved_context(Path(directory))
                payload_path = Path(payload_ref["path"]); receipt_path = Path(receipt_ref["path"])
                payload = reader.decode(payload_path.read_bytes()); receipt = reader.decode(receipt_path.read_bytes())
                if attack == "selected_price":
                    payload["selected_original_rows"]["QQQ"]["Close"] = "999999"
                else:
                    payload["source_row_locations"]["QQQ"]["original_data_row_index"] += 1
                payload_path.write_bytes(reader.enc(payload))
                forged_payload = dict(path=str(payload_path), sha256=reader.sha(payload_path.read_bytes()))
                receipt["payload_reference"] = forged_payload
                receipt_path.write_bytes(reader.enc(receipt))
                forged_receipt = dict(path=str(receipt_path), sha256=reader.sha(receipt_path.read_bytes()))
                with self.assertRaises(ValueError): read_context(context, forged_payload, forged_receipt)
                output = payload_path.parent
                self.assertTrue((output / "failure.json").is_file())
                self.assertFalse((output / "independent_readback.json").exists())
                failure = reader.decode((output / "failure.json").read_bytes())
                self.assertEqual(failure["status"], "INDEPENDENT_READBACK_FAILED_NO_RETRY")
                self.assertTrue(failure["partial_evidence_preserved"])
                self.assertTrue(payload_path.exists() and receipt_path.exists())
                with self.assertRaises(ValueError): read_context(context, forged_payload, forged_receipt)


if __name__ == "__main__": unittest.main()
