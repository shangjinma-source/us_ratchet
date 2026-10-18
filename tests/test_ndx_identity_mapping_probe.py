import hashlib
import json
import unittest

from backtest.ndx_identity_mapping_probe import (
    IdentityMappingProbeError, build_mapping_jobs, build_mapping_observation, verify_mapping_observation,
)

SOURCE = b"security_id,issuer_id,ticker,cik,cusip,observation_from,observation_to\nS,I,TEST,0000000001,123456789,2020-01-01,2026-03-31\n"


class IdentityMappingProbeTest(unittest.TestCase):
    def observe(self, result):
        raw = json.dumps([result]).encode()
        return build_mapping_observation(identity_csv_bytes=SOURCE, tickers=["TEST"],
                                         response_bytes=raw, observed_at_utc="2026-09-05T21:00:00Z", http_status=200)

    def match(self):
        return {"ticker": "TEST", "figi": "F", "compositeFIGI": "C", "shareClassFIGI": "S",
                "exchCode": "US", "marketSector": "Equity"}

    def test_observed_match_is_never_execution_or_historical_authority(self):
        result = self.observe({"data": [self.match()]})
        self.assertEqual(result["matched_count"], 1)
        self.assertFalse(result["execution_valid_on_date_proved"])
        self.assertFalse(result["historical_asof_mapping_claimed"])
        self.assertFalse(result["admission_authority"])
        self.assertEqual(result["historical_identity_source_sha256"], hashlib.sha256(SOURCE).hexdigest())
        self.assertEqual(result["response_bytes_sha256"], hashlib.sha256(result["response_body_utf8"].encode()).hexdigest())

    def test_ambiguous_missing_warning_and_renamed_tickers_do_not_match(self):
        for response in ({"data": [self.match(), self.match()]}, {"warning": "No match"},
                         {"data": []}, {"data": [{**self.match(), "ticker": "RENAMED"}]},
                         {"data": [{**self.match(), "exchCode": "XX"}]}):
            with self.subTest(response=response):
                self.assertEqual(self.observe(response)["matched_count"], 0)

    def test_transport_identity_and_response_cardinality_are_strict(self):
        for names in ([], ["TEST", "TEST"], ["MISSING"]):
            with self.assertRaises(IdentityMappingProbeError):
                build_mapping_jobs(SOURCE, names)
        with self.assertRaises(IdentityMappingProbeError):
            build_mapping_observation(identity_csv_bytes=SOURCE, tickers=["TEST"], response_bytes=b"[]",
                                      observed_at_utc="2026-09-05T21:00:00Z", http_status=200)

    def test_duplicate_json_keys_are_rejected_at_all_levels(self):
        for raw in (b'[{"data":[],"data":[]}]', b'[{"data":[{"ticker":"A","ticker":"B"}]}]'):
            with self.assertRaisesRegex(IdentityMappingProbeError, "duplicate JSON key"):
                build_mapping_observation(identity_csv_bytes=SOURCE, tickers=["TEST"], response_bytes=raw,
                                          observed_at_utc="2026-09-05T21:00:00Z", http_status=200)

    def test_cross_job_provider_identity_collision_invalidates_all_related_rows(self):
        source = SOURCE + b"S2,I2,OTHER,0000000002,987654321,2020-01-01,2026-03-31\n"
        for field in ("figi", "compositeFIGI", "shareClassFIGI"):
            first = self.match()
            second = {**self.match(), "ticker": "OTHER", "figi": "F2", "compositeFIGI": "C2", "shareClassFIGI": "S2"}
            second[field] = first[field]
            with self.subTest(field=field):
                result = build_mapping_observation(
                    identity_csv_bytes=source, tickers=["TEST", "OTHER"],
                    response_bytes=json.dumps([{"data": [first]}, {"data": [second]}]).encode(),
                    observed_at_utc="2026-09-05T21:00:00Z", http_status=200,
                )
                self.assertEqual(result["matched_count"], 0)
                self.assertTrue(all(row["status"] == "UNRESOLVED_CROSS_JOB_PROVIDER_IDENTITY_COLLISION"
                                    for row in result["results"]))

    def test_saved_observation_rebuild_rejects_result_and_source_tampering(self):
        result = self.observe({"data": [self.match()]})
        raw = json.dumps(result).encode()
        self.assertEqual(verify_mapping_observation(raw, identity_csv_bytes=SOURCE), result)
        result["admission_authority"] = True
        with self.assertRaises(IdentityMappingProbeError):
            verify_mapping_observation(json.dumps(result).encode(), identity_csv_bytes=SOURCE)
        with self.assertRaises(IdentityMappingProbeError):
            verify_mapping_observation(raw, identity_csv_bytes=SOURCE.replace(b"2020-01-01", b"2021-01-01"))


if __name__ == "__main__":
    unittest.main()
