from copy import deepcopy
from datetime import datetime,timedelta
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import unittest
from core.strategy_account_ledger import canonical
import test_strategy_paper_application_descriptor_v1 as descriptor_fixture
from data.strategy_paper_application_descriptor_v1 import SCOPE
from backtest.current_strategy_prospective_paper_book_v1 import (
    CODE_PATHS,DECISION_SCHEMA,SETTLEMENT_SCHEMA,create_book,transact,replay,digest,_apply)


class ProspectiveBookTests(unittest.TestCase):
    def setUp(self):
        f=descriptor_fixture.DescriptorTests();f.setUp()
        root=Path(__file__).resolve().parents[1]
        codes={name:(root/name).read_bytes() for name in CODE_PATHS}
        f.app['code_sha256']={k:sha256(v).hexdigest() for k,v in codes.items()}
        descriptor=canonical(f.app);digest=sha256(descriptor).hexdigest()
        approval=canonical(dict(schema='PAPER_APPLICATION_REVIEW_V1',scope=SCOPE,descriptor_sha256=digest,
            approved=True,reviewed_at='2026-10-30T13:58:30+00:00',
            review_role='IMPLEMENTATION_REVIEW_OF_USER_AUTHORIZED_PAPER_SCOPE',authorization_basis='ISOLATED TEST ONLY'))
        registration=canonical(dict(schema='PROSPECTIVE_PAPER_REGISTRATION_V1',scope=SCOPE,descriptor_sha256=digest,
            account_id=f.app['account_id'],simulation_id=f.app['simulation_id'],registered_at='2026-10-30T13:59:00+00:00',
            first_session=f.plan['first_session'],terminal_session=f.plan['terminal_session'],integration_review_sha256='a'*64))
        self.authority=dict(descriptor_arguments=dict(descriptor_bytes=descriptor,trusted_descriptor_sha256=digest,
            approval_bytes=approval,trusted_approval_sha256=sha256(approval).hexdigest(),calendar_bytes=f.calendar,
            code_bytes=codes,source_bytes=f.sources),registration_bytes=registration,
            trusted_registration_sha256=sha256(registration).hexdigest(),trusted_integration_review_sha256='a'*64)
        self.book=create_book(authority=self.authority,clock=lambda:datetime.fromisoformat('2026-10-30T14:00:00+00:00'))
        self.admitted={}
        self.settlements={}

    def decision(self,book,orders=None,day='2026-10-30',effective=None):
        orders=orders or [dict(security_id='A',side='BUY',quantity=10,limit_price='100')]
        hour='14' if day=='2026-10-30' else '15'
        decision=dict(schema=DECISION_SCHEMA,scope=SCOPE,status='VERIFIED_PROSPECTIVE_PAPER_EXECUTION_DECISION',
            descriptor_sha256=book['descriptor_sha256'],registration_sha256=book['registration_sha256'],
            account_id=book['account_id'],account_revision=book['revision'],target_id='independently-reviewed-target',
            session_date=day,available_at=day+'T'+hour+':00:05+00:00',valid_until=day+'T'+hour+':01:00+00:00',
            fee_bps='1',cancel_before_recalculate=[],new_orders=orders,effective_target_quantities=effective or {'A':10})
        raw=canonical(decision);self.admitted[sha256(raw).hexdigest()]=raw
        return raw.decode()

    def apply(self,book,request,now,advance=0):
        ticks=iter([datetime.fromisoformat(now),datetime.fromisoformat(now)+timedelta(seconds=advance),
                    datetime.fromisoformat(now)+timedelta(seconds=advance*2)])
        return transact(book,request,authority=self.authority,admitted_decisions=self.admitted,
            admitted_settlements=self.settlements,current_target_id='independently-reviewed-target',clock=lambda:next(ticks))

    def settlement_request(self,book,identifier,minutes,observed):
        evidence=dict(schema=SETTLEMENT_SCHEMA,scope=SCOPE,status='VERIFIED_PROSPECTIVE_PAPER_SETTLEMENT_EVIDENCE',
            descriptor_sha256=book['descriptor_sha256'],registration_sha256=book['registration_sha256'],
            account_id=book['account_id'],account_revision=book['revision'],
            pending_orders_sha256=digest({oid:o for oid,o in book['orders'].items() if o['closed'] is None}),
            observed_through=observed,available_at=observed,minutes=minutes,
            source_review=dict(scope='PROSPECTIVE_PAPER_MINUTE_SOURCE_REVIEW_V1',receipt_sha256='b'*64,
                source_sha256={'fixture/minutes.json':digest(minutes)}))
        raw=canonical(evidence);self.settlements[sha256(raw).hexdigest()]=raw
        return dict(kind='SETTLE',operation_id=identifier,expected_revision=book['revision'],
            minutes=minutes,observed_through=observed,settlement_bytes=raw.decode())

    def accept(self,book,**kwargs):
        return self.apply(book,dict(kind='ACCEPT',operation_id='accept',expected_revision=book['revision'],
            decision_bytes=self.decision(book,**kwargs)),'2026-10-30T14:00:10+00:00',advance=.01)

    def fill(self,book):
        minutes={oid:[dict(security_id=o['security_id'],start='2026-10-30T14:01:00+00:00',
            end='2026-10-30T14:02:00+00:00',open='100',high='101',low='99',close='100')]
            for oid,o in book['orders'].items() if o['closed'] is None}
        return self.apply(book,self.settlement_request(book,'settle',minutes,'2026-10-30T14:02:00+00:00'),
            '2026-10-30T14:02:01+00:00',.1)

    def test_formal_book_server_time_accept_fill_replay_no_real_event(self):
        accepted=self.accept(self.book);filled=self.fill(accepted)
        self.assertEqual(Fraction(filled['cash']),Fraction('18999.9'))
        self.assertEqual(filled['shares'],{'A':10})
        self.assertEqual(replay(filled,authority=self.authority,admitted_decisions=self.admitted,
            admitted_settlements=self.settlements),filled)
        request=deepcopy(accepted['operations'][0]['request']);request.pop('accepted_at')
        self.assertEqual(self.apply(accepted,request,'2026-11-02T15:00:10+00:00'),accepted)
        self.assertFalse(filled['real_account'])

    def test_first_miss_and_clock_crossing_window_are_atomic(self):
        with self.assertRaisesRegex(ValueError,'INITIALIZATION_MISSED'):
            create_book(authority=self.authority,clock=lambda:datetime.fromisoformat('2026-10-30T14:01:00+00:00'))
        before=deepcopy(self.book)
        with self.assertRaisesRegex(ValueError,'ACCEPT_WINDOW'):
            self.apply(self.book,dict(kind='ACCEPT',operation_id='late',expected_revision=self.book['revision'],
                decision_bytes=self.decision(self.book)),'2026-10-30T14:00:59.900000+00:00',.2)
        self.assertEqual(self.book,before)

    def test_temporary_preview_or_unadmitted_decision_cannot_accept(self):
        raw=self.decision(self.book);self.admitted={}
        request=dict(kind='ACCEPT',operation_id='bad',expected_revision=self.book['revision'],decision_bytes=raw)
        with self.assertRaisesRegex(ValueError,'NOT_SERVER_ADMITTED'):self.apply(self.book,request,'2026-10-30T14:00:10+00:00')
        import json
        data=json.loads(raw);data['schema']='VERIFIED_PAPER_EXECUTION_PREVIEW_V1'
        data['scope']='ISOLATED_CURRENT_STRATEGY_PAPER_TEMPORARY_EXECUTION_PREVIEW_ONLY'
        wrong=canonical(data);self.admitted[sha256(wrong).hexdigest()]=wrong;request['decision_bytes']=wrong.decode()
        with self.assertRaisesRegex(ValueError,'DECISION_BINDING'):self.apply(self.book,request,'2026-10-30T14:00:10+00:00')

    def test_sale_proceeds_not_used_for_concurrent_buy(self):
        full=self.fill(self.accept(self.book,orders=[dict(security_id='A',side='BUY',quantity=199,limit_price='100')],effective={'A':199}))
        orders=[dict(security_id='A',side='SELL',quantity=199,limit_price='100'),
                dict(security_id='B',side='BUY',quantity=100,limit_price='100')]
        raw=self.decision(full,orders,day='2026-11-02',effective={'A':0,'B':100})
        before=deepcopy(full)
        with self.assertRaisesRegex(ValueError,'RESOURCE_INVARIANT'):
            self.apply(full,dict(kind='ACCEPT',operation_id='rotate',expected_revision=full['revision'],
                decision_bytes=raw),'2026-11-02T15:00:10+00:00')
        self.assertEqual(full,before)

    def test_terminal_late_settlement_remains_available_no_new_orders(self):
        accepted=self.accept(self.book)
        oid=next(iter(accepted['orders']))
        late=self.apply(accepted,self.settlement_request(accepted,'terminal',{oid:[]},'2026-11-27T18:00:00+00:00'),
            '2026-11-30T22:00:00+00:00')
        self.assertIn(late['operations'][-1]['outcome'][oid]['status'],{'UNKNOWN','EXPIRED'})
        self.assertEqual(late['cash'],'20000')
        with self.assertRaisesRegex(ValueError,'ACCEPT_WINDOW'):
            self.apply(late,dict(kind='ACCEPT',operation_id='extend',expected_revision=late['revision'],
                decision_bytes=self.decision(late,day='2026-12-01')),'2026-12-01T15:00:10+00:00')

    def test_final_third_clock_crosses_deadline_without_commit(self):
        raw=self.decision(self.book)
        ticks=iter(map(datetime.fromisoformat,['2026-10-30T14:00:59.8+00:00',
            '2026-10-30T14:00:59.9+00:00','2026-10-30T14:01:00+00:00']))
        before=deepcopy(self.book)
        with self.assertRaisesRegex(ValueError,'FINAL_ACCEPT_DEADLINE'):
            transact(self.book,dict(kind='ACCEPT',operation_id='race',expected_revision=self.book['revision'],
                decision_bytes=raw),authority=self.authority,admitted_decisions=self.admitted,
                current_target_id='independently-reviewed-target',clock=lambda:next(ticks))
        self.assertEqual(self.book,before)

    def test_current_target_and_book_tamper_are_rejected(self):
        raw=self.decision(self.book)
        with self.assertRaisesRegex(ValueError,'CURRENT_TARGET_CHANGED'):
            transact(self.book,dict(kind='ACCEPT',operation_id='oldtarget',expected_revision=self.book['revision'],
                decision_bytes=raw),authority=self.authority,admitted_decisions=self.admitted,
                current_target_id='newly-published-target',clock=lambda:datetime.fromisoformat('2026-10-30T14:00:10+00:00'))
        filled=self.fill(self.accept(self.book));filled['cash']='999999'
        with self.assertRaisesRegex(ValueError,'BOOK_REPLAY'):
            replay(filled,authority=self.authority,admitted_decisions=self.admitted,
                   admitted_settlements=self.settlements)

    def test_settlement_server_admission_binding_tamper_and_replay(self):
        import json
        accepted=self.accept(self.book);oid=next(iter(accepted['orders']))
        request=self.settlement_request(accepted,'audit',{oid:[]},'2026-10-30T14:02:00+00:00')
        original=deepcopy(accepted);raw=request['settlement_bytes'].encode()
        self.settlements={}
        with self.assertRaisesRegex(ValueError,'NOT_SERVER_ADMITTED'):
            self.apply(accepted,request,'2026-10-30T14:02:01+00:00')
        self.settlements[sha256(raw).hexdigest()]=raw
        changed=deepcopy(request);changed['observed_through']='2026-10-30T14:03:00+00:00'
        with self.assertRaisesRegex(ValueError,'INPUT_CHANGED'):
            self.apply(accepted,changed,'2026-10-30T14:03:01+00:00')
        for field,value in [('account_id','paper-current:other-account'),('account_revision','wrong'),
                            ('pending_orders_sha256','0'*64)]:
            evidence=json.loads(raw);evidence[field]=value;bad=canonical(evidence)
            self.settlements[sha256(bad).hexdigest()]=bad
            changed=deepcopy(request);changed['settlement_bytes']=bad.decode()
            with self.assertRaises(ValueError):self.apply(accepted,changed,'2026-10-30T14:02:01+00:00')
        self.assertEqual(accepted,original)
        settled=self.apply(accepted,request,'2026-10-30T14:02:01+00:00',.01)
        self.assertEqual(self.apply(settled,request,'2026-10-30T14:04:00+00:00'),settled)
        self.settlements.pop(sha256(raw).hexdigest())
        with self.assertRaisesRegex(ValueError,'NOT_SERVER_ADMITTED'):
            replay(settled,authority=self.authority,admitted_decisions=self.admitted,admitted_settlements=self.settlements)


    def test_duplicate_operation_cannot_overwrite_order_during_replay(self):
        accepted=self.accept(self.book);before=deepcopy(accepted)
        request=dict(kind='ACCEPT',operation_id='accept',expected_revision=accepted['revision'],
            accepted_at='2026-10-30T14:00:20+00:00',decision_bytes=self.decision(accepted,
                [dict(security_id='B',side='BUY',quantity=1,limit_price='100')],effective={'B':1}))
        with self.assertRaisesRegex(ValueError,'OPERATION_ID_REUSE'):
            _apply(accepted,request,self.authority,self.admitted,self.settlements)
        self.assertEqual(accepted,before)
        forged=deepcopy(accepted)
        forged['operations'].append(dict(request=request,outcome={},revision='forged'))
        with self.assertRaisesRegex(ValueError,'OPERATION_ID_REUSE'):
            replay(forged,authority=self.authority,admitted_decisions=self.admitted)

    def test_incomplete_batch_preserves_resources_and_watermark_then_recovers(self):
        accepted=self.accept(self.book,orders=[dict(security_id=s,side='BUY',quantity=10,limit_price='100')
                                              for s in ('A','B')],effective={'A':10,'B':10})
        ids=list(accepted['orders'])
        bar=dict(security_id='A',start='2026-10-30T14:01:00+00:00',end='2026-10-30T14:02:00+00:00',
                 open='100',high='101',low='99',close='100')
        unknown=self.apply(accepted,self.settlement_request(accepted,'incomplete',
            {ids[0]:[bar],ids[1]:[]},'2026-10-30T14:02:00+00:00'),'2026-10-30T14:02:01+00:00',.01)
        self.assertEqual(unknown['cash'],accepted['cash'])
        self.assertEqual(unknown['shares'],accepted['shares'])
        self.assertEqual(unknown['orders'],accepted['orders'])
        self.assertEqual(unknown['last_observed_at'],accepted['last_observed_at'])
        self.assertTrue(all(v['status']=='UNKNOWN' for v in unknown['operations'][-1]['outcome'].values()))
        recovered=self.fill(unknown)
        self.assertEqual(recovered['shares'],{'A':10,'B':10})
        self.assertEqual(recovered['last_observed_at'],'2026-10-30T14:02:00+00:00')

    def test_complete_no_cross_day_expires_and_releases_reserved_cash(self):
        accepted=self.accept(self.book);oid=next(iter(accepted['orders']))
        start=datetime.fromisoformat('2026-10-30T14:01:00+00:00')
        bars=[dict(security_id='A',start=(start+timedelta(minutes=i)).isoformat(),
                   end=(start+timedelta(minutes=i+1)).isoformat(),open='100',high='101',low='100',close='100')
              for i in range(359)]
        expired=self.apply(accepted,self.settlement_request(accepted,'expiry',{oid:bars},
            '2026-10-30T20:00:00+00:00'),'2026-10-30T20:00:01+00:00',.01)
        self.assertEqual(expired['orders'][oid]['closed'],'EXPIRED')
        self.assertEqual(expired['cash'],'20000')
        self.assertEqual(expired['shares'],{})
        self.assertEqual(expired['last_observed_at'],'2026-10-30T20:00:00+00:00')


if __name__=='__main__':unittest.main()
