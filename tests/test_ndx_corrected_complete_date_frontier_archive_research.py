from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_corrected_complete_date_frontier_archive_research as m


class Tests(unittest.TestCase):
    def test_full_diff_archive_schema_coordinate_denominator_and_scope(self):
        path=str(Path('complete.json').resolve());parent=dict(original_count=10,pending_count=3,available_count=7)
        complete=dict(input_artifact_binding_verified=True,source_resolution_schema=m.reader.RESOLUTION_SCHEMA)
        report=dict(schema=m.independent_diff.SCHEMA,date='2023-04-03',output_path=path,output_sha256='h',
            historical_expected_source_hashes=dict(m.independent_diff.LOADED,**{path:'h'}),
            original_count=10,selected_replaced=3,unrelated_records_exact=7,
            whole_date_task_map_verified=True,ordered_full_record_diff_verified=True,full_new_results_match_external_checkpoints=True,output_source_partitions_reverified=True,
            **dict.fromkeys(m.independent_diff.FLAGS,False))
        args=dict(date='2023-04-03',complete_path=path,complete_sha256='h',parent=parent,complete=complete)
        m.validate_diff(report,**args)
        for key,value in [('schema','SELECTED_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1'),('selected_replaced',True),('date','2023-05-01'),('merger_called',True)]:
            changed=deepcopy(report);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_diff(changed,**args)

    def test_archive_and_loader_gap_rechecked_without_old_live_verifier(self):
        partition=dict(archive_resolutions=[{}]*85,historical_gap_observations=[{}]*26)
        report=dict(schema='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1',source_resolution_schema=m.reader.RESOLUTION_SCHEMA,
            historical_expected_source_hashes=dict(m.LOADED),archive_resolution=partition,historical_loader_gap_observations=['gap'],**dict.fromkeys(m.FLAGS,False))
        with patch.object(m.archive,'load_contract',return_value={}),patch.object(m.archive,'verify_expected_sources',return_value=partition),patch.object(m.reader.independent,'verify_gaps') as gaps:
            m.verify(report);gaps.assert_called_once_with(['gap'])
            gaps.side_effect=ValueError('YAML observation changed')
            with self.assertRaises(ValueError):m.verify(report)
        bad=deepcopy(report);bad['verified_source_hashes']={}
        with self.assertRaises(ValueError):m.verify(bad)

    def test_source_and_scope_cannot_be_upgraded(self):
        for key in m.FLAGS:
            report=dict(schema='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1',source_resolution_schema=m.reader.RESOLUTION_SCHEMA,**dict.fromkeys(m.FLAGS,False));report[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):m.verify(report)


if __name__=='__main__':unittest.main()
