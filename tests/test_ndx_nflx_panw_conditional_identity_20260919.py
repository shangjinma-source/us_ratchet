import unittest
from scripts import ndx_nflx_panw_conditional_identity_20260919 as reader


def fixture(ticker):
    s=reader.CASES[ticker]
    memo=f"#{s['memo_number']} Date: {s['memo_date']} 100 {s['company']} ({ticker}) Common Shares CUSIP:{s['cusip']} This Information Memo provides an unofficial summary"
    memo+=f" Ex-Date: {s['ex_date']} The Ex-distribution Date is {s['event_text']}. Effective Date:{s['event_text']}"
    if ticker=='NFLX':memo+=" (NFLX) has announced a 10 for 1 stock split, subject to the filing of an amendment to the Company's Amended and Restated Certificate of Incorporation."
    fields={'EntityCentralIndexKey':s['cik'],'EntityRegistrantName':s['cover_company'],'TradingSymbol':ticker,'Security12bTitle':s['title'],'DocumentPeriodEndDate':s['period']}
    cover=''.join(f'<ix:nonNumeric name="dei:{k}" contextRef="{s["context"]}">{v}</ix:nonNumeric>' for k,v in fields.items()).encode()
    return memo,cover


class ConditionalIdentityTests(unittest.TestCase):
    def test_two_explicit_relations_preserve_limits(self):
        for ticker in reader.CASES:
            value=reader.relation(ticker,*fixture(ticker))
            self.assertTrue(all(value[f] is False for f in reader.FALSE))
            self.assertEqual(value['conditional_research_security_id'],'security:'+reader.CASES[ticker]['cik']+':'+reader.CASES[ticker]['cusip'])

    def test_wrong_class_cik_context_and_duplicate_rejected(self):
        memo,cover=fixture('NFLX')
        for bad in (cover.replace(b'Common stock',b'Class B stock'),cover.replace(b'0001065280',b'0001327567'),cover.replace(b'contextRef=',b'wrongContext='),cover+cover):
            with self.assertRaises(ValueError):reader.relation('NFLX',memo,bad)

    def test_memo_class_condition_cusip_and_wrapper_rejected(self):
        memo,cover=fixture('NFLX')
        for bad in (memo.replace('Common Shares','Class B Shares'),memo.replace('subject to the filing','after the filing'),memo+' CUSIP:000000000'):
            with self.assertRaises(ValueError):reader.relation('NFLX',bad,cover)
        with self.assertRaises(ValueError):reader.pdf_payload(b'%PDF-forged-direct','PANW')


if __name__=='__main__':unittest.main()
