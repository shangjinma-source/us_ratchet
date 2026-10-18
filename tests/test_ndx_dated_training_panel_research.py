"""Synthetic 77-column training isolation; no actual prepared payload or fit."""
from copy import deepcopy
from datetime import date,timedelta
import unittest
from backtest import ndx_dated_training_panel_research as m


def fixture():
    def weekdays(first,last):
        d=date.fromisoformat(first);out=[]
        while d<=date.fromisoformat(last):
            if d.weekday()<5:out.append(d.isoformat())
            d+=timedelta(days=1)
        return out
    a=weekdays('2025-09-18','2026-03-20');b=weekdays('2026-03-23','2026-09-21');days=a[:126]+[a[-1]]+b[:125]+[b[-1]]
    parent=dict(path='panel.json',sha256='a'*64);channels=dict(path='channels.json',sha256='b'*64);audit=dict(path='audit.json',sha256='c'*64)
    source=dict(schema='BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1',security_count=77,issuer_count=76,observed_security_count=101,conditional_numeric_channel_count=77,blocked_price_channel_count=0,calendar253=days,training_freeze_close_date=days[126],evaluation_first_return_date=days[127],evaluation_interval_previously_used_for_fitting=True,future_independent_oos=False,untouched_holdout=False,input_references=dict(panel=parent),original_identity_assumed_window=dict(first='2026-03-20',last='2026-09-21'),original_provenance_and_missing=[dict(ticker='T'+str(i).zfill(3),original=True) for i in range(101)],preserved_evidence_sidecars={k:{'old':k} for k in m.SIDECARS},preserved_sidecar_references={k:dict(parent,json_pointer='/'+k) for k in m.SIDECARS},evaluation_prior_fit_overlap_evidence={'oldfit':True},rows=[])
    source.update({k:False for k in ('point_in_time_verified','execution_authorized','promotion_allowed','legal_training_input_admitted','fit_performed','historical_identity_verified','historical_risk_verified','identity_interval_extended')})
    for i in range(77):
        ticker='T'+str(i).zfill(3);coordinate=dict(ticker=ticker,security_id='S'+str(i).zfill(3),issuer_id='I'+str(max(1,i)).zfill(3),risk_chain='CHAIN',median_dollar_volume_usd=999999)
        returns=[dict(previous_session=days[j],session=days[j+1],split_only_return_exact='1/100',split_only_return_float=.01,dividends_included=False) for j in range(252)]
        channel=dict(schema='BULK_LONG_WINDOW_CONDITIONAL_CHANNEL_V1',ticker=ticker,status='CONDITIONAL_NUMERIC_RESULT',reasons=[],calendar=days,training_freeze_close_date=days[126],evaluation_initial_close_date=days[126],training_returns=returns[:126],evaluation_returns=returns[126:],return_rows=returns,training_returns_sha256=m.digest(returns[:126]),evaluation_returns_sha256=m.digest(returns[126:]))
        channel.update({k:False for k in ('source_bytes_authenticated','provider_price_unit_verified','identity_interval_verified','point_in_time_verified','legal_training_input_admitted','execution_authorized','fit_performed')})
        source['rows'].append(dict(coordinate=coordinate,channel=channel,original_identity_assumed_window=deepcopy(source['original_identity_assumed_window'])))
    return dict(channels_document=source,channels_reference=channels,independent_readback_reference=audit,parent_panel_reference=parent)


class TrainingTests(unittest.TestCase):
    def test_full_training_dates_mapping_and_evaluation_references(self):
        args=fixture();before=deepcopy(args);out=m.prepare_dated_training_panel(**args);self.assertEqual(args,before)
        frame=out['fit_payload']['returns'];self.assertEqual(len(frame['data']),126);self.assertEqual(len(frame['columns']),77);self.assertEqual(frame['index'][-1],'2026-03-20T00:00:00')
        self.assertEqual(out['numeric_conversion_evidence'][0]['rows'][0]['float_hex'],(.01).hex())
        self.assertNotIn('evaluation_returns',out['fit_payload']);self.assertEqual(out['evaluation_references'][0]['return_end_dates'][0],'2026-03-23')
        self.assertTrue(all(set(r)=={'ticker','issuer_id','risk_chain'} for r in out['fit_payload']['selected_by_security'].values()))
        self.assertEqual(len(out['original_provenance_and_missing']),101);self.assertEqual(out['preserved_evidence_sidecars'],args['channels_document']['preserved_evidence_sidecars'])

    def test_future_mdv_never_changes_fit_payload(self):
        args=fixture();old=m.prepare_dated_training_panel(**args);args['channels_document']['rows'][0]['coordinate']['median_dollar_volume_usd']=1e99
        new=m.prepare_dated_training_panel(**args);self.assertEqual(old['fit_payload_sha256'],new['fit_payload_sha256']);self.assertNotEqual(old['original_coordinate_evidence'],new['original_coordinate_evidence']);self.assertFalse(new['liquidity_qualification_at_training_cutoff_verified'])

    def test_dates_float_and_false_attacks(self):
        changes=[lambda s:s['rows'][0]['channel']['training_returns'][0].update(split_only_return_float=True),lambda s:s['rows'][0]['channel']['training_returns'][0].update(split_only_return_float=.02),lambda s:s['rows'][0]['channel']['training_returns'][-1].update(session='2026-03-23'),lambda s:s.update(point_in_time_verified=0),lambda s:s.update(security_count=True),lambda s:s['rows'][1]['coordinate'].update(ticker='T000'),lambda s:s['preserved_evidence_sidecars'].pop(m.SIDECARS[-1])]
        for change in changes:
            with self.subTest(change=change):
                args=fixture();change(args['channels_document'])
                # Re-sign changed row payload to test deeper type/date gates.
                c=args['channels_document']['rows'][0]['channel'];c['training_returns_sha256']=m.digest(c['training_returns'])
                with self.assertRaises(ValueError):m.prepare_dated_training_panel(**args)

    def test_same_issuer_singletons_and_schema_authority(self):
        out=m.prepare_dated_training_panel(**fixture());self.assertEqual(set(m.selected_mapping_dated(out,['S000'])),{'S000'})
        with self.assertRaises(ValueError):m.selected_mapping_dated(out,['S000','S001'])
        with self.assertRaises(ValueError):m.selected_mapping_dated(out,['S003','S002'])
        bad=deepcopy(out);bad['promotion_allowed']=True;bad['content_sha256']=m.digest({k:v for k,v in bad.items() if k!='content_sha256'})
        with self.assertRaises(ValueError):m.selected_mapping_dated(bad,['S002'])
        bad=deepcopy(out);bad['schema']='OLD_PANEL';bad['content_sha256']=m.digest({k:v for k,v in bad.items() if k!='content_sha256'})
        with self.assertRaises(ValueError):m.selected_mapping_dated(bad,['S002'])

if __name__=='__main__':unittest.main()
