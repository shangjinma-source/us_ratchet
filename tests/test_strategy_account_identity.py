import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.strategy_account_identity import PinnedStrategyIdentity


class IdentityTests(unittest.TestCase):
    def test_pins_rechecked_and_unknown_rejected(self):
        with TemporaryDirectory() as directory:
            root=Path(directory); reference=root/'reference.json';reference.write_bytes(b'{}')
            manifest=dict(candidates=[dict(ticker='SNDK',security_id='SID',status='READY_CONDITIONAL',
                identity_reviewed=True,identity_source_references=['reference.json'])],
                source_hashes={'reference.json':sha256(reference.read_bytes()).hexdigest()})
            raw=json.dumps(manifest).encode();(root/'manifest.json').write_bytes(raw)
            resolver=PinnedStrategyIdentity(root,'manifest.json',sha256(raw).hexdigest())
            self.assertEqual(resolver('SNDK')['security_id'],'SID')
            with self.assertRaisesRegex(ValueError,'IDENTITY_NOT_UNIQUE_OR_UNAVAILABLE'):
                resolver('UNKNOWN')
            reference.write_bytes(b'{"changed":true}')
            with self.assertRaisesRegex(ValueError,'IDENTITY_SOURCE_CHANGED'):
                resolver('SNDK')
            (root/'manifest.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'IDENTITY_SOURCE_CHANGED'):
                resolver('SNDK')

    def test_no_path_or_symbol_guessing(self):
        resolver=PinnedStrategyIdentity('.', '../outside.json','0'*64)
        with self.assertRaisesRegex(ValueError,'IDENTITY_SOURCE_PATH_INVALID'):
            resolver('SNDK')
        with self.assertRaisesRegex(ValueError,'INVALID_TICKER'):
            resolver('SNDK/../../secret')


if __name__=='__main__':unittest.main()
