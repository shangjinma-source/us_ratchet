"""Independent synthetic-only TSM review; no original build or owner test run."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_tsm_incumbent_identity_20261002 as fixture_module
m=fixture_module.module

class IndependentReview(unittest.TestCase):
    def test_underlying_share_or_detached_cusip_resigned_rejected(self):
        for replacement in ('common shares have been listed on the New York Stock Exchange', 'ADSs have been listed on the Taiwan Stock Exchange'):
            raw,manifest,filing,receipt=fixture_module.fixture()
            raw=raw.replace(b'ADSs have been listed on the New York Stock Exchange',replacement.encode())
            fixture_module.resign(raw,manifest,filing)
            with self.assertRaises(ValueError):m.extract(raw,manifest,filing,receipt)
        raw,manifest,filing,receipt=fixture_module.fixture()
        raw=raw.replace(m.CUSIP_SENTENCE.encode(),b'')+m.CUSIP_SENTENCE.encode()
        fixture_module.resign(raw,manifest,filing)
        with self.assertRaises(ValueError):m.extract(raw,manifest,filing,receipt)

    def test_archive_cik_and_late_dates_are_not_inline_or_continuity(self):
        args=fixture_module.fixture(); before=deepcopy(args); result=m.extract(*args)
        self.assertEqual(args,before)
        self.assertEqual(result['security_id'],'security:incumbent_overlay:TSM')
        self.assertEqual(result['security_class'],'American Depositary Shares')
        self.assertEqual(result['issuer_cik_binding_kind'],'SAVED_MANIFEST_AND_SEC_ARCHIVE_PATH_NOT_INLINE_FIELD')
        for field in m.FALSE_FLAGS:self.assertIs(result[field],False)
        self.assertNotIn('holdings',result)
        self.assertNotIn('converted_shares',result)
        self.assertEqual(result['original_manifest'],before[1])
        for key in ('source_locator','fetched_at','cik'):
            value=list(deepcopy(args));del value[1][key]
            with self.subTest(key=key),self.assertRaises((ValueError,KeyError)):m.extract(*value)

    def test_raw_hash_and_hard_build_pin_precede_extraction(self):
        args=list(fixture_module.fixture());args[0]+=b' '
        with self.assertRaisesRegex(ValueError,'hash'):m.extract(*args)
        raw,manifest,filing,receipt=fixture_module.fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); f=root/'source'; f.write_bytes(raw); p=root/'manifest';p.write_bytes(m.encoded(manifest))
            with patch.object(m,'FILING',f),patch.object(m,'MANIFEST',p),patch.object(m,'extract') as extract:
                with self.assertRaisesRegex(ValueError,'Hard input SHA'):m.build()
                extract.assert_not_called()

    def test_existing_namespace_and_post_receipt_orphan_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); output=root/'out';output.mkdir()
            with patch.object(m,'OUTPUT',output),patch.object(m,'build') as build:
                with self.assertRaises(ValueError):m.publish()
                build.assert_not_called()
            output=root/'new'; source=root/'source';source.write_text('sealed')
            result={'source_hashes':{str(source):m.digest(source.read_bytes())}}
            original=m.durable
            def orphan(path,raw):
                original(path,raw)
                if path.name=='publication.json':(output/'unrelated.bin').write_bytes(b'orphan')
            with patch.object(m,'OUTPUT',output),patch.object(m,'build',return_value=result),patch.object(m,'durable',side_effect=orphan):
                with self.assertRaisesRegex(ValueError,'orphan'):m.publish()
                self.assertTrue((output/'failure.json').exists())
                with self.assertRaises(ValueError):m.publish()

if __name__=='__main__':unittest.main()
