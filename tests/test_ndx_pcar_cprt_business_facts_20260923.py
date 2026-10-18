import copy
import unittest
from unittest.mock import patch

from scripts import ndx_pcar_cprt_business_facts_20260923 as m


def fixture(ticker):
    s=m.identity.CASES[ticker]
    fields={'EntityCentralIndexKey':s['cik'],'EntityRegistrantName':s['company'],
        'TradingSymbol':ticker,'DocumentPeriodEndDate':s['period'],'Security12bTitle':s['title']}
    raw='<html>'+''.join(f'<ix:nonNumeric name="dei:{k}" contextRef="{s["context"]}">{v}</ix:nonNumeric>' for k,v in fields.items())
    if ticker=='CPRT':raw+='<p>Item 1. Business Corporate Information</p>'
    for clause in m.CLAUSES[ticker]:
        raw+='<p>'+clause+(' source company. PACCAR competes in the North American' if ticker=='PCAR' and not clause.endswith('.') else ' source markets. Our goals are to generate' if not clause.endswith('.') else '')+'</p>'
    if ticker=='CPRT':raw+='<p>Item 1A. Risk Factors</p>'
    return (raw+'</html>').encode()


class BusinessTests(unittest.TestCase):
    def test_actual_original_build_no_publication(self):
        report=m.build()
        self.assertEqual([r['ticker'] for r in report['rows']],['PCAR','CPRT'])
        self.assertEqual(report['rows'][1]['candidate_risk_chains'],['internet_ecommerce','automotive','industrial'])
        for row in report['rows']:
            self.assertIsNone(row['assigned_risk_chain'])
            self.assertTrue(all(row[k] is False for k in m.FALSE))

    def test_context_and_missing_business_clause_refused(self):
        for ticker in m.CLAUSES:
            raw=fixture(ticker)
            self.assertEqual(m.extract(ticker,raw)['ticker'],ticker)
            for bad in [raw.replace(m.CLAUSES[ticker][0].encode(),b'unsupported'),raw.replace(b'contextRef=',b'wrongRef=',1)]:
                with self.assertRaises(ValueError):m.extract(ticker,bad)

    def test_publisher_rejects_assignment_scope_and_source_edits(self):
        value={'source_hashes':{'a':'b'},'risk_chain_assigned':False,'rows':[]}
        with patch.object(m,'build',return_value=value),patch.object(m,'verify_sources'):
            for key,new in [('risk_chain_assigned',True),('source_hashes',{}),('rows',[{'assigned_risk_chain':'automotive'}])]:
                bad=copy.deepcopy(value);bad[key]=new
                with self.assertRaises(ValueError):m.verify(bad)


if __name__=='__main__':unittest.main()
