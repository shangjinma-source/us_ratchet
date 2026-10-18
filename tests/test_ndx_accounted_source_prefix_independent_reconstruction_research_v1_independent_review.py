"""Independent prefix attacks; no runtime, capture, observations or actual IO."""
import ast
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from backtest import ndx_accounted_source_prefix_independent_reconstruction_research_v1 as module
from backtest import ndx_accounted_source_prefix_research_v1 as producer
from test_ndx_accounted_source_prefix_independent_reconstruction_research_v1 import HEADER,DAYS,arguments


class IndependentPrefixAdversarialTests(unittest.TestCase):
    def test_exact_physical_limit_counts_crlf_once_and_keeps_blank_bytes(self):
        base=HEADER+b'\r\n2026-10-05,10,12,8,10,100\r\n'
        raw=base+b'\r\n'*99998
        args=arguments(raw,DAYS[:1]);self.assertEqual(module.reconstruct_accounted_prefix(**args),producer.derive_accounted_prefix(**args))
        self.assertEqual(module.reconstruct_accounted_prefix(**args)[0],raw)
        with self.assertRaises(ValueError):module.reconstruct_accounted_prefix(**arguments(raw+b'\r\n',DAYS[:1]))

    def test_data_limit_is_independent_of_physical_count(self):
        day=date(1900,1,1);sessions=[]
        while len(sessions)<20001:
            if day.weekday()<5:sessions.append(day.isoformat())
            day+=timedelta(days=1)
        raw=HEADER+b'\n'+b''.join((s+',10,12,8,10,100\n').encode()for s in sessions[:20000])
        args=arguments(raw,sessions[:1]);args['scope_start']=sessions[0];prefix,evidence=module.reconstruct_accounted_prefix(**args)
        self.assertEqual(evidence['original_row_count'],20000);self.assertEqual(evidence['suffix_original_row_indexes'][-1],19999)
        self.assertEqual((prefix,evidence),producer.derive_accounted_prefix(**args))
        bad=deepcopy(args);bad['source_bytes']=raw+(sessions[-1]+',10,12,8,10,100\n').encode();bad['source_reference']['sha256']=module.sha256(bad['source_bytes']).hexdigest()
        with self.assertRaises(ValueError):module.reconstruct_accounted_prefix(**bad)

    def test_unicode_decimal_and_quoted_numeric_grammar_agrees_without_reserialization(self):
        for numeric in ('\uff11\uff10','\u0661\u0660','1_0','+1e+1','1e-50','9'*50):
            raw=b'\xef\xbb\xbf'+HEADER+b'\r'+''.join(s+','+','.join('"'+numeric+'"'for _ in range(4))+',"0"\r\n'for s in DAYS).encode()
            args=arguments(raw);self.assertEqual(module.reconstruct_accounted_prefix(**args),producer.derive_accounted_prefix(**args))
        for numeric in ('0','-0','NaN','Infinity','1e51','1e-51','9'*51):
            raw=HEADER+b'\n'+(DAYS[0]+','+','.join(numeric for _ in range(4))+',100\n').encode()
            with self.subTest(numeric=numeric),self.assertRaises(ValueError):module.reconstruct_accounted_prefix(**arguments(raw,DAYS[:1]))

    def test_malformed_unconsumed_suffix_and_multiline_trim_are_never_hidden(self):
        base=HEADER+b'\n2026-10-05,10,12,8,10,100\n'
        for suffix in (b'2026-10-06,10,12,8,10,100,EXTRA\n',b'2026-10-06,10,12,8,10,\xff\n',
                b'2026-10-06,"10\n",12,8,10,100\n',b'2026-10-05,10,12,8,10,100\n',b'2026-10-10,10,12,8,10,100\n'):
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):module.reconstruct_accounted_prefix(**arguments(base+suffix,DAYS[:1]))

    def test_whole_evidence_checks_bool_integer_distinctions_and_nested_rows(self):
        raw=HEADER+b'\n2026-10-02,10,9,11,10,100\n'+b''.join((s+',10,12,8,10,100\n').encode()for s in DAYS)
        args=arguments(raw);prefix,evidence=module.reconstruct_accounted_prefix(**args)
        changes=[]
        for field,value in (('byte_start',False),('full_source_byte_count',True),('prefix_is_original_initial_byte_range',1),('timeliness_verified',0)):
            item=deepcopy(evidence);item[field]=value;changes.append(item)
        item=deepcopy(evidence);item['excluded_before_scope_rows'][0]['raw_csv_row']['High']='12';changes.append(item)
        item=deepcopy(evidence);item['excluded_before_scope_ohlc_diagnostics'][0]['violations']=[];changes.append(item)
        for index,item in enumerate(changes):
            with self.subTest(index=index),self.assertRaises(ValueError):module.verify_accounted_prefix(prefix_bytes=prefix,evidence=item,**args)

    def test_import_ast_has_no_producer_dependency_and_runtime_never_reads_files(self):
        tree=ast.parse(Path(module.__file__).read_text())
        imports=[node.module or ''for node in ast.walk(tree)if isinstance(node,ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree)if isinstance(node,ast.Import)for alias in node.names]
        self.assertFalse(any(name.startswith(('backtest','scripts'))for name in imports))
        raw=HEADER+b'\n2026-10-05,10,12,8,10,100'
        with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(producer,'derive_accounted_prefix',side_effect=AssertionError('Producer execution')),patch.dict(sys.modules,{
                'backtest.ndx_forward_source_capture_scoped_research':SimpleNamespace(),
                'backtest.ndx_forward_source_capture_research':SimpleNamespace()}):
            result=module.reconstruct_accounted_prefix(**arguments(raw,DAYS[:1]))
        self.assertEqual(result[0],raw)


if __name__=='__main__':unittest.main()
