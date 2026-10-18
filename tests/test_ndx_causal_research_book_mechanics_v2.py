"""Small explicit synthetic fixtures only; no source readers or account engines."""
from copy import deepcopy
from fractions import Fraction
import unittest
from backtest import ndx_causal_research_book_mechanics_v2 as m


def ref(role):
    return dict(path='synthetic/'+role,sha256=m.digest(role),json_pointer='')


def fixture(cash='1000'):
    names=list('ABCDE');calendar=[dict(session=d,open_at_utc=d+'T13:30:00Z',close_at_utc=d+'T20:00:00Z') for d in ('2026-10-05','2026-10-06','2026-10-07','2026-10-08')]
    scenario=dict(schema='CAUSAL_RESEARCH_SCENARIO_V1',scenario_id='fixture',currency='USD',quantity_domain='WHOLE_SHARES',book_lineage_id='book',bootstrap_policy='EXPLICIT_POSITIVE_PRIOR_CLOSE_RESEARCH',cashflow_schedule=[],calendar=calendar,lane_coordinate=dict(lane='SYNTHETIC_EXPLICIT',fx_mode='USD',lineage_kind='ONE_CHRONOLOGICAL_BOOK'),risk_policy_reference=ref('risk'),action_policy_reference=ref('action'),source_requirements=list(m.COVERAGE))
    context=dict(input_scope='SYNTHETIC_EXPLICIT',numeric_coverage=dict.fromkeys(m.COVERAGE,'DECLARED_COMPLETE'),source_references_by_role={r:ref(r) for r in m.SOURCE_ROLES},full_inventory_reference=ref('full77'),eligibility_blockers=['PIT_NOT_VERIFIED'],authority=dict(m.FLAGS))
    initial=dict(session=calendar[0]['session'],close_at_utc=calendar[0]['close_at_utc'],holdings_by_sid={s:1 for s in names},cash_usd=cash)
    state=m.bootstrap_research_book(scenario=scenario,initial_state=initial,initial_marks={s:'10' for s in names},source_context=context)['next_state']
    frame=dict(schema='CAUSAL_RESEARCH_FRAME_V1',session=calendar[1]['session'],previous_state_sha256=state['content_sha256'],identity_risk_by_sid={s:dict(issuer_id='issuer'+s,risk_chain='chain'+s) for s in names},open_prices_usd={s:'10' for s in names},close_prices_usd={s:'10' for s in names},cashflow_events=[],corporate_events=[],source_context=context,session_open_at_utc=calendar[1]['open_at_utc'],session_close_at_utc=calendar[1]['close_at_utc'])
    action=make_action(scenario,state,frame)
    return dict(scenario=scenario,previous_state=state,frame=frame,explicit_action=action)


def make_action(scenario,state,frame,status='EXPLICIT_BUY',action_id='action1'):
    baseline=dict(schema='FROZEN_PRE_EVENT_ACTION_BASELINE_V1',phase='PRIOR_CLOSE_BEFORE_FRAME_EVENTS_AND_FLOW',previous_state_sha256=state['content_sha256'],holdings_by_sid=deepcopy(state['holdings_by_sid']),cash_usd=state['cash_usd'],planned_cashflow_event_ids=sorted(f['event_id'] for f in frame['cashflow_events']))
    result=dict(schema='EXPLICIT_RESEARCH_ACTION_V1',status=status,action_id=action_id,decision_session=state['session'],decision_at_utc=state['close_at_utc'],execution_session=frame['session'],information_cutoff_utc=state['close_at_utc'],decision_state_sha256=state['content_sha256'],fill_baseline_sha256=m.digest(baseline),frozen_baseline=baseline,policy_reference=scenario['action_policy_reference'],source_references={r:dict(reference=scenario['action_policy_reference'] if r=='policy' else frame['source_context']['source_references_by_role'][r],available_at_utc=state['close_at_utc'],stage='DECISION_KNOWN_ONLY') for r in ('decision_prices','identity_risk','policy')})
    if status=='EXPLICIT_BUY':result['buy_shares']={s:1 for s in state['holdings_by_sid']}
    else:result['reason']='EXPLICIT_FIXTURE_NO_TRADE'
    return result


