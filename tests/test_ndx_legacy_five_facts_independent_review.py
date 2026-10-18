"""No publication; adversarial cover and dated-evidence boundary tests."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import test_ndx_legacy_five_dated_facts_20260923 as fixtures

m=fixtures.subject


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blobs={key:(m.ROOT/path).read_bytes() for key,(path,sha) in m.BOUND.items()}

    def test_conflicting_cover_and_wrong_class_do_not_link(self):
        raw=self.blobs['TEAM_cover']
        conflict=raw+b'<ix:nonNumeric name="dei:TradingSymbol">OTHER</ix:nonNumeric>'
        with self.assertRaises(ValueError):m.cover_context(conflict,'TEAM')
        html=''.join('<ix:nonNumeric name="dei:'+key+'">'+value+'</ix:nonNumeric>' for key,value in {
            'EntityCentralIndexKey':'0001650372','TradingSymbol':'TEAM','EntityRegistrantName':'Atlassian',
            'Security12bTitle':'Class B Common Stock','DocumentPeriodEndDate':'2022-09-30'}.items())
        with self.assertRaises(ValueError):m.cover_context(html.encode(),'TEAM')

    def test_duplicate_adi_transcription_and_changed_accession_reject(self):
        for attack in ('duplicate','accession'):
            blobs=dict(self.blobs)
            if attack=='duplicate':
                doc=json.loads(blobs['adi_transcription']);doc['rows'].append(deepcopy(next(r for r in doc['rows'] if r['ticker']=='ADI')))
                blobs['adi_transcription']=json.dumps(doc).encode()
            else:
                doc=json.loads(blobs['adi_readback']);next(r for r in doc['rows'] if r['ticker']=='ADI')['accession']='other'
                blobs['adi_readback']=json.dumps(doc).encode()
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(blobs)

    def test_publisher_rejects_permission_and_reporter_subject_upgrade_before_mkdir(self):
        original=m.assemble(self.blobs);original['source_hashes']={}
        for attack in ('permission','subject'):
            bad=deepcopy(original)
            if attack=='permission':bad['promotion_allowed']=True
            else:next(r for r in bad['rows'] if r['ticker']=='TEAM')['subject_cik']='0001357550'
            with self.subTest(attack=attack),patch.object(m,'build',return_value=original),patch.object(m.Path,'mkdir') as mkdir:
                with self.assertRaises(ValueError):m.publish(bad)
                mkdir.assert_not_called()

    def test_table_columns_not_quote_and_unknown_clocks_stay_unknown(self):
        value=m.assemble(self.blobs);rows={r['ticker']:r for r in value['rows']}
        for ticker in ('DDOG','TEAM'):
            row=rows[ticker]
            self.assertEqual(row['excerpts'][0]['extraction'],'SELECTED_TABLE_COLUMNS_NOT_CONTIGUOUS_QUOTE')
            self.assertNotIn('verbatim_value',row['excerpts'][0])
            self.assertIsNone(row['event_date']);self.assertEqual(row['report_period'],'2022-12-31')
            self.assertFalse(row['subject_cik_directly_in_cusip_document'])
        for ticker in ('QCOM','TXN','DDOG','TEAM'):
            self.assertEqual(rows[ticker]['tool_call_started_utc'],'unknown')
            self.assertFalse(rows[ticker]['full_tool_response_preserved'])
            self.assertIsNone(rows[ticker]['continuous_identity_interval'])


if __name__=='__main__':unittest.main()
