"""Original-position domain and journal counterexamples, no economic execution."""
from copy import deepcopy
import unittest
from backtest import ndx_cash_neighbor_recovery_partition_research as subject
from test_ndx_cash_neighbor_recovery_partition_research import fixture


class IndependentRecoveryReview(unittest.TestCase):
    def segment(self):
        return dict(original_task_start=163,original_task_stop=165,task_ids=['a'*64,'b'*64],
            original_descriptor=dict(global_task_start=259193,global_task_stop=259358,shard=dict(start=46000,stop=46165)))

    def make(self, segment=None, **overrides):
        values=dict(sequence=0,previous_hash='0'*64,registration_sha256='c'*64,
            segment=segment or self.segment(),task_position=163,stage='TASK_STARTED',payload={})
        values.update(overrides)
        return subject.make_record(**values)

    def test_shard_ordinal_bool_float_and_negative_rejected(self):
        original=fixture()
        for value in (False,0.0,-1):
            data=deepcopy(original)
            size=data[0][0]['shard']['stop']
            data[0][0]['shard'].update(start=value,stop=size+value)
            with self.subTest(value=value),self.assertRaises(ValueError):
                subject.build_recovery_segments(*data)

    def test_record_hash_refs_have_explicit_sha_shape(self):
        for key in ('previous_hash','registration_sha256'):
            for value in ('', 'z'*64, 'a'*63, True):
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    self.make(**{key:value})

    def test_segment_metadata_requires_exact_original_integer_positions(self):
        for attack in ('global_bool','ordinal_float','negative_start','length','duplicate'):
            segment=self.segment()
            if attack=='global_bool':segment['original_descriptor']['global_task_start']=True
            elif attack=='ordinal_float':segment['original_descriptor']['shard']['start']=46000.0
            elif attack=='negative_start':segment['original_task_start']=-1
            elif attack=='length':segment['task_ids'].append('d'*64)
            else:segment['task_ids'][1]=segment['task_ids'][0]
            with self.subTest(attack=attack),self.assertRaises(ValueError):
                self.make(segment)

    def test_wrong_registration_rejected_and_empty_prefix_is_undispatched(self):
        segment=self.segment(); record=self.make(segment)
        raw=subject.encode(record)+b'\n'
        with self.assertRaises(ValueError):
            subject.inspect_recovery_journal(raw,segment=segment,registration_sha256='d'*64)
        result=subject.inspect_recovery_journal(b'',segment=segment,registration_sha256='c'*64)
        self.assertIsNone(result['active'])
        self.assertEqual(result['undispatched_task_ids'],segment['task_ids'])
        self.assertFalse(result['complete'])


if __name__=='__main__':unittest.main()
