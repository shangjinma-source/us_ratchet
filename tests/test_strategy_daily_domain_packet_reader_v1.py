from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_daily_dynamic_factory_v1 import run_dynamic_sources, FACTORY_SOURCES
from data.strategy_daily_domain_packet_reader_v1 import DomainSessionDailyPacketReaderV1
import test_strategy_daily_domain_runner_v1 as fixtures


class DomainReaderTests(unittest.TestCase):
    def test_previous_session_continuity_is_read_and_missing_parent_rejects(self):
        import test_strategy_daily_dynamic_factory_v1 as dynamic
        from datetime import datetime
        with TemporaryDirectory() as folder:
            account, root, run, calls = dynamic.DynamicFactoryTests().setup(folder)
            self.assertEqual(run()["status"], "DYNAMIC_DOMAIN_PACKET_SAVED")
            account.clock[0] = datetime.fromisoformat("2026-11-03T15:00:00+00:00")
            self.assertEqual(run()["status"], "DYNAMIC_DOMAIN_PACKET_SAVED")
            config_path = "dynamic-runs/2026-11-03/configuration.json"
            raw = (root/config_path).read_bytes()
            reader = DomainSessionDailyPacketReaderV1(
                root=root, configuration_path=config_path,
                configuration_sha256=sha256(raw).hexdigest(), archive_root=root/"rebound")
            self.assertEqual(reader(account.store.read(), account.target, account.clock[0])["status"],
                             "WAIT_POLICY_RELEASE")
            path = root/"dynamic-runs/2026-11-02/terminal.json"
            path.rename(path.with_suffix(".saved"))
            with self.assertRaises((ValueError, OSError)):
                reader(account.store.read(), account.target, account.clock[0])
            self.assertEqual(len(calls), 2)

    def case(self, folder):
        account, unused, root = fixtures.DomainRunnerTests().setup(folder, multiple=True)
        pins = []
        for name in FACTORY_SOURCES:
            raw = (fixtures.fixtures.ROOT/name).read_bytes()
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            pins.append(dict(path=name, sha256=sha256(raw).hexdigest()))
        calendar_raw = (root/"calendar.json").read_bytes()
        config = dict(schema="SERVER_DYNAMIC_DAILY_SOURCE_V1", source_pins=pins,
            calendar=dict(path="calendar.json", sha256=sha256(calendar_raw).hexdigest()),
            identity=account.identity_reference, runs_root="dynamic-runs",
            first_execution_date="2026-11-02", target_evidence_root="capture",
            account_id=account.state["account_id"])
        raw = canonical(config)
        (root/"reader-config.json").write_bytes(raw)
        dates = json.loads(calendar_raw)["sessions"]
        window = dates[-21:-1]
        from datetime import datetime
        def fetch(ticker, *args):
            return dict(status=200, body=canonical(dict(chart=dict(error=None, result=[
                dict(meta=dict(symbol=ticker, currency="USD", instrumentType="EQUITY",
                               exchangeName="NMS"), events={},
                     timestamp=[int(datetime.fromisoformat(s["open"]).timestamp()) for s in window],
                     indicators=dict(quote=[dict(close=[100]*20)],
                                     adjclose=[dict(adjclose=[100]*20)]))]))))
        before = account.store.path.read_bytes()
        result = run_dynamic_sources(
            root=root, configuration_bytes=raw, configuration_sha256=sha256(raw).hexdigest(),
            account_reader=account.store.read, target_reader=lambda: account.target,
            execute=True, clock=lambda: account.clock[0], fetch_daily=fetch,
            fetch_official=lambda: dict(status=200, body=b"<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>"))
        self.assertEqual(result["status"], "DYNAMIC_DOMAIN_PACKET_SAVED", result)
        reader = DomainSessionDailyPacketReaderV1(
            root=root, configuration_path="reader-config.json",
            configuration_sha256=sha256(raw).hexdigest(), archive_root=root/"rebound")
        return account, root, reader, before

    def test_held_exit_security_survives_current_account_reaggregation(self):
        with TemporaryDirectory() as folder:
            account, root, reader, before = self.case(folder)
            result = reader(account.store.read(), account.target, account.clock[0])
            self.assertEqual(result["status"], "WAIT_POLICY_RELEASE", result)
            self.assertEqual(result["reviewed_securities"], ["A", "B"])
            self.assertEqual(account.store.path.read_bytes(), before)
            self.assertFalse((root/"rebound").exists())

    def test_missing_terminal_waits_and_future_publication_rejects(self):
        with TemporaryDirectory() as folder:
            account, root, reader, before = self.case(folder)
            path = root/"dynamic-runs/2026-11-02/terminal.json"
            raw = path.read_bytes()
            path.rename(path.with_suffix(".saved"))
            self.assertEqual(reader(account.store.read(), account.target, account.clock[0])["reason"],
                             "INCOMPLETE_DAILY_PACKET")
            terminal = json.loads(raw)
            terminal["finished_at"] = "2099-01-01T00:00:00Z"
            path.write_bytes(canonical(terminal))
            with self.assertRaisesRegex(ValueError, "DOMAIN_READER_PUBLICATION_TIME"):
                reader(account.store.read(), account.target, account.clock[0])
            self.assertEqual(account.store.path.read_bytes(), before)

    def test_tampered_individual_packet_rejects_before_policy_wait(self):
        with TemporaryDirectory() as folder:
            account, root, reader, before = self.case(folder)
            terminal = json.loads((root/"dynamic-runs/2026-11-02/terminal.json").read_bytes())
            path = root/terminal["packets"]["A"]["receipt_reference"]["path"]
            path.write_bytes(b"{}")
            with self.assertRaises(ValueError):
                reader(account.store.read(), account.target, account.clock[0])
            self.assertEqual(account.store.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
