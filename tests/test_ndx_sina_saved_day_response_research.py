import csv,io,json,unittest
from datetime import date,timedelta
from decimal import localcontext,Inexact
from backtest import ndx_sina_saved_day_response_research as m

def fixture(ticker='QQQ'):
    days=[];d=date(2026,7,1)
    while d<=date(2026,10,1):
        if d.weekday()<5:days.append(d.isoformat())
        d+=timedelta(days=1)
    days.remove('2026-07-03');days.remove('2026-09-07')
    assert len(days)==65
    out=io.StringIO();w=csv.writer(out,lineterminator='\n');w.writerow(['Date',*m.FIELDS])
    for d in days:w.writerow([d,'100','102','99','101','123'])
    rows=[dict(d=d,o='100.0',h='102',l='99',c='101',v='123') for d in days+['2026-10-02']]
    raw=('var _='+ticker+'_day('+json.dumps(rows)+');').encode()
    return raw,out.getvalue().encode(),rows

def raw(rows):return ('var _=QQQ_day('+json.dumps(rows)+');').encode()
class Tests(unittest.TestCase):
    def test_exact_overlap_context_and_no_authority(self):
        b,c,_=fixture()
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True
            r=m.inspect_response(raw_bytes=b,ticker='QQQ',baseline_csv_bytes=c)
        self.assertTrue(r['overlap_numeric_equal']);self.assertTrue(r['exact_single_new_target']);self.assertEqual(len(r['overlap']),65)
        for k in m.FLAGS:self.assertIs(r[k],False)
    def test_missing_and_revision_not_intersection(self):
        _,c,rows=fixture();rows.pop(3);rows[4]['c']='100'
        r=m.inspect_response(raw_bytes=raw(rows),ticker='QQQ',baseline_csv_bytes=c)
        self.assertEqual(len(r['missing_baseline_sessions']),1);self.assertEqual(len(r['overlap_differences']),1);self.assertFalse(r['overlap_numeric_equal'])
    def test_strict_envelope_duplicates_fields_and_ohlc(self):
        b,c,rows=fixture()
        candidates=[b.replace(b'QQQ_day',b'SPY_day'),b+b'evil();',b.replace(b'"o": "100.0"',b'"o":"1","o":"2"',1)]
        for change in ('missing','bounds','duplicate'):
            q=json.loads(json.dumps(rows))
            if change=='missing':del q[-1]['o']
            elif change=='bounds':q[-1]['h']='98'
            else:q.append(q[-1])
            candidates.append(raw(q))
        for b in candidates:
            with self.subTest(),self.assertRaises(ValueError):m.inspect_response(raw_bytes=b,ticker='QQQ',baseline_csv_bytes=c)
    def test_outside_bad_and_future_retained(self):
        _,c,rows=fixture();rows.insert(0,dict(d='2015-03-30',o='100',h='98',l='99',c='101',v='1'));rows.append(dict(d='2026-10-05',o='100',h='102',l='99',c='101',v='1'))
        r=m.inspect_response(raw_bytes=raw(rows),ticker='QQQ',baseline_csv_bytes=c)
        self.assertEqual(len(r['outside_scope_ohlc_diagnostics']),1);self.assertEqual(r['future_sessions'],['2026-10-05']);self.assertFalse(r['exact_single_new_target'])
if __name__=='__main__':unittest.main()
