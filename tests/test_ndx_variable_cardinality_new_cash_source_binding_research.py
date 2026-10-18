"""Bounded author regressions; real77 replay is an explicit separate test class."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import gzip
import json
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_variable_cardinality_new_cash_source_binding_research as subject


class StrictSourceUnits(unittest.TestCase):
    def test_lexemes_and_utf8_pointer_offsets(self):
        blob = '{"中/文~": [1.0e+02,100.0,100,-0,0.123456789012345678901],"s":"number12"}'.encode()
        left, compat, tokens = subject._strict_views(blob, with_tokens=True)
        self.assertEqual(left['中/文~'][-1], Decimal('0.123456789012345678901'))
        self.assertNotEqual(Fraction(compat['中/文~'][-1]), Fraction(left['中/文~'][-1]))
        self.assertEqual([t['original_lexeme'] for t in tokens.values()],
                         ['1.0e+02', '100.0', '100', '-0', '0.123456789012345678901'])
        for pointer, token in tokens.items():
            self.assertTrue(pointer.startswith('/中~1文~0/'))
            self.assertEqual(blob[token['utf8_byte_start']:token['utf8_byte_stop']].decode(), token['original_lexeme'])

    def test_escaped_strings_are_not_numeric_tokens(self):
        left, _, tokens = subject._strict_views(b'{"x":"\\\"123","u":"\\u0031","2":3}', with_tokens=True)
        self.assertEqual(list(tokens), ['/2'])
        self.assertEqual(left['u'], '1')

    def test_duplicate_and_nonfinite_rejected(self):
        for blob in [b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'NaN', b'Infinity', b'-Infinity', b'1e400']:
            with self.subTest(blob=blob), self.assertRaises(ValueError):
                subject._strict_views(blob, with_tokens=True)

    def test_utf8_and_trailing_json_rejected(self):
        for blob in [b'"\xff"', '{"a":1}'.encode('utf-16'), b'1 2', b'[01]', b'[true,]']:
            with self.subTest(blob=blob), self.assertRaises((ValueError, UnicodeError)):
                subject._strict_views(blob, with_tokens=True)

    def test_missing_and_null_volume_are_distinct(self):
        left, _, tokens = subject._strict_views(b'[{"status":"B"},{"raw_volume":null},{"raw_volume":1.00e+3}]', with_tokens=True)
        absent = subject._number_descriptor(left[0], 'raw_volume', '/0', tokens)
        null = subject._number_descriptor(left[1], 'raw_volume', '/1', tokens)
        number = subject._number_descriptor(left[2], 'raw_volume', '/2', tokens)
        self.assertFalse(absent['present'])
        self.assertIsNone(absent['json_pointer'])
        self.assertTrue(null['present'])
        self.assertEqual(null['original_json_type'], 'null')
        self.assertEqual(number['original_lexeme'], '1.00e+3')
        self.assertEqual(number['exact_fraction'], '1000')

    def test_json_fidelity_keeps_exact_values_and_bool_type(self):
        left, _, tokens = subject._strict_views(b'{"x":0.10000000000000000001,"b":true}', with_tokens=True)
        result = subject._json_fidelity(left)
        self.assertEqual(result['x'], '0.10000000000000000001')
        self.assertIs(result['b'], True)
        self.assertNotIn('/b', tokens)

    def test_raw_exact_view_never_requires_float_conversion(self):
        left,tokens,decoded=subject._raw_fidelity(b'{"price":1.0000000000000000001,"scale":1e400}')
        self.assertEqual(left['price'],Decimal('1.0000000000000000001'))
        self.assertEqual(tokens['/scale']['original_lexeme'],'1e400')
        self.assertEqual(decoded,subject._sha(b'{"price":1.0000000000000000001,"scale":1e400}'))

    def test_raw_decoder_bounds_and_strict_json(self):
        with patch.object(subject,'_MAX_RAW',64):
            with self.assertRaisesRegex(ValueError,'Decoded raw byte bound'):
                subject._raw_fidelity(gzip.compress(b' '*65,mtime=0))
            with self.assertRaisesRegex(ValueError,'Raw byte bound'):
                subject._raw_fidelity(b' '*65)
        for blob in [b'{"x":1,"x":2}',b'{"x":NaN}',b'"\xff"']:
            with self.subTest(blob=blob),self.assertRaises((ValueError,UnicodeError)):
                subject._raw_fidelity(blob)

    def test_unknown_role_rejected_before_io(self):
        session = subject._ReadSession(dict(roles={}))
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('IO trap')):
            with self.assertRaisesRegex(ValueError, 'Unknown host role'):
                session.take('extra.trap')

    def test_bad_host_pins_precede_any_io(self):
        for pin in [None, '', 'z' * 64, True]:
            with patch.object(subject, '_HOST_FILES', ((Path('E:/trap.json'), pin),)), \
                    patch.object(Path, 'read_bytes', side_effect=AssertionError('IO trap')), \
                    patch.object(Path, 'lstat', side_effect=AssertionError('stat trap')):
                with self.assertRaisesRegex(ValueError, 'host pin'):
                    subject.read_conditional_full_pool_sources()

    def test_optional_flag_requires_actual_bool_before_io(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('IO trap')):
            for value in [1, 'yes', None, [], {}]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    subject.read_conditional_full_pool_sources(include_saved_dual_benchmarks=value)

    def test_fixed_host_sha_rejects_before_following_trap_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trap = root / 'trap.json'
            document = root / 'source.json'
            original = b'{"source_hashes":{}}'
            document.write_bytes(original)
            catalog = dict(roles={'root': dict(reference=dict(path=str(document), sha256=subject._sha(original)))})
            session = subject._ReadSession(catalog)
            document.write_text(json.dumps({'source_hashes': {str(trap): '0' * 64}}))
            with self.assertRaisesRegex(ValueError, 'Source bytes changed'):
                session.document('root')
            self.assertFalse(trap.exists())

    def test_guard_source_namespace_and_detached_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root / 'one.json'
            p.write_bytes(b'{}')
            session = subject._ReadSession(dict(roles={'one':dict(reference=dict(path=str(p),sha256=subject._sha(b'{}')))}))
            session.take('one')
            expected = [dict(name='one.json',type='regular_file',reparse_point=False)]
            session.bind_namespace(str(root), expected)
            detached = deepcopy(session.sources)
            detached.clear()
            session.guard()
            p.write_bytes(b'{ }')
            with self.assertRaisesRegex(ValueError, 'Final source drift'):
                session.guard()
            p.write_bytes(b'{}')
            extra = root / 'failure.json'
            extra.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'Final namespace drift'):
                session.guard()
            extra.unlink()
            session.guard()

    def test_namespace_subdirectory_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'extra').mkdir()
            with self.assertRaisesRegex(ValueError, 'Host file type'):
                subject._namespace_snapshot(directory)

    def test_reparse_path_rejected_before_open(self):
        import stat
        import types
        info=types.SimpleNamespace(st_mode=stat.S_IFREG,st_file_attributes=1024)
        with patch.object(Path,'lstat',return_value=info), patch.object(Path,'read_bytes',side_effect=AssertionError('read trap')):
            with self.assertRaisesRegex(ValueError,'reparse'):
                subject._regular_path(Path('E:/explicit_fixture.json'))

    def test_json_byte_and_depth_bounds(self):
        with patch.object(subject,'_MAX_JSON',3):
            with self.assertRaisesRegex(ValueError,'JSON byte bound'):
                subject._strict_views(b'[123]')
        with self.assertRaisesRegex(ValueError,'depth bound'):
            subject._strict_views(('['*130+'0'+']'*130).encode())

    def test_issuer_multiclass_all_k_coefficients(self):
        coordinates = [dict(issuer_id='A'),dict(issuer_id='A'),dict(issuer_id='B'),dict(issuer_id='C')]
        result = subject._issuer_coefficients(coordinates)
        # Independently count each small class subset; incompatible A+A excluded.
        import itertools
        expected = []
        for k in range(1,4):
            expected.append(sum(len({coordinates[i]['issuer_id'] for i in group})==k
                                for group in itertools.combinations(range(4), k)))
        self.assertEqual([int(r['conditional_support_count']) for r in result['per_k']], expected)
        self.assertEqual(result['k_above_issuer_count']['first_k'],4)
        self.assertIsNone(result['qualified_denominator'])

    def test_optional_failure_is_explicit_not_partial_proof(self):
        class Session:
            def bind_namespace(self, *args):
                raise ValueError('fixture optional failure')
        result = subject._saved_benchmarks(Session(),dict(namespaces={'one':dict(profile='OPTIONAL_SAVED_DUAL_NUMBERS',path='unused',expected_direct_regular_files=[])}))
        self.assertEqual(result['status'],'SOURCE_BLOCKED')
        self.assertFalse(result['partial_proof_claimed'])


class PinnedPureInspectorEdges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session, cls.catalogue, _, _=subject._bootstrap(False)
        cls.inspector=subject._pure_inspector(cls.session)
        cls.tzif=cls.session.take('timezone.new_york')

    def case(self,raw):
        rawref=dict(path='E:\\synthetic_only\\raw.bin',sha256=subject._sha(raw))
        receiptref=dict(path='E:\\synthetic_only\\receipt.json',sha256='1'*64)
        receipt=dict(ticker='SYNTHETIC',raw_path=rawref['path'],raw_sha256=rawref['sha256'],raw_bytes=len(raw),
                     http_status=200,received_at_utc='2026-09-23T16:00:00+00:00',promotion_allowed=False,point_in_time_verified=False)
        bridge=dict(ticker='SYNTHETIC',new_raw_reference=rawref,new_receipt_reference=receiptref,new_decoded_sha256='0'*64)
        return dict(saved_channel={'schema':'MULTIDECISION_SCORING_HISTORY_CHANNEL_V1'},raw_bytes=raw,
                    raw_reference=rawref,receipt=receipt,receipt_reference=receiptref,bridge_row=bridge,
                    reference_calendar=[],tzif_bytes=self.tzif,window_contract=deepcopy(self.inspector.CONTRACT),outer_inventory_contract={})

    def test_frozen_checker_rejects_decimal_saved_json(self):
        with self.assertRaises(TypeError):
            self.inspector.encoded({'saved_float':Decimal('0.1')})
        self.assertEqual(self.inspector.encoded({'saved_float':0.1}),b'{"saved_float":0.1}')

    def test_gzip_decoded_bound(self):
        args=self.case(gzip.compress(b' '*65,mtime=0))
        with patch.object(self.inspector,'MAX_BYTES',64):
            with self.assertRaisesRegex(ValueError,'Decoded bytes'):
                self.inspector.inspect_scoring_history_channel(**args)

    def test_raw_duplicate_and_nonfinite_before_provider_parse(self):
        for raw,expected in [(b'{"chart":1,"chart":2}','Duplicate JSON key'),(b'{"chart":NaN}','Nonfinite JSON')]:
            args=self.case(raw);args['bridge_row']['new_decoded_sha256']=subject._sha(raw)
            with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,expected):
                self.inspector.inspect_scoring_history_channel(**args)

    def test_resigned_saved_last_price_does_not_pass_whole_arithmetic(self):
        saved=self.session.document('channel.000.reference')[1]
        bridge_role='ndx_multidecision_scoring_history_independent_readback_v2_20261003.py.BOUND.bridge'
        bridge=self.session.document(bridge_role)[1]
        bridge_row=next(r for r in bridge['rows'] if r['ticker']==saved['ticker'])
        index=self.session.document('history.0')[1]
        changed=deepcopy(saved)
        changed['quote_rows'][-1]['nominal_close_exact']='1'
        changed['quote_rows_sha256']=self.inspector.digest(changed['quote_rows'])
        changed['content_sha256']=self.inspector.digest({k:v for k,v in changed.items() if k!='content_sha256'})
        with self.assertRaisesRegex(ValueError,'Independent complete nominal slots'):
            self.inspector.inspect_scoring_history_channel(saved_channel=changed,
                raw_bytes=self.session.take('channel.000.raw_reference'),raw_reference=saved['raw_reference'],
                receipt=self.session.document('channel.000.receipt_reference')[1],receipt_reference=saved['receipt_reference'],
                bridge_row=bridge_row,reference_calendar=index['reference_calendar']['dates'],tzif_bytes=self.tzif,
                window_contract=index['window_contract'],outer_inventory_contract=index['outer_inventory_contract'])
        self.session.guard()


class FixedReal77Readback(unittest.TestCase):
    def test_whole77_price_only_and_saved_dual_numbers(self):
        result = subject.read_conditional_full_pool_sources(include_saved_dual_benchmarks=True)
        facts = result['facts']
        self.assertEqual((facts['conditional_security_count'],facts['conditional_issuer_count'],facts['observed_provenance_count']), (77,76,101))
        self.assertEqual(len(facts['channel_facts']),77)
        self.assertEqual(len(facts['observed_provenance']),101)
        self.assertEqual(facts['window_coverage']['total_sid_decision_window_cells'],6006)
        self.assertEqual(facts['window_coverage']['blocked_by_ticker']['WDC'],51)
        self.assertEqual(facts['window_coverage']['blocked_by_ticker']['LRCX'],27)
        self.assertEqual(len(facts['matrix_layout']['required_union_dates']),610)
        self.assertEqual(facts['issuer_support_domain']['per_k'][0],dict(k=1,conditional_support_count='77'))
        self.assertEqual(facts['issuer_support_domain']['per_k'][-1],dict(k=76,conditional_support_count='2'))
        self.assertTrue(facts['research_policy']['source_reference']['path'].endswith('multidecision_stateful_account_inputs_20261003_v1.json'))
        self.assertIsNone(facts['research_policy']['cash_event'])
        self.assertEqual(facts['saved_dual_benchmarks']['status'],'SAVED_NUMBER_AND_EXISTING_AUDIT_ASSOCIATION_ONLY_NOT_NEW_RAW_REPLAY')
        self.assertFalse(any(facts['permissions'].values()))
        self.assertIsNone(facts['qualified_inventory'])
        self.assertIsNone(facts['qualified_denominator'])
        self.assertIsNone(facts['current_new_money'])
        self.assertIsNone(facts['current_account'])
        self.assertEqual(facts['plan_rows'],[])
        self.assertEqual(len(facts['source_checks']),10)
        self.assertTrue(all(c['status']=='SOURCE_BLOCKED' for c in facts['source_checks']))
        self.assertFalse(facts['saved_history_state']['new_independent_numeric_readback_completed'])
        catalogue=json.loads(subject._HOST_FILES[1][0].read_text(encoding='utf-8'))
        for role,item in catalogue['roles'].items():
            if item['profile']=='OPTIONAL_SAVED_DUAL_NUMBERS':
                self.assertIn(role,facts['saved_dual_benchmarks']['fixed_optional_roles_read'])
                self.assertEqual(facts['consumed_source_hashes'][item['reference']['path']],item['reference']['sha256'])
        optional=facts['saved_dual_benchmarks']['documents']
        for role,entry in optional.items():
            blob=Path(entry['reference']['path']).read_bytes()
            saved=json.loads(blob,parse_float=Decimal)
            def normalize_optional(value):
                if isinstance(value,Decimal):return str(value)
                if isinstance(value,dict):return {k:normalize_optional(v) for k,v in value.items()}
                if isinstance(value,list):return [normalize_optional(v) for v in value]
                return value
            self.assertEqual(entry['original_document'],normalize_optional(saved))
            for token in entry['original_numeric_tokens'].values():
                self.assertEqual(blob[token['utf8_byte_start']:token['utf8_byte_stop']].decode(),token['original_lexeme'])
        modes=optional['target_training.1']['original_document']['modes']
        self.assertEqual(sum(w['status']=='BLOCKED_WINDOW' for d in modes[0]['decisions'] for w in d['windows']),78)
        self.assertEqual(sum(w['status']=='CONDITIONAL_NUMERIC_WINDOW' for d in modes[1]['decisions'] for w in d['windows']),78)
        for channel in facts['channel_facts']:
            reference = channel['source_reference']
            blob = Path(reference['path']).read_bytes()
            self.assertEqual(subject._sha(blob),reference['sha256'])
            # Independent standard Decimal load and recursive conversion, not subject decoder.
            saved = json.loads(blob,parse_float=Decimal)
            def normalize(value):
                if isinstance(value,Decimal):return str(value)
                if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
                if isinstance(value,list):return [normalize(v) for v in value]
                return value
            self.assertEqual(channel['original_channel'],normalize(saved))
            raw=Path(channel['raw_reference']['path']).read_bytes()
            decoded=gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
            self.assertEqual(subject._sha(decoded),channel['raw_decoded_sha256'])
            provider=json.loads(decoded,parse_float=Decimal)
            self.assertEqual(channel['raw_token_offsets'],'DECODED_UTF8_JSON_BYTES_NOT_COMPRESSED_FILE_OFFSETS')
            for pointer,token in channel['raw_required_scope_numeric_tokens'].items():
                self.assertEqual(decoded[token['utf8_byte_start']:token['utf8_byte_stop']].decode(),token['original_lexeme'])
                value=provider
                for key in pointer.split('/')[1:]:
                    value=value[int(key)] if isinstance(value,list) else value[key]
                self.assertEqual(Fraction(Decimal(token['original_lexeme'])),Fraction(value))
                self.assertEqual(token['exact_fraction'],str(Fraction(value)))
            self.assertEqual(len(saved['quote_rows']),610)
            self.assertEqual(len(saved['return_rows']),609)
            for pointer,token in channel['original_numeric_tokens'].items():
                self.assertEqual(blob[token['utf8_byte_start']:token['utf8_byte_stop']].decode('utf-8'),token['original_lexeme'])
                value=saved
                for key in pointer.split('/')[1:]:
                    key=key.replace('~1','/').replace('~0','~')
                    value=value[int(key)] if isinstance(value,list) else value[key]
                self.assertEqual(Decimal(token['original_lexeme']),value)
            for row,descriptor in zip(saved['quote_rows'],channel['quote_volume_presence']):
                self.assertEqual(descriptor['present'],'raw_volume' in row)
                if not descriptor['present']:self.assertIsNone(descriptor['json_pointer'])
            self.assertEqual(sum(len(d['windows']) for d in saved['decisions']),78)
        # Facts mutation cannot alter the internally closed guard baseline.
        source_snapshot=deepcopy(facts['consumed_source_hashes'])
        namespace_snapshot=deepcopy(facts['namespace_snapshots'])
        facts['consumed_source_hashes'].clear()
        facts['namespace_snapshots'].clear()
        result['final_guard']()
        global LAST_REAL_SUMMARY
        LAST_REAL_SUMMARY=dict(status='PASS_ALL77_PRICE_RETURN_WINDOW_REPLAY_AND_SAVED_DUAL_ASSOCIATION',
            security_count=77,issuer_count=76,provenance_count=101,window_cells=6006,blocked_wdc=51,blocked_lrcx=27,
            source_hashes=source_snapshot,
            namespace_snapshots=namespace_snapshot,
            real_pit_or_liquidity_qualification=False,fit_or_solver_or_economic_run=False,account_io=False,
            optional_benchmark_fresh_raw_replay=False)


if __name__ == '__main__':
    unittest.main()
