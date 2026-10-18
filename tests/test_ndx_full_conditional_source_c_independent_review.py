"""Independent completeness oracle; one real77 call, then isolated read views only."""
import gzip
import hashlib
import itertools
import json
import re
import tempfile
import unittest
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_variable_cardinality_new_cash_source_binding_research as subject

ROOT=Path(__file__).resolve().parents[1]
SUMMARY={}
def sha(blob):return hashlib.sha256(blob).hexdigest()
def normalize(value):
    if type(value) is Decimal:return str(value)
    if type(value) is dict:return {k:normalize(v) for k,v in value.items()}
    if type(value) is list:return [normalize(v) for v in value]
    return value

class ByteJSON:
    """Separate byte-recursive parser, not subject's regex scan + object walk."""
    number=re.compile(rb'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?')
    def __init__(self,blob):self.blob=blob;self.pos=0;self.tokens={}
    def ws(self):
        while self.pos<len(self.blob) and self.blob[self.pos] in b' \r\n\t':self.pos+=1
    def string(self):
        start=self.pos;self.pos+=1
        while self.blob[self.pos]!=34:
            self.pos+=2 if self.blob[self.pos]==92 else 1
        self.pos+=1
        return json.loads(self.blob[start:self.pos])
    def value(self,pointer=''):
        self.ws();ch=self.blob[self.pos]
        if ch==34:return self.string()
        if ch in (123,91):
            obj={} if ch==123 else [];end=125 if ch==123 else 93;self.pos+=1;self.ws()
            if self.blob[self.pos]==end:self.pos+=1;return obj
            while True:
                if ch==123:
                    key=self.string();assert key not in obj;self.ws();assert self.blob[self.pos]==58;self.pos+=1
                    escaped=key.replace('~','~0').replace('/','~1')
                    obj[key]=self.value(pointer+'/'+escaped)
                else:obj.append(self.value(pointer+'/'+str(len(obj))))
                self.ws();sep=self.blob[self.pos];self.pos+=1
                if sep==end:return obj
                assert sep==44;self.ws()
        for word,value in [(b'true',True),(b'false',False),(b'null',None)]:
            if self.blob.startswith(word,self.pos):self.pos+=len(word);return value
        match=self.number.match(self.blob,self.pos);assert match is not None
        start=self.pos;self.pos=match.end();lexeme=match.group().decode('ascii')
        self.tokens[pointer]=dict(original_lexeme=lexeme,utf8_byte_start=start,utf8_byte_stop=self.pos,original_json_type='number')
        return Decimal(lexeme) if any(c in lexeme for c in '.eE') else int(lexeme)
    def parse(self):
        value=self.value();self.ws();assert self.pos==len(self.blob);return value,self.tokens

