import io
import unittest
from copy import deepcopy
from unittest.mock import patch
from scripts import ndx_dated_risk_chain_display_independent_readback_20261003 as m
from test_ndx_dated_risk_chain_display_20261003 import fixture_stream,core
from scripts import ndx_dated_risk_chain_display_20261003 as producer

def case():
    parent,shared,raw=fixture_stream();lines=[];offset=0
    def emit(row):
        nonlocal offset
        b=m.enc(row)+b'\n';r=dict(record_index=len(lines),byte_start=offset,byte_stop=offset+len(b),row_sha256=m.sha(b));offset+=len(b);lines.append(b);return r
    index=producer.project_stream(io.BytesIO(raw),parent,shared,core,emit);controls=index.pop('shared_control_aggregates');output=b''.join(lines)
    index['task_jsonl_reference']=dict(path='output',sha256=m.sha(output),byte_count=len(output),record_count=len(lines))
    return parent,index,shared,controls,raw,output

def inspect(c):
    parent,index,shared,controls,raw,output=c
    return m.inspect_streams(io.BytesIO(raw),io.BytesIO(output),parent,index,shared,controls)

def alter_output(c,change):
    parent,index,shared,controls,raw,output=deepcopy(c);rows=[m.loads(x) for x in output.splitlines()];change(rows);lines=[];offset=0;j=0
    for e in index['task_index']:
        if e['status']=='COMPARISON_NOT_SUPPLIED':continue
        b=m.enc(rows[j])+b'\n';e['jsonl_record']=dict(record_index=j,byte_start=offset,byte_stop=offset+len(b),row_sha256=m.sha(b));lines.append(b);offset+=len(b);j+=1
    output=b''.join(lines);index['task_jsonl_reference'].update(sha256=m.sha(output),byte_count=len(output),record_count=j)
    return parent,index,shared,controls,raw,output

class Tests(unittest.TestCase):
    def test_complete_stream_independent_sums_and_missing(self):
        c=case();before=deepcopy(c);d=inspect(c)
        self.assertEqual(c,before);self.assertEqual(d['planned_tasks'],1632);self.assertEqual(d['projected_tasks'],2);self.assertEqual(d['not_supplied_tasks'],1630);self.assertEqual(d['shared_control_paths_verified_once'],2)
    def test_rehashed_sum_target_cash_and_missing_forgery(self):
        c=case()
        def badsum(rows):rows[0]['targets']['candidate']['aggregation']['saved_literal_total']=m.ratio(m.Fraction(999))
        def badcash(rows):rows[0]['tracks']['candidate_integer']['rows'][0]['cash_fraction_display']=m.ratio(m.Fraction(9))
        def missing(rows):rows[1]['tracks']['candidate_integer']['rows']=[]
        def target(rows):rows[0]['targets']['candidate']['source_evidence']['rows'][0]['original_position']['target_weight']='1'
        def permission(rows):rows[0]['point_in_time_verified']=0
        for fn in (badsum,badcash,missing,target,permission):
            with self.subTest(fn=fn.__name__),self.assertRaises(ValueError):inspect(alter_output(c,fn))
    def test_shared_identity_order_and_zero_unknown(self):
        c=case();bad=deepcopy(c);next(iter(bad[3].values()))['identity']['role']='wrong'
        with self.assertRaises(ValueError):inspect(bad)
        bad=deepcopy(c);bad[1]['task_index'][-1]['k']=True
        with self.assertRaises(ValueError):inspect(bad)
        entries=[dict(security_id='a',risk_chain=None,saved_value='0'),dict(security_id='b',risk_chain='unclassified',saved_value='2'),dict(security_id='c',risk_chain='tech',saved_value='2')]
        saved=core.grouped(entries);m.inspect_group(saved,entries);self.assertEqual(saved['unknown_saved_literal_total'],m.ratio(m.Fraction(2)))
        saved['rows'][0]['members']=[]
        with self.assertRaises(ValueError):m.inspect_group(saved,entries)
    def test_pending_and_fixed_closure_collision(self):
        unbound=deepcopy(m.BOUND)
        unbound['index']=(unbound['index'][0],None)
        with patch.object(m,'BOUND',unbound),patch.object(m.Path,'read_bytes',side_effect=AssertionError('No actual I/O')):
            with self.assertRaises(ValueError):m.readback(execute=True)
        names=('projection_index','projection_publication','projection_audit','projection_reader','projection_producer','projection_core','core','producer')
        refs={k:dict(path=k,sha256='a'*64) for k in names};bound,s=m.expected_producer_sources(refs,dict(path='shared',sha256='a'*64),dict(path='jsonl',sha256='a'*64))
        self.assertEqual(len(bound),7);self.assertEqual(len(s),10)
        refs['core']=dict(path='producer',sha256='b'*64)
        with self.assertRaises(ValueError):m.expected_producer_sources(refs,dict(path='shared',sha256='a'*64),dict(path='jsonl',sha256='a'*64))
if __name__=='__main__':unittest.main()
