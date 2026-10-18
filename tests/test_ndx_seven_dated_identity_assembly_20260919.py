import copy,unittest
from scripts import ndx_seven_dated_identity_assembly_20260919 as m

class AssemblyTests(unittest.TestCase):
    def rows(self):
        return [dict(ticker=t,subject_cik=cik,issuer_id=f'issuer:{cik}',cusip=cusip,security_id=f'security:{cik}:{cusip}',security_class=m.CLASS_TITLES[t],continuous_interval_verified=False,provider_binding_verified=False,point_in_time_verified=False) for t,(cik,cusip) in m.COORDINATES.items()]

    def test_full_denominator_and_no_identity_upgrade(self):
        m.validate_rows(self.rows())
        for mutate in (lambda r:r.pop(),lambda r:r[0].update(cusip='000000000'),lambda r:r[0].update(subject_cik='0001364742'),lambda r:r[0].update(point_in_time_verified=True),lambda r:r[0].update(evidence_available_date='2023-03-31'),lambda r:next(x for x in r if x['ticker']=='BKR').update(security_class='Class B Common Stock')):
            rows=self.rows();mutate(rows)
            with self.assertRaises(ValueError):m.validate_rows(rows)

    def test_cover_requires_same_context_class(self):
        raw=b'<ix:nonNumeric name="dei:EntityCentralIndexKey">0001262039</ix:nonNumeric><ix:nonNumeric name="dei:TradingSymbol" contextRef="a">FTNT</ix:nonNumeric><ix:nonNumeric name="dei:Security12bTitle" contextRef="b">Common Stock</ix:nonNumeric>'
        with self.assertRaises(ValueError):m.cover_fields(raw,'FTNT','0001262039')

    def test_actual_sources_without_publication_or_execution(self):
        v=m.build();self.assertEqual(len(v['rows']),7);self.assertFalse(v['execution_performed'])
        self.assertEqual({r['ticker'] for r in v['rows']},set(m.COORDINATES))
        self.assertEqual(next(r for r in v['rows'] if r['ticker']=='FTNT')['evidence']['memo_cik_link'],'CROSS_DOCUMENT_TICKER_COMMON_CLASS_CONDITIONAL_NOT_CIK_IN_MEMO')
        for key,value in [('conditional_window',{'start':'2022-01-01','end':'2023-05-01'}),('promotion_allowed',True),('provider_price_binding_verified',True),('point_in_time_verified',True),('issuer_count',True)]:
            changed=copy.deepcopy(v);changed[key]=value
            with self.assertRaises(ValueError):m.validate_report(changed)

if __name__=='__main__':unittest.main()
