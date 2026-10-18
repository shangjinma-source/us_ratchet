import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_single_replacement_shard_worker_20261003 as worker
from test_ndx_single_replacement_shard_worker_20261003 import context


class RootJournalReview(unittest.TestCase):
    def test_resigned_start_must_match_original_full_task(self):
        supplied = context()
        descriptor = supplied['plan']['document']['shards'][0]
        with tempfile.TemporaryDirectory() as folder, patch.object(worker, 'resource'):
            path = Path(folder) / 'shard'
            result = json.loads(worker.read(worker.process_shard(supplied, descriptor, path)))
            entries = [json.loads(line) for line in (path / 'journal.jsonl').read_bytes().splitlines()]
            entries[0]['body']['payload']['task']['proposed_holdings']['ZERO'] = 999
            previous = '0' * 64
            records = []
            for record in entries:
                body = record['body']
                body['previous_sha256'] = previous
                updated = supplied['journal'].make_record(**{key: value for key, value in body.items() if key != 'schema'})
                previous = updated['record_sha256']
                records.append(supplied['journal'].encode(updated) + b'\n')
            tasks = [supplied['evaluator'].project_validated_task(supplied['validated'], index) for index in range(2)]
            with self.assertRaises(ValueError):
                supplied['journal'].inspect_journal(b''.join(records), context_sha256=result['context_sha256'], ordered_tasks=tasks)


if __name__ == '__main__':
    unittest.main()
