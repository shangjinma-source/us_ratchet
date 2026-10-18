"""Leading-zero CUSIPs remain the same identities through the full search chain."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import pandas as pd
import fixture_fresh_search_v4_e2e as fixture
from scripts import ndx_dynamic_shadow_fresh_search_v4 as acceptance


class LeadingZeroIdentityE2ETests(unittest.TestCase):
    def test_leading_zero_identity_is_not_excluded_or_renumbered(self):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve()
            path, watched = fixture.prepare(root, leading_zero_cusips=True)
            calls = []
            fixture.bindings(stack, root, calls)
            result = acceptance.execute(path)
            self.assertTrue(result["v4_verified"])
            self.assertEqual(len(calls), 8)
            eligible = pd.read_csv(path.parent / "eligible_securities.csv", dtype=str, keep_default_na=False)
            for index, ticker in enumerate(("O000", "O001", "O002")):
                identities = eligible.loc[eligible.ticker.eq(ticker), "security_id"]
                self.assertEqual(len(identities), 2)
                self.assertTrue(identities.eq(f"security:{index + 101:010d}:{index + 2:09d}").all())
            for source, digest in watched.items():
                self.assertEqual(acceptance.digest(source), digest)
