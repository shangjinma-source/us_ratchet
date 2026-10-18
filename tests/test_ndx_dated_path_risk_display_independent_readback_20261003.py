from copy import deepcopy
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_dated_path_risk_display_independent_readback_20261003 as r
from scripts import ndx_dated_path_risk_display_20261003 as producer
from backtest import ndx_dated_path_risk_display_research as core
from test_ndx_dated_path_risk_display_research import fixture
from test_ndx_dated_path_risk_display_wrapper_20261003 import summary_fixture


def stream_fixture():
    summary=summary_fixture();second=summary['rows'][7]['numerical_task_id']
    inputs={r.FIRST:fixture(first=True),second:fixture(task_id=second,missing=True)}
    lines=[];offset=0
    def write(row):
        nonlocal offset
        b=r.enc(row)+b'\n';start=offset;offset+=len(b);lines.append(b)
        return dict(record_index=len(lines)-1,byte_start=start,byte_stop=offset,row_sha256=r.sha(b))
    index=producer.stream_paths(summary,dict.fromkeys(inputs,{}),lambda t,x:inputs[t],core,write)
    raw=b''.join(lines);index['task_jsonl_reference']=dict(path='tasks.jsonl',sha256=r.sha(raw),byte_count=len(raw),record_count=len(lines))
    return raw,index,summary,inputs


def inspect(data):
    raw,index,summary,inputs=data
    return r.inspect_stream(BytesIO(raw),index,index['shared_paths'],summary,lambda t,refs:(inputs[t]['document'],inputs[t]['inputs_document']))


class Tests(unittest.TestCase):
    def test_fixed_sources_exact_union_and_reader_not_arbitrary_python(self):
        base={'producer.py':'a'*64,'core.py':'b'*64}
        items=[dict(path='comparison.json',sha256='c'*64),dict(path='comparison.json',sha256='c'*64)]
        expected={**base,'comparison.json':'c'*64}
        self.assertEqual(r.check_source_closure(expected,base,items),expected)
        for bad in ({**expected,'injected.py':'d'*64},{k:v for k,v in expected.items() if k!='core.py'},{**expected,'comparison.json':'d'*64}):
            with self.assertRaises(ValueError):r.check_source_closure(bad,base,items)
        p,h=r.READERS['inputs']
        with self.assertRaises(ValueError):r.check_reader(dict(reader_sha256=h,source_hashes={'other.py':h}),'inputs')
        r.check_reader(dict(reader_sha256=h,source_hashes={str(r.ROOT/p):h}),'inputs')
        with patch.object(r,'BOUND',{**r.BOUND,'batch':(r.BOUND['batch'][0],None)}):
            with self.assertRaises(ValueError):r.fixed_base()

    def test_full_index_two_encodings_shared_and_absence(self):
        data=stream_fixture();before=deepcopy(data)
        result=inspect(data)
        self.assertEqual(result['projected_task_count'],2)
        self.assertEqual(result['not_supplied_task_count'],1630)
        self.assertEqual(result['shared_path_count'],4)
        self.assertEqual(data,before)

    def test_resigned_daily_risk_target_or_shared_mutation_rejected(self):
        for attack in ('daily','target','gap','shared','missing'):
            data=list(stream_fixture());rows=[r.loads(line) for line in data[0].splitlines()]
            if attack=='daily':rows[0]['tracks']['candidate_integer']['path'][2]['cash_usd']=9
            elif attack=='target':rows[0]['target_evidence']['candidate']['rows'][0]['risk_chain']='invented'
            elif attack=='gap':rows[0]['original_provenance_and_missing']=[]
            elif attack=='shared':next(iter(data[1]['shared_paths'].values()))['payload']['metrics']['maximum_drawdown']['exact']='99'
            else:rows[1]['tracks']['candidate_integer']['calendar_slots'][0]['value']=0
            lines=[];offset=0
            for i,row in enumerate(rows):
                b=r.enc(row)+b'\n';entry=data[1]['task_index'][0 if i==0 else 7]
                entry['jsonl_record']=dict(record_index=i,byte_start=offset,byte_stop=offset+len(b),row_sha256=r.sha(b));offset+=len(b);lines.append(b)
            data[0]=b''.join(lines);data[1]['task_jsonl_reference'].update(sha256=r.sha(data[0]),byte_count=len(data[0]))
            with self.subTest(attack=attack),self.assertRaises(ValueError):inspect(data)

    def test_byte_tail_order_and_pending_source_gate(self):
        for attack in ('tail','offset','order','bool'):
            data=list(stream_fixture())
            if attack=='tail':data[0]+=b'\n'
            elif attack=='offset':data[1]['task_index'][0]['jsonl_record']['byte_start']=1
            elif attack=='order':data[1]['task_index'][0],data[1]['task_index'][1]=data[1]['task_index'][1],data[1]['task_index'][0]
            else:data[1]['task_index'][0]['task_ordinal']=False
            with self.subTest(attack=attack),self.assertRaises(ValueError):inspect(data)
        with patch.object(r,'INDEX_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('No pending I/O')):
            with self.assertRaises(ValueError):r.readback(execute=True)

if __name__=='__main__':unittest.main()
