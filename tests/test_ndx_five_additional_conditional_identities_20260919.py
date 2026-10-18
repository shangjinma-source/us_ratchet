import unittest
from scripts import ndx_five_additional_conditional_identities_20260919 as m


def fixture(t):
    s=m.CASES[t]
    fields={'EntityCentralIndexKey':s['cik'],'EntityRegistrantName':s['cover_company'],'TradingSymbol':t,'Security12bTitle':s['title'],'DocumentPeriodEndDate':s['period']}
    cover=''.join(f'<ix:nonNumeric name="dei:{k}" contextRef="{s["context"]}">{v}</ix:nonNumeric>' for k,v in fields.items()).encode()
    if t=='LRCX':
        text="Lam Research Corporation 94-2634797 October 2, 2024 10-for-1 forward stock split 512807306 LRCX Lam Research Corporation announced a 10-for-1 forward stock split of the issuer's common stock. The forward stock split became effective at 5PM Eastern Time on October 2, 2024; every one (1) share of the issuer's common stock issued and outstanding at the Effective Time was automatically divided into 10 (ten) shares of common stock."
    else:
        text=f"#{s['memo']} Date: {s['date']} Ex-Date: {s['ex']} The Ex-distribution Date is {s['event']}. Effective Date:{s['event']} 100 {s['company']} ({t}) Common Shares CUSIP:{s['cusip']} This Information Memo provides an unofficial summary"
    return text,cover


class FiveIdentityTests(unittest.TestCase):
    def test_conditional_relations_and_no_old_lrcx_stitch(self):
        for t in m.CASES:
            row=m.relation(t,*fixture(t))
            self.assertTrue(all(row[k] is False for k in m.FALSE))
            self.assertEqual(row['cusip'],m.CASES[t]['cusip'])
        row=m.relation('LRCX',*fixture('LRCX'))
        self.assertEqual(row['minimum_conditional_date'],'2024-10-03')
        self.assertEqual(row['old_cusip_not_joined'],'512807108')

    def test_wrong_class_cik_cusip_context_or_action_date_rejected(self):
        for t in m.CASES:
            text,cover=fixture(t);s=m.CASES[t]
            variants=[(text.replace(s['cusip'],'000000000'),cover),(text,cover.replace(s['cik'].encode(),b'0000000001')),(text,cover+cover),(text,cover.replace(s['title'].encode(),b'Class B Common Stock'))]
            if t!='LRCX':variants.append((text.replace('Ex-Date: '+s['ex'],'Ex-Date: 1/1/2026'),cover))
            else:variants.append((text.replace('512807306','512807108'),cover))
            for a,b in variants:
                with self.subTest(ticker=t),self.assertRaises(ValueError):m.relation(t,a,b)

    def test_actual_bound_sources_read_without_publication(self):
        value=m.build()
        self.assertEqual(value['security_count'],5)
        self.assertEqual({r['ticker'] for r in value['rows']},set(m.CASES))
        self.assertTrue(all(r['latest_security_interval_verified'] is False for r in value['rows']))


if __name__=='__main__':unittest.main()
