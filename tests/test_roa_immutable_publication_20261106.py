import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.research.publish_roa_immutable_inputs import publish,verify


class PublicationTests(unittest.TestCase):
    def test_source_cache_refresh_does_not_change_published_version(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'data/cache/facts.json';source.parent.mkdir(parents=True)
            source.write_text('{"value":1}')
            entry=root/'signal.json';entry.write_text(json.dumps({'source_hashes':{'data/cache/facts.json':sha256(source.read_bytes()).hexdigest()}}))
            pins={'signal.json':sha256(entry.read_bytes()).hexdigest()}
            output=publish(root=root,entrypoints=pins,destination=root/'bundle')
            self.assertEqual(output['file_count'],2)
            source.write_text('{"value":2}')
            self.assertEqual(verify(root/'bundle')['file_count'],2)
            with self.assertRaisesRegex(ValueError,'PUBLICATION_SOURCE_CHANGED'):
                publish(root=root,entrypoints=pins,destination=root/'another')
            (root/'bundle/inputs/data/cache/facts.json').write_text('tamper')
            with self.assertRaisesRegex(ValueError,'PUBLICATION_INPUT_CHANGED'):verify(root/'bundle')

    def test_no_overwrite_and_path_escape(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'one.json';source.write_text('{}')
            args=dict(root=root,entrypoints={'one.json':sha256(source.read_bytes()).hexdigest()},destination=root/'bundle')
            publish(**args)
            with self.assertRaisesRegex(ValueError,'PUBLICATION_DESTINATION_EXISTS'):publish(**args)
            with self.assertRaisesRegex(ValueError,'PUBLICATION_SOURCE_PATH_INVALID'):
                publish(**dict(args,entrypoints={'../outside':'0'*64}),dry_run=True)


if __name__=='__main__':unittest.main()