class IndependentFullPool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert sha(Path(subject.__file__).read_bytes())=='1d8d6197d837d2f1e45b1b999e48e7b543a8920db19418d9d2c003786c2f67e5'
        cls.result=subject.read_conditional_full_pool_sources(include_saved_dual_benchmarks=True)
        cls.facts=cls.result['facts']

    def test_01_all_original_and_required_raw_numeric_sets_not_just_emitted_values(self):
        f=self.facts;self.assertEqual((f['conditional_security_count'],f['conditional_issuer_count'],f['observed_provenance_count']),(77,76,101))
        self.assertEqual(len(f['conditional_inventory']),77);self.assertEqual(len(f['channel_facts']),77)
        self.assertEqual(len(f['observed_provenance']),101)
        catalogue=json.loads(subject._HOST_FILES[1][0].read_bytes())
        pool_blob=Path(catalogue['roles']['pool.0']['reference']['path']).read_bytes()
        pool,pool_tokens=ByteJSON(pool_blob).parse()
        self.assertEqual(f['original_root_numeric_tokens'],{'pool.0':pool_tokens})
        self.assertEqual(f['conditional_inventory'],[dict(zip(pool['panel']['universe']['columns'],normalize(row))) for row in pool['panel']['universe']['data']])
        token_total=raw_total=volume_absent=volume_null=window_count=0;blocks={}
        for i,entry in enumerate(f['channel_facts']):
            blob=Path(entry['source_reference']['path']).read_bytes();original,expected_tokens=ByteJSON(blob).parse()
            self.assertEqual(entry['original_channel'],normalize(original))
            self.assertEqual(entry['original_numeric_tokens'],expected_tokens)
            token_total+=len(expected_tokens)
            raw=Path(entry['raw_reference']['path']).read_bytes();decoded=gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
            provider,raw_tokens=ByteJSON(decoded).parse()
            self.assertEqual(sha(decoded),entry['raw_decoded_sha256'])
            quote=provider['chart']['result'][0]['indicators']['quote'][0]
            expected={}
            for row in original['quote_rows']:
                index=row['raw_row_index']
                if index is None:continue
                for field in ('open','high','low','close','volume'):
                    value=quote[field][index]
                    pointer=f'/chart/result/0/indicators/quote/0/{field}/{index}'
                    if type(value) in (int,Decimal):
                        expected[pointer]=dict(raw_tokens[pointer],exact_fraction=str(Fraction(value)))
                    else:self.assertNotIn(pointer,raw_tokens)
            self.assertEqual(entry['raw_required_scope_numeric_tokens'],expected)
            raw_total+=len(expected)
            self.assertEqual(len(entry['quote_volume_presence']),610)
            for j,(row,desc) in enumerate(zip(original['quote_rows'],entry['quote_volume_presence'])):
                present='raw_volume' in row;value=row.get('raw_volume');pointer=f'/quote_rows/{j}/raw_volume'
                self.assertIs(desc['present'],present)
                self.assertEqual(desc['json_pointer'],pointer if present else None)
                kind='absent' if not present else 'null' if value is None else 'number' if type(value) in (int,Decimal) else 'string'
                self.assertEqual(desc['original_json_type'],kind)
                self.assertEqual(desc['exact_fraction'],str(Fraction(value)) if kind=='number' else None)
                self.assertEqual(desc['original_lexeme'],expected_tokens[pointer]['original_lexeme'] if kind=='number' else None)
                volume_absent+=not present;volume_null+=present and value is None
            self.assertEqual([entry['coordinate']['security_id']], [f['conditional_inventory'][i]['security_id']])
            windows=[w for d in original['decisions'] for w in d['windows']]
            self.assertEqual(len(windows),78);window_count+=len(windows)
            blocks[entry['coordinate']['ticker']]=sum(w['status']=='BLOCKED_WINDOW' for w in windows)
        self.assertEqual(window_count,6006);self.assertEqual(blocks,f['window_coverage']['blocked_by_ticker'])
        self.assertEqual(blocks['WDC'],51);self.assertEqual(blocks['LRCX'],27)
        self.assertEqual(sum(blocks.values()),78)
        for doc in f['saved_dual_benchmarks']['documents'].values():
            original,tokens=ByteJSON(Path(doc['reference']['path']).read_bytes()).parse()
            self.assertEqual(doc['original_document'],normalize(original));self.assertEqual(doc['original_numeric_tokens'],tokens)
        self.assertEqual(f['saved_history_state'],dict(status='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_INDEPENDENT_READBACK',new_independent_numeric_readback_completed=False))
        self.assertEqual(len(f['source_checks']),10);self.assertTrue(all(g['status']=='SOURCE_BLOCKED' for g in f['source_checks']))
        self.assertTrue(all(v is False for v in f['permissions'].values()))
        for key in ('qualified_inventory','qualified_denominator','current_account','current_new_money'):self.assertIsNone(f[key])
        self.assertEqual(f['plan_rows'],[]);self.assertIsNone(f['research_policy']['cash_event'])
        self.assertEqual(f['research_policy']['mathematical_tolerance'],'1/1000000000')
        # One duplicated issuer plus 75 singleton issuers: (1+2z)(1+z)^75.
        import math
        expected_coeff=[math.comb(75,k)+(2*math.comb(75,k-1) if k else 0) if k<=75 else 2 for k in range(1,77)]
        self.assertEqual([int(x['conditional_support_count']) for x in f['issuer_support_domain']['per_k']],expected_coeff)
        SUMMARY.update(original_channel_numeric_tokens=token_total,required_raw_numeric_tokens=raw_total,volume_absent=volume_absent,volume_null=volume_null,window_cells=window_count,source_hashes=deepcopy(f['consumed_source_hashes']),namespaces=deepcopy(f['namespace_snapshots']))

    def test_02_final_guard_read_views_and_detached_internal_baselines(self):
        f=self.facts;guard=self.result['final_guard'];sources=deepcopy(f['consumed_source_hashes']);namespaces=deepcopy(f['namespace_snapshots'])
        guard();f['consumed_source_hashes'].clear();f['namespace_snapshots'].clear();guard()
        actual_read=Path.read_bytes
        paths=[next(p for p in sources if p.endswith('.py')),next(p for p in sources if 'incumbent' in p)]
        for target in paths:
            def changed(path):return actual_read(path)+b' ' if str(path)==target else actual_read(path)
            with patch.object(Path,'read_bytes',changed),self.assertRaisesRegex(ValueError,'Final source drift'):guard()
        actual_iter=Path.iterdir;directory=next(iter(namespaces))
        with tempfile.TemporaryDirectory() as temporary:
            extra=Path(temporary)/'unbound.json';extra.write_bytes(b'{}')
            def extras(path):return iter([*actual_iter(path),extra]) if str(path)==directory else actual_iter(path)
            with patch.object(Path,'iterdir',extras),self.assertRaisesRegex(ValueError,'Final namespace drift'):guard()
        guard()

    def test_03_optional_failed_partial_read_precision_and_fixed_inspector_edges(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);one=root/'one.json';two=root/'two.json';one.write_bytes(b'{}');two.write_bytes(b'{}')
            catalogue=dict(namespaces={'test':dict(profile='OPTIONAL_SAVED_DUAL_NUMBERS',path=str(root),expected_direct_regular_files=['one.json','two.json'])},roles={
                'first':dict(profile='OPTIONAL_SAVED_DUAL_NUMBERS',reference=dict(path=str(one),sha256=sha(b'{}'))),
                'second':dict(profile='OPTIONAL_SAVED_DUAL_NUMBERS',reference=dict(path=str(two),sha256='0'*64))})
            session=subject._ReadSession(catalogue);result=subject._saved_benchmarks(session,catalogue)
            self.assertEqual(result['status'],'SOURCE_BLOCKED');self.assertIs(result['partial_proof_claimed'],False)
            self.assertEqual(session.sources,{str(one):sha(b'{}')});session.guard()
            one.write_bytes(b'{ }')
            with self.assertRaisesRegex(ValueError,'Final source drift'):session.guard()
        blob='{"非ASCII/键~":[-0.00e+2,1.23456789012345678901e-3,null,true],"1":"2"}'.encode()
        left,compat,tokens=subject._strict_views(blob,with_tokens=True);expected,etokens=ByteJSON(blob).parse()
        self.assertEqual(left,expected);self.assertEqual(tokens,etokens)
        self.assertNotEqual(Fraction(left['非ASCII/键~'][1]),Fraction(compat['非ASCII/键~'][1]))
        with patch.object(Path,'read_bytes',side_effect=AssertionError('caller IO trap')):
            for value in [1,None,'true']:
                with self.assertRaises(ValueError):subject.read_conditional_full_pool_sources(include_saved_dual_benchmarks=value)
            with self.assertRaisesRegex(ValueError,'Unknown host role'):subject._ReadSession(dict(roles={})).take('arbitrary.source_hashes')
        # Fixed pure price inspector only: no original producer or IO reader entry.
        session,catalogue,_,_=subject._bootstrap(False);inspector=subject._pure_inspector(session)
        channel=session.document('channel.000.reference')[1];index=session.document('history.0')[1]
        bridge=session.document('ndx_multidecision_scoring_history_independent_readback_v2_20261003.py.BOUND.bridge')[1]
        args=dict(saved_channel=channel,raw_bytes=session.take('channel.000.raw_reference'),raw_reference=channel['raw_reference'],receipt=session.document('channel.000.receipt_reference')[1],receipt_reference=channel['receipt_reference'],bridge_row=next(r for r in bridge['rows'] if r['ticker']==channel['ticker']),reference_calendar=index['reference_calendar']['dates'],tzif_bytes=session.take('timezone.new_york'),window_contract=index['window_contract'],outer_inventory_contract=index['outer_inventory_contract'])
        bad=deepcopy(args);bad['receipt']['raw_bytes']+=1
        with self.assertRaisesRegex(ValueError,'Receipt binds bytes'):inspector.inspect_scoring_history_channel(**bad)
        bad=deepcopy(args);bad['raw_bytes']+=b' '
        with self.assertRaisesRegex(ValueError,'Raw bytes binding'):inspector.inspect_scoring_history_channel(**bad)
        bad=deepcopy(args);bad['tzif_bytes']=b'not TZif'
        with self.assertRaises(ValueError):inspector.inspect_scoring_history_channel(**bad)
        session.guard()

if __name__=='__main__':unittest.main()
