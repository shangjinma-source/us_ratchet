"""Synthetic byte-level partition tests; no actual source or evaluator run."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import ndx_cash_neighbor_interrupted_partition_20261008 as subject
from backtest import ndx_cash_topup_neighbor_journal_research as journal


class IndependentPartitionReview(unittest.TestCase):
    ids = ['1'*64, '2'*64, '3'*64]
    context = 'a'*64

    def journal_bytes(self, stages):
        previous = journal.ZERO
        lines = []
        for index, (position, stage, payload) in enumerate(stages):
            row = journal.make_record(sequence=index, previous_hash=previous,
                context_sha256=self.context, task_id=self.ids[position],
                task_position=position, stage=stage, payload=payload)
            previous = row['record_sha256']
            lines.append(journal.encode(row)+b'\n')
        return b''.join(lines)

    def classify_bytes(self, raw):
        scan = journal.inspect_journal(raw, context_sha256=self.context, ordered_task_ids=self.ids)
        return subject.classify(self.ids, scan)

    def test_both_raw_stages_preserved_without_postcheck(self):
        for raw_stage in ('RAW_RETURNED', 'RAW_EXCEPTION'):
            raw = self.journal_bytes([(0, 'EXTERNAL_REFERENCE', {}),
                (1, 'TASK_STARTED', {}), (1, raw_stage, {'opaque': 'no economic interpretation'})])
            with self.subTest(raw_stage=raw_stage):
                groups = self.classify_bytes(raw)
                self.assertEqual(groups['EXTERNALLY_REFERENCED'], self.ids[:1])
                self.assertEqual(groups['RAW_SAVED_POSTCHECK_MISSING'], self.ids[1:2])
                self.assertEqual(groups['UNDISPATCHED'], self.ids[2:])
                self.assertFalse(groups['INFEASIBLE'])
                self.assertFalse(groups['FEASIBLE'])

    def test_partial_raw_never_reclassified_as_undispatched(self):
        raw = self.journal_bytes([(0, 'TASK_STARTED', {}), (0, 'RAW_RETURNED', {})])
        with self.assertRaisesRegex(ValueError, 'Partial bytes'):
            self.classify_bytes(raw[:-1])
        with self.assertRaises(ValueError):
            self.classify_bytes(raw.replace(b'RAW_RETURNED', b'RAW_EXCEPTION'))

    def test_saved_failure_does_not_become_economic_infeasibility(self):
        for outcome in ('EVALUATION_EXCEPTION', 'VALIDATION_FAILURE'):
            raw = self.journal_bytes([(0, 'TASK_STARTED', {}), (0, 'RAW_EXCEPTION', {}),
                (0, 'POSTCHECK', {'outcome': outcome})])
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                self.classify_bytes(raw)

    def test_prior_completion_cannot_be_rehashed_away_from_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory)/'batch'; batch.mkdir()
            worker = Path(directory)/'worker.py'; worker.write_text('FLAGS={}\n')
            journal_source = Path(directory)/'journal.py'; journal_source.write_text('# synthetic\n')
            def save(relative, value):
                path = batch/relative; path.parent.mkdir(parents=True, exist_ok=True)
                raw = subject.encode(value); path.write_bytes(raw)
                return dict(path=str(path), sha256=subject.digest(raw))
            context = {'source_hashes': {}}
            context_sha = subject.digest(subject.encode(context))
            started = save('started.json', {'context': context, 'context_sha256': context_sha})
            prior_start = save('request-dc2686d5a18447f5837e70f5936731ee/started.json',
                dict(context_sha256=context_sha, full_shard_count=324, full_task_count=301657))
            completion = save('scenario-00-shard-00000/completion.json', {'saved': 'original'})
            prior = save('request-dc2686d5a18447f5837e70f5936731ee/result.json',
                dict(context_sha256=context_sha, batch_started_reference=started,
                    request_started_reference=prior_start, completed_shard_references=[completion]))
            # Rewrite the local completion self-consistently, but leave its old
            # external request anchor untouched. Must fail before any economics.
            Path(completion['path']).write_bytes(subject.encode({'saved': 'rewritten'}))
            with patch.multiple(subject, BATCH=batch, WORKER=worker,
                    WORKER_SHA=subject.digest(worker.read_bytes()), JOURNAL=journal_source,
                    JOURNAL_SHA=subject.digest(journal_source.read_bytes()),
                    ANCHORS={'started.json': started['sha256'],
                        'request-dc2686d5a18447f5837e70f5936731ee/result.json': prior['sha256']}):
                with self.assertRaisesRegex(ValueError, 'Source drift: .*completion.json'):
                    subject.inspect()

    def test_create_only_publish_and_failed_inspection_preserve_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'snapshot'
            with patch.object(subject, 'OUTPUT', output):
                with patch.object(subject, 'inspect', side_effect=ValueError('source drift')):
                    with self.assertRaisesRegex(ValueError, 'source drift'):
                        subject.publish(execute=True)
                    self.assertFalse(output.exists())
                with patch.object(subject, 'inspect', return_value={'scope': 'SYNTHETIC_ONLY', **subject.FLAGS}):
                    reference = subject.publish(execute=True)
                saved = Path(reference['path']).read_bytes()
                self.assertEqual(subject.digest(saved), reference['sha256'])
                with patch.object(subject, 'inspect', side_effect=AssertionError('must not inspect')):
                    with self.assertRaisesRegex(ValueError, 'Create-only'):
                        subject.publish(execute=True)
                self.assertEqual(Path(reference['path']).read_bytes(), saved)


if __name__ == '__main__':
    unittest.main()
