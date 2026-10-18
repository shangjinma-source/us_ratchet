import copy
import unittest
from unittest.mock import patch
from test_ndx_fixed_control_accounting_independent_audit_research import fixture
from scripts import ndx_single_window_control_raw_recovery_20260923 as m


def receipts():
    args=fixture();ledger=args['execution']
    ledger['daily'][0]['risk']={'all_passed':False,'checks':{'ALL_CASH':False}}
    labels=args['schedule'][0]['targets'];columns={s:'SID_'+s for s in labels}
    selected=dict(original_schedule=args['schedule'],columns=columns,labels=labels,prices=args['prices'],arguments=dict(risk_chains_by_decision=args['risk_chains_by_decision']))
    state=dict(selected=selected,calendar=args['calendar'],contract=args['contract'],independent_target_audit_reference={},historical_expected_source_hashes={'required':'a'*64})
    rawledger=copy.deepcopy(ledger)
    for row in rawledger['decisions']:
        for sid,target in row['targets'].items():target['ticker']=columns[sid]
    for row in rawledger['trades']:row['ticker']=columns[row['security_id']]
    for row in rawledger['daily']:row['tickers']={s:columns[s] for s in row['shares']}
    marker=dict(schema='HISTORICAL_SINGLE_WINDOW_ACCOUNT_ATTEMPT_V1',track='incumbent',attempt_count=1,prepared_sha256=m.original.digest(state),input_reference=m.original.INPUT,target_reference=m.original.TARGET,independent_target_audit_reference={})
    raw=dict(schema='HISTORICAL_SINGLE_WINDOW_RAW_EXECUTION_V1',track='incumbent',execution=rawledger,started_reference=m.REFS['started'],original_schedule=args['schedule'],internal_columns=columns,calendar=args['calendar'],execution_contract=args['contract'],independent_accounting_completed=False,**dict.fromkeys(m.original.FALSE,False))
    failure=dict(schema='HISTORICAL_SINGLE_WINDOW_FAILED_ATTEMPT_V1',track='incumbent',started_reference=m.REFS['started'],raw_execution_reference=m.REFS['raw'],engine_call_started=True,error_type='ValueError',automatic_retry_allowed=False,failure_is_economic_infeasibility=False,**dict.fromkeys(m.original.FALSE,False))
    return state,raw,marker,failure,ledger


class RecoveryReview(unittest.TestCase):
    def test_only_labels_restore_with_raw_preserved_and_no_engine(self):
        state,raw,started,failure,ledger=receipts();before=copy.deepcopy(raw)
        with patch.object(m.original.control,'simulate_dynamic_frozen_incumbent_control',side_effect=AssertionError('engine forbidden')) as engine:
            restored,audit=m.inspect_receipts(state,raw,started,failure)
        self.assertTrue(m.exact(restored,ledger));self.assertTrue(m.exact(raw,before));engine.assert_not_called()
        self.assertTrue(audit['filled']);self.assertFalse(audit['risk_is_order_gate'])

    def test_cash_marker_source_failure_scope_mutations_rejected(self):
        for defect in ('cash','source','marker','failure','scope','raw_label'):
            state,raw,started,failure,_=receipts()
            if defect=='cash':raw['execution']['daily'][2]['cash_usd']+=1
            elif defect=='source':state['historical_expected_source_hashes'].clear()
            elif defect=='marker':started['attempt_count']=True
            elif defect=='failure':failure['automatic_retry_allowed']=True
            elif defect=='scope':raw['promotion_allowed']=True
            else:raw['execution']['trades'][0]['ticker']='FORGED'
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect_receipts(state,raw,started,failure)

    def test_publisher_rebuild_rejects_resigned_sources_or_authority(self):
        original=dict(schema='HISTORICAL_SINGLE_WINDOW_CONDITIONAL_ACCOUNT_RAW_RECOVERY_V2',historical_expected_source_hashes={'required':'a'*64},archive_resolution={},execution_replayed=False,promotion_allowed=False)
        for defect in ('source','replayed','scope'):
            altered=copy.deepcopy(original)
            if defect=='source':altered['historical_expected_source_hashes'].clear()
            elif defect=='replayed':altered['execution_replayed']=True
            else:altered['promotion_allowed']=True
            with self.subTest(defect=defect),patch.object(m,'build',return_value=original),patch.object(m.original,'exclusive_publish') as publish:
                with self.assertRaises(ValueError):m.publish_verified(altered)
                publish.assert_not_called()


if __name__=='__main__':unittest.main()