def resign(state):
    state['content_sha256']=m.digest({k:v for k,v in state.items() if k!='content_sha256'})


class MechanicsTests(unittest.TestCase):
    def test_oracle_five_equal_full_state_and_detached(self):
        args=fixture();before=deepcopy(args);r=m.advance_research_book(**args)
        self.assertEqual(args,before);self.assertEqual(r['action_disposition'],'ACCEPTED_EXPLICIT_BUY')
        row=r['valuation_row'];self.assertEqual((row['gross_buy_usd'],row['fees_usd'],row['cash_after_usd'],row['close_equity_usd']),('50','0.05','949.95','1049.95'))
        self.assertEqual(row['session_twr'],dict(numerator='-1',denominator='21000'))
        self.assertEqual(r['next_state']['holdings_by_sid'],dict.fromkeys('ABCDE',2));self.assertTrue(r['risk_observations']['prospective_open']['all_passed'])
        self.assertEqual(r['next_state']['applied_action_ids'],['action1']);self.assertEqual(r['readiness'],'SOURCE_BLOCKED');self.assertEqual(r['eligibility_blockers'],['PIT_NOT_VERIFIED'])
        r['next_state']['holdings_by_sid'].clear();self.assertEqual(args,before)
        self.assertEqual(m.advance_research_book(**args),m.advance_research_book(**args))

    def test_pending_is_not_zero_trade_and_no_ids_consumed(self):
        a=fixture();a['explicit_action']=dict(schema='EXPLICIT_RESEARCH_ACTION_V1',status='PENDING_ACTION_POLICY',reason='POLICY_NOT_REGISTERED',decision_session=a['previous_state']['session'],execution_session=a['frame']['session'])
        r=m.advance_research_book(**a);self.assertIsNone(r['next_state']);self.assertEqual(r['consumed_action_ids'],[]);self.assertEqual(r['consumed_event_ids'],[])
        a=fixture();a['explicit_action']=make_action(a['scenario'],a['previous_state'],a['frame'],'EXPLICIT_NO_TRADE');r=m.advance_research_book(**a)
        self.assertEqual(r['valuation_row']['session_twr'],dict(numerator='0',denominator='1'));self.assertEqual(r['next_state']['applied_action_ids'],['action1'])

    def test_flow_oracle_rejection_atomic_and_flow_once(self):
        a=fixture();flow=dict(event_id='flow1',session=a['frame']['session'],amount_usd='200',available_at_utc=a['previous_state']['close_at_utc']);a['scenario']['cashflow_schedule']=[flow]
        # Rebootstrap with the new scenario content, never hotpatch a state hash lineage.
        c=a['frame']['source_context'];initial=dict(session=a['previous_state']['session'],close_at_utc=a['previous_state']['close_at_utc'],holdings_by_sid={},cash_usd='1000')
        a['previous_state']=m.bootstrap_research_book(scenario=a['scenario'],initial_state=initial,initial_marks={},source_context=c)['next_state'];f=a['frame'];f['previous_state_sha256']=a['previous_state']['content_sha256'];f['cashflow_events']=[flow];f['open_prices_usd']={'A':'100'};f['close_prices_usd']={'A':'110'};f['identity_risk_by_sid']={'A':dict(issuer_id='issuerA',risk_chain='chainA')}
        a['explicit_action']=make_action(a['scenario'],a['previous_state'],f);a['explicit_action']['buy_shares']={'A':1}
        r=m.advance_research_book(**a);self.assertEqual(r['action_disposition'],'REJECTED_ORIGINAL_RISK');self.assertEqual(r['next_state']['cash_usd'],'1200');self.assertEqual(r['valuation_row']['fees_usd'],'0');self.assertEqual(r['next_state']['applied_event_ids'],['flow1']);self.assertEqual(r['valuation_row']['session_twr'],dict(numerator='0',denominator='1'))

    def test_split_stale_and_bad_hash_precedence(self):
        a=fixture();a['frame']['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='split1',session=a['frame']['session'],security_id='A',new_shares=2,old_shares=1)];a['frame']['open_prices_usd']['A']='5';a['frame']['close_prices_usd']['A']='5'
        r=m.advance_research_book(**a);self.assertEqual(r['action_disposition'],'REJECTED_STALE_CORPORATE_ACTION');self.assertEqual(r['next_state']['holdings_by_sid']['A'],2);self.assertEqual(r['valuation_row']['fees_usd'],'0');self.assertEqual(r['next_state']['applied_action_ids'],['action1'])
        a['explicit_action']['fill_baseline_sha256']='0'*64
        with self.assertRaises(ValueError):m.advance_research_book(**a)

    def test_critical_source_and_fractional_event_block(self):
        a=fixture();a['frame']['source_context']['numeric_coverage']['prices']='MISSING';a['frame']['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='split1',session=a['frame']['session'],security_id='A',new_shares=2,old_shares=1)]
        r=m.advance_research_book(**a);self.assertEqual(r['status'],'BLOCKED_INPUT');self.assertIsNone(r['next_state'])
        a=fixture();a['frame']['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='split1',session=a['frame']['session'],security_id='A',new_shares=1,old_shares=2)]
        self.assertIn('UNSUPPORTED_FRACTIONAL_SPLIT_ENTITLEMENT',m.advance_research_book(**a)['blockers'])
        a=fixture();a['frame']['corporate_events']=[dict(schema='UNSUPPORTED_CORPORATE_EVENT_V1',event_id='div1',session=a['frame']['session'],security_id='A',kind='CASH_DIVIDEND')]
        self.assertIsNone(m.advance_research_book(**a)['next_state'])

    def test_buffer_boundary_no_resize(self):
        self.assertEqual(m.advance_research_book(**fixture('150.05'))['next_state']['cash_usd'],'100')
        r=m.advance_research_book(**fixture('150.049'));self.assertEqual(r['action_disposition'],'REJECTED_CASH_BUFFER');self.assertEqual(r['valuation_row']['fees_usd'],'0');self.assertEqual(r['next_state']['cash_usd'],'150.049')

    def test_duplicate_action_event_kind_and_boundaries(self):
        a=fixture();completed=m.advance_research_book(**a);state=completed['next_state'];frame=deepcopy(a['frame']);frame.update(session='2026-10-07',session_open_at_utc='2026-10-07T13:30:00Z',session_close_at_utc='2026-10-07T20:00:00Z',previous_state_sha256=state['content_sha256']);action=make_action(a['scenario'],state,frame,'EXPLICIT_NO_TRADE','action1')
        with self.assertRaisesRegex(ValueError,'Duplicate action'):m.advance_research_book(scenario=a['scenario'],previous_state=state,frame=frame,explicit_action=action)
        a=fixture();flow=dict(event_id='same',session=a['frame']['session'],amount_usd='0',available_at_utc=a['previous_state']['close_at_utc']);a['scenario']['cashflow_schedule']=[flow];state=a['previous_state'];state['scenario_content_sha256']=m.digest(a['scenario']);resign(state);a['frame']['previous_state_sha256']=state['content_sha256'];a['frame']['cashflow_events']=[flow];a['explicit_action']=make_action(a['scenario'],state,a['frame']);a['frame']['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='same',session=a['frame']['session'],security_id='A',new_shares=2,old_shares=1)]
        with self.assertRaisesRegex(ValueError,'across kinds'):m.advance_research_book(**a)
        # Resource boundary is generated from a pristine genesis and explicit
        # zero flow schedule, never a forged genesis with pre-consumed IDs.
        m.ids([f'e{i:04d}' for i in range(4096)])
        with self.assertRaisesRegex(ValueError,'engineering bound'):m.ids([f'e{i:04d}' for i in range(4097)])
        for count in (4095,4096):
            a=fixture();flows=[dict(event_id=f'e{i:04d}',session=a['frame']['session'],amount_usd='0',available_at_utc=a['previous_state']['close_at_utc']) for i in range(count)];a['scenario']['cashflow_schedule']=flows
            initial=dict(session=a['previous_state']['session'],close_at_utc=a['previous_state']['close_at_utc'],holdings_by_sid=dict.fromkeys('ABCDE',1),cash_usd='1000')
            a['previous_state']=m.bootstrap_research_book(scenario=a['scenario'],initial_state=initial,initial_marks=dict.fromkeys('ABCDE','10'),source_context=a['frame']['source_context'])['next_state'];a['frame']['previous_state_sha256']=a['previous_state']['content_sha256'];a['frame']['cashflow_events']=flows;a['explicit_action']=make_action(a['scenario'],a['previous_state'],a['frame']);a['frame']['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='newid',session=a['frame']['session'],security_id='A',new_shares=2,old_shares=1)]
            if count==4095:self.assertEqual(len(m.advance_research_book(**a)['next_state']['applied_event_ids']),4096)
            else:
                with self.assertRaisesRegex(ValueError,'Cumulative event'):m.advance_research_book(**a)

    def test_causality_no_trade_and_realized_close_leak(self):
        for status in ('EXPLICIT_BUY','EXPLICIT_NO_TRADE'):
            a=fixture();a['explicit_action']=make_action(a['scenario'],a['previous_state'],a['frame'],status);a['explicit_action']['information_cutoff_utc']='2026-10-06T20:00:00Z'
            with self.assertRaises(ValueError):m.advance_research_book(**a)
        a=fixture();a['frame']['source_context']['source_references_by_role']['decision_prices']=a['frame']['source_context']['source_references_by_role']['close_prices'];a['explicit_action']=make_action(a['scenario'],a['previous_state'],a['frame'])
        with self.assertRaisesRegex(ValueError,'realized'):m.advance_research_book(**a)

    def test_types_closed_authority_hash_and_numeric_resources(self):
        for mutation in ('extra','bool','hash','authority','float'):
            a=fixture()
            if mutation=='extra':a['frame']['unknown']=ref('trap')
            elif mutation=='bool':a['explicit_action']['buy_shares']['A']=True
            elif mutation=='hash':a['previous_state']['cash_usd']='999'
            elif mutation=='authority':a['frame']['source_context']['authority']['point_in_time_verified']=True
            else:a['frame']['open_prices_usd']['A']=10.0
            with self.assertRaises(ValueError):m.advance_research_book(**a)
        for text in ('NaN','Infinity','1e40','00','0.0','1'*41):
            with self.assertRaises(ValueError):m.number(text)
        for val in ('x'*129,'x y','非ASCII'):
            with self.assertRaises(ValueError):m.identifier(val)
        with self.assertRaises(ValueError):m.utc('2026-10-05T20:00:00.000000Z')
        self.assertEqual(m.utc('2026-10-05T20:00:00.000001Z').microsecond,1)

    def test_zero_inception_and_continuous_explicitly_unsupported(self):
        a=fixture();initial=dict(session=a['scenario']['calendar'][0]['session'],close_at_utc=a['scenario']['calendar'][0]['close_at_utc'],holdings_by_sid={},cash_usd='0')
        with self.assertRaisesRegex(ValueError,'ZERO_CAPITAL'):m.bootstrap_research_book(scenario=a['scenario'],initial_state=initial,initial_marks={},source_context=a['frame']['source_context'])
        a['scenario']['quantity_domain']='CONTINUOUS'
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_QUANTITY'):m.advance_research_book(**a)

    def test_original_five_risk_observations_and_unique_issuer(self):
        a=fixture();a['frame']['identity_risk_by_sid']['B']['issuer_id']='issuerA';r=m.advance_research_book(**a);self.assertEqual(r['action_disposition'],'REJECTED_DUPLICATE_ISSUER')
        a=fixture();a['frame']['identity_risk_by_sid']={s:dict(issuer_id='issuer'+s,risk_chain='onechain') for s in 'ABCDE'};r=m.advance_research_book(**a);self.assertFalse(r['risk_observations']['prospective_open']['checks']['RISK_CHAIN_TOP1_WEIGHT'])
        identity={s:dict(issuer_id='i'+s,risk_chain='c'+s) for s in 'ABCDE'};risk=m.risk_snapshot(dict.fromkeys('ABCDE',1),dict(A=Fraction(10000),B=Fraction(1),C=Fraction(1),D=Fraction(1),E=Fraction(1)),identity)
        self.assertTrue(all(risk['checks'][k] is False for k in ('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N')))

    def test_chronological_second_step_cross_kind_action_id_and_no_mutation(self):
        a=fixture();r=m.advance_research_book(**a);state=r['next_state'];frame=deepcopy(a['frame']);frame['session']='2026-10-07';frame['session_open_at_utc']='2026-10-07T13:30:00Z';frame['session_close_at_utc']='2026-10-07T20:00:00Z';frame['previous_state_sha256']=state['content_sha256'];act=make_action(a['scenario'],state,frame,'EXPLICIT_NO_TRADE','action1')
        with self.assertRaisesRegex(ValueError,'Duplicate action'):m.advance_research_book(scenario=a['scenario'],previous_state=state,frame=frame,explicit_action=act)
        act=make_action(a['scenario'],state,frame,'EXPLICIT_NO_TRADE','action2');r2=m.advance_research_book(scenario=a['scenario'],previous_state=state,frame=frame,explicit_action=act)
        self.assertEqual(r2['next_state']['applied_action_ids'],['action1','action2']);self.assertEqual(r2['next_state']['previous_state_sha256'],state['content_sha256'])

    def test_full13_overlap_mapping_anchor_and_missing_endpoint(self):
        a=fixture();r=m.advance_research_book(**a);state=r['next_state'];cal=[x['session'] for x in a['scenario']['calendar']]
        record=dict(sequence=1,session=cal[1],previous_close_session=cal[0],previous_state_sha256=a['previous_state']['content_sha256'],state_sha256=state['content_sha256'],book_lineage_id='book',scenario_content_sha256=m.digest(a['scenario']),session_twr=r['valuation_row']['session_twr'],status='COMPUTED')
        windows=[dict(window_id=f'w{i}',fit_end='2026-10-02',evaluation_start=cal[1],evaluation_end_inclusive=cal[1]) for i in range(13)]
        mapping=dict(schema='ROLLING_BOOK_WINDOW_VIEW_MAPPING_V1',book_lineage_id='book',scenario_content_sha256=m.digest(a['scenario']),calendar=cal,terminal_boundary=None)
        result=m.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=[record],mapping_contract=mapping)
        self.assertEqual(result['window_count'],13);self.assertTrue(all(row['view_twr']==dict(numerator='-1',denominator='21000') and row['anchor_close_session']==cal[0] for row in result['rows']));self.assertFalse(result['book_execution_performed'])
        windows[0]['evaluation_end_inclusive']=cal[-1];blocked=m.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=[record],mapping_contract=mapping);self.assertEqual(len(blocked['rows']),13);self.assertIn('BLOCKED_ENDPOINT',blocked['rows'][0]['blockers'])
        record['book_lineage_id']='otherbook'
        with self.assertRaises(ValueError):m.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=[record],mapping_contract=mapping)


    def test_emitted_numeric_domain_and_mapper_factor(self):
        a=fixture();initial=dict(session=a['scenario']['calendar'][0]['session'],close_at_utc=a['scenario']['calendar'][0]['close_at_utc'],holdings_by_sid={'A':10**12},cash_usd='0')
        with self.assertRaisesRegex(ValueError,'Decimal engineering bound'):
            m.bootstrap_research_book(scenario=a['scenario'],initial_state=initial,initial_marks={'A':'9'*40},source_context=a['frame']['source_context'])
        record=dict(sequence=1,session='2026-10-06',previous_close_session='2026-10-05',previous_state_sha256='0'*64,state_sha256='1'*64,book_lineage_id='book',scenario_content_sha256=m.digest(a['scenario']),session_twr=dict(numerator='-1',denominator='1'),status='COMPUTED')
        windows=[dict(window_id=f'w{i}',fit_end='2026-10-02',evaluation_start='2026-10-06',evaluation_end_inclusive='2026-10-06') for i in range(13)]
        mapping=dict(schema='ROLLING_BOOK_WINDOW_VIEW_MAPPING_V1',book_lineage_id='book',scenario_content_sha256=m.digest(a['scenario']),calendar=['2026-10-05','2026-10-06'],terminal_boundary=dict(kind='AFTER_LAST_SAVED_MARK',ordinal=2))
        with self.assertRaisesRegex(ValueError,'Positive frame return factor'):m.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=[record],mapping_contract=mapping)


    def test_genesis_invariants_reject_coordinated_resigning(self):
        for field,value in (('applied_event_ids',['used']),('applied_action_ids',['used']),('cumulative_twr',dict(numerator='1',denominator='100')),('session','2026-10-02'),('close_at_utc','2026-10-05T19:59:59Z')):
            a=fixture();a['previous_state'][field]=value;resign(a['previous_state']);a['frame']['previous_state_sha256']=a['previous_state']['content_sha256'];a['explicit_action']=make_action(a['scenario'],a['previous_state'],a['frame'])
            with self.assertRaisesRegex(ValueError,'Genesis'):m.advance_research_book(**a)

    def test_stale_max_actual_position_skips_unexecuted_proposal_only(self):
        a=fixture();initial=dict(session=a['previous_state']['session'],close_at_utc=a['previous_state']['close_at_utc'],holdings_by_sid=dict(A=5*10**11,B=1,C=1,D=1,E=1),cash_usd='1000')
        a['previous_state']=m.bootstrap_research_book(scenario=a['scenario'],initial_state=initial,initial_marks=dict.fromkeys('ABCDE','10'),source_context=a['frame']['source_context'])['next_state'];a['frame']['previous_state_sha256']=a['previous_state']['content_sha256'];a['explicit_action']=make_action(a['scenario'],a['previous_state'],a['frame']);a['frame']['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='split1',session=a['frame']['session'],security_id='A',new_shares=2,old_shares=1)];a['frame']['open_prices_usd']['A']='5';a['frame']['close_prices_usd']['A']='5'
        r=m.advance_research_book(**a);self.assertEqual(r['action_disposition'],'REJECTED_STALE_CORPORATE_ACTION');self.assertEqual(r['next_state']['holdings_by_sid']['A'],10**12);self.assertEqual(r['valuation_row']['buy_shares'],{});self.assertEqual(r['valuation_row']['fees_usd'],'0');self.assertEqual(r['risk_observations']['prospective_open']['status'],'NOT_EVALUATED_STALE_ACTION');self.assertIsNone(r['risk_observations']['prospective_open']['all_passed'])
        malformed=deepcopy(a);malformed['explicit_action']['buy_shares']['A']=10**12+1
        with self.assertRaisesRegex(ValueError,'whole shares'):m.advance_research_book(**malformed)
        missing=deepcopy(a);missing['frame']['close_prices_usd'].pop('A');self.assertIsNone(m.advance_research_book(**missing)['next_state'])
        excessive=deepcopy(a);excessive['frame']['corporate_events'][0]['new_shares']=3
        with self.assertRaisesRegex(ValueError,'Postsplit'):m.advance_research_book(**excessive)


if __name__=='__main__':unittest.main()
