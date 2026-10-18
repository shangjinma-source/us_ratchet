import unittest
from backtest import ndx_double_stream_resource_v3_research as resource


class Tests(unittest.TestCase):
    def test_constructor_does_not_execute_body(self):
        source="def forbidden():\n raise AssertionError('point execution')\n return dict(schema='X',count=amount,flag=False)\n"
        self.assertEqual(resource.constructor(source,'X',{'amount':17}),dict(schema='X',count=17,flag=False))
        with self.assertRaises(ValueError):resource.constructor(source,'MISSING',{})

    def test_ambiguous_constructor_requires_explicit_scope(self):
        source="def first():\n return dict(schema='X',value=1)\ndef second():\n return dict(schema='X',value=2)\n"
        with self.assertRaises(ValueError):resource.constructor(source,'X',{})
        self.assertEqual(resource.constructor(source,'X',{'__function__':'second'})['value'],2)

    def test_symbolic_runs_cover_all_numeric_singletons(self):
        total=52406569;limit=resource.normal_run_bound(total)
        self.assertEqual(limit,67)
        for n in (0,9,999,9999999,total-1):
            for kind in ('inspected_feasible','inspected_infeasible'):
                self.assertLessEqual(len(resource.encode(dict(start=n,stop=n+1,status=kind)))+1,limit)

    def test_files_cluster_rounding_and_tail(self):
        report=resource.totals(count=513,batch_size=512,gzip_total=100,gzip_batch=60,raw_batch=80,file_lengths={'result.json':2},manifest_line=4,audit_line=8,request_lengths={'result':10})
        self.assertEqual(report['batch_count'],2)
        self.assertEqual(report['normal_file_count'],21)
        self.assertEqual(report['normal_logical_bytes_upper'],100+513*resource.normal_run_bound(513)+2*(2+4+8)+10)
        self.assertEqual(resource.allocation_bytes(4097,4096),8192)
        self.assertIsNone(report['process_rss_upper'])
        self.assertIsNone(report['ntfs_internal_metadata_upper'])
        self.assertFalse(report['execution_authorized'])
        with self.assertRaises(AssertionError):resource.totals(count=True,batch_size=512,gzip_total=1,gzip_batch=1,raw_batch=1,file_lengths={},manifest_line=1,audit_line=1,request_lengths={})

    def test_payload_model_charges_shared_tree_twice(self):
        child={'values':[1,2,'text']}
        self.assertGreater(resource.retained_tree_bytes([child,child]),2*resource.retained_tree_bytes(child))
        with self.assertRaises(TypeError):resource.retained_tree_bytes(object())


if __name__=='__main__':unittest.main()
