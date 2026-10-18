import copy
import unittest
from unittest.mock import patch

from scripts import ndx_pcar_cprt_conditional_identity_20260923 as m


def fixture(ticker):
    s = m.CASES[ticker]
    fields = dict(EntityCentralIndexKey=s['cik'], EntityRegistrantName=s['company'],
        TradingSymbol=ticker, Security12bTitle=s['title'], DocumentPeriodEndDate=s['period'])
    cover = ('<html>' + ''.join(f'<ix:nonNumeric name="dei:{k}" contextRef="{s["context"]}">{v}</ix:nonNumeric>' for k,v in fields.items()) + '</html>').encode()
    texts = {}
    for name,e in m.EVENTS.items():
        if e['ticker'] != ticker:
            continue
        texts[name] = (f"#{e['number']} Date: {e['publication']} "
            f"{s['memo_company']} ({ticker}) has announced a {e['new']} for {e['old']} stock split. "
            f"Ex-Date: {e['ex']} The Ex-distribution Date is {e['date_text']}. "
            f"The Payable Date is {e['payable']}. The Record Date is {e['record']}. "
            f"Effective Date:{e['date_text']} {e['deliverable']} {s['memo_company']} ({ticker}) Common Shares "
            f"CUSIP:{s['cusip']} This Information Memo provides an unofficial summary")
    return cover, texts


class IdentityTests(unittest.TestCase):
    def test_both_relations_and_distinct_dates(self):
        for ticker in m.CASES:
            result = m.relation(ticker, *fixture(ticker))
            self.assertEqual(len(result['dated_memo_facts']), 1 if ticker == 'PCAR' else 2)
            self.assertIsNone(result['risk_chain'])
            self.assertTrue(all(result[k] is False for k in m.FALSE))

    def test_wrong_context_class_cusip_and_missing_event_refused(self):
        cover, texts = fixture('CPRT')
        for bad in [cover.replace(b'0000900075', b'0000000001'), cover.replace(b'Common Stock', b'Preferred Stock'), cover.replace(m.CASES['CPRT']['context'].encode(), b'other', 1)]:
            with self.assertRaises(ValueError): m.relation('CPRT', bad, texts)
        for bad in [{next(iter(texts)): next(iter(texts.values()))}, {k:v.replace('217204106','693718108') for k,v in texts.items()}, {k:v.replace('Effective Date:', 'Deleted Date:') for k,v in texts.items()}]:
            with self.assertRaises(ValueError): m.relation('CPRT', cover, bad)

    def test_rebuilt_report_not_caller_re_signed_authority(self):
        expected = dict(source_hashes={'a':'b'}, promotion_allowed=False, rows=[m.relation('PCAR', *fixture('PCAR'))])
        with patch.object(m, 'build', return_value=expected), patch.object(m, 'verify_sources'):
            for change in ['flag','sources','risk']:
                bad=copy.deepcopy(expected)
                if change=='flag': bad['promotion_allowed']=True
                if change=='sources': bad['source_hashes']={}
                if change=='risk': bad['rows'][0]['risk_chain']='guessed'
                with self.assertRaises(ValueError): m.verify(bad)


if __name__ == '__main__': unittest.main()
