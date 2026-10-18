"""Synthetic producer fixtures; reconstruction itself has no producer dependency."""
from copy import deepcopy
from fractions import Fraction
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_causal_book_independent_reconstruction_v1 as reader
from backtest import ndx_causal_research_book_mechanics_v2 as producer
from test_ndx_causal_research_book_mechanics_v2 import fixture, make_action


def resign(obj):
    obj['content_sha256']=reader.fingerprint({k:v for k,v in obj.items() if k!='content_sha256'})


def path_fixture(nontrivial=False,buy=False):
    setup=fixture('100' if nontrivial else '1000'); scenario=deepcopy(setup['scenario']); context=deepcopy(setup['frame']['source_context'])
    dates=['2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09']
    scenario['calendar']=[dict(session=d,open_at_utc=d+'T13:30:00Z',close_at_utc=d+'T20:00:00Z') for d in dates]
    injections=['20','0','30','5'] if nontrivial else ['100','0','0','50']
    scenario['cashflow_schedule']=[dict(event_id='flow'+str(i),session=dates[i],amount_usd=value,available_at_utc=dates[i-1]+'T20:00:00Z') for i,value in enumerate(injections,1) if value!='0']
    initial=dict(session=dates[0],close_at_utc=dates[0]+'T20:00:00Z',holdings_by_sid=dict.fromkeys('ABCDE',1),cash_usd='100' if nontrivial else '1000')
    marks=dict.fromkeys('ABCDE','10'); boot=producer.bootstrap_research_book(scenario=scenario,initial_state=initial,initial_marks=marks,source_context=context)
    previous=boot['next_state']; frames=[]; actions=[]; transitions=[]; timeline=[]
    for i in range(1,5):
        op,cl=[('12','11'),('9','10'),('11','8'),('10','13')][i-1] if nontrivial else ('10','10')
        frame=dict(schema='CAUSAL_RESEARCH_FRAME_V1',session=dates[i],previous_state_sha256=previous['content_sha256'],identity_risk_by_sid={sid:dict(issuer_id='issuer'+sid,risk_chain='chain'+sid) for sid in 'ABCDE'},open_prices_usd=dict.fromkeys('ABCDE',op),close_prices_usd=dict.fromkeys('ABCDE',cl),cashflow_events=[f for f in scenario['cashflow_schedule'] if f['session']==dates[i]],corporate_events=[],source_context=deepcopy(context),session_open_at_utc=dates[i]+'T13:30:00Z',session_close_at_utc=dates[i]+'T20:00:00Z')
        if not nontrivial and i==2:
            frame['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='split2',session=dates[i],security_id='A',new_shares=2,old_shares=1)]
            frame['open_prices_usd']['A']=frame['close_prices_usd']['A']='5'
        if not nontrivial and i>2: frame['open_prices_usd']['A']=frame['close_prices_usd']['A']='5'
        status='EXPLICIT_BUY' if buy and i<3 else 'EXPLICIT_NO_TRADE'
        action=make_action(scenario,previous,frame,status,'action'+str(i))
        result=producer.advance_research_book(scenario=scenario,previous_state=previous,frame=frame,explicit_action=action)
        frames.append(frame); actions.append(action); transitions.append(result)
        timeline.append(dict(sequence=i,session=dates[i],previous_close_session=dates[i-1],previous_state_sha256=previous['content_sha256'],state_sha256=result['next_state']['content_sha256'],book_lineage_id=scenario['book_lineage_id'],scenario_content_sha256=producer.digest(scenario),session_twr=result['valuation_row']['session_twr'],status='COMPUTED'))
        previous=result['next_state']
    pairs=[(1,2),(1,3),(1,4),(1,5),(2,3),(2,4),(2,5),(3,4),(3,5),(4,5),(1,2),(2,4),(1,5)]
    windows=[dict(window_id='w'+str(i),fit_end=dates[a-1],evaluation_start=dates[a],evaluation_end_inclusive=dates[b-1]) for i,(a,b) in enumerate(pairs)]
    mapping=dict(schema='ROLLING_BOOK_WINDOW_VIEW_MAPPING_V1',book_lineage_id=scenario['book_lineage_id'],scenario_content_sha256=producer.digest(scenario),calendar=dates,terminal_boundary=dict(kind='AFTER_LAST_SAVED_MARK',ordinal=5))
    views=producer.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=timeline,mapping_contract=mapping)
    return dict(scenario=scenario,initial_state=initial,initial_marks=marks,initial_source_context=context,frames=frames,explicit_actions=actions,saved_bootstrap=boot,saved_transitions=transitions,window_coordinates=windows,mapping_contract=mapping,saved_views=views)


def single_frame(args):
    scenario=args['scenario']; frame=args['frame']; prior=args['previous_state']; context=frame['source_context']
    initial=dict(session=prior['session'],close_at_utc=prior['close_at_utc'],holdings_by_sid=prior['holdings_by_sid'],cash_usd=prior['cash_usd'])
    boot=producer.bootstrap_research_book(scenario=scenario,initial_state=initial,initial_marks=dict.fromkeys(initial['holdings_by_sid'],'10'),source_context=context)
    # These fixture changes are explicit scenario inputs, not edits to saved
    # states. Re-freeze the action against the new genesis when inputs changed.
    frame['previous_state_sha256']=boot['next_state']['content_sha256']
    action=make_action(scenario,boot['next_state'],frame,args['explicit_action']['status'])
    if action['status']=='EXPLICIT_BUY': action['buy_shares']=args['explicit_action']['buy_shares']
    result=producer.advance_research_book(scenario=scenario,previous_state=boot['next_state'],frame=frame,explicit_action=action)
    windows=[dict(window_id='single'+str(i),fit_end=initial['session'],evaluation_start=frame['session'],evaluation_end_inclusive=frame['session']) for i in range(13)]
    mapping=dict(schema='ROLLING_BOOK_WINDOW_VIEW_MAPPING_V1',book_lineage_id=scenario['book_lineage_id'],scenario_content_sha256=producer.digest(scenario),calendar=[c['session'] for c in scenario['calendar']],terminal_boundary=None)
    timeline=[]
    if result['next_state'] is not None:
        timeline=[dict(sequence=1,session=frame['session'],previous_close_session=initial['session'],previous_state_sha256=boot['next_state']['content_sha256'],state_sha256=result['next_state']['content_sha256'],book_lineage_id=scenario['book_lineage_id'],scenario_content_sha256=producer.digest(scenario),session_twr=result['valuation_row']['session_twr'],status='COMPUTED')]
    return dict(scenario=scenario,initial_state=initial,initial_marks=dict.fromkeys(initial['holdings_by_sid'],'10'),initial_source_context=context,frames=[frame],explicit_actions=[action],saved_bootstrap=boot,saved_transitions=[result],window_coordinates=windows,mapping_contract=mapping,saved_views=producer.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=timeline,mapping_contract=mapping))


class IndependentTests(unittest.TestCase):
    def test_derived_open_notional_does_not_gain_source_decimal_bound(self):
        args=fixture(); args['previous_state']['holdings_by_sid']=dict.fromkeys('ABCDE',10**12)
        args['explicit_action']['status']='EXPLICIT_NO_TRADE'; args['frame']['open_prices_usd']=dict.fromkeys('ABCDE','1'+'0'*39)
        report=reader.inspect_saved_book(**single_frame(args))
        self.assertGreater(len(report['transitions'][0]['valuation_row']['pre_flow_open_equity_usd']),40)

    def test_exact_buffer_and_all_five_risk_math_rejections(self):
        for cash,expected in [('150.05','ACCEPTED_EXPLICIT_BUY'),('150.049','REJECTED_CASH_BUFFER')]:
            report=reader.inspect_saved_book(**single_frame(fixture(cash)))
            self.assertEqual(report['transitions'][0]['action_disposition'],expected)
            self.assertEqual(report['transitions'][0]['next_state']['cash_usd'],'100' if expected.startswith('ACCEPTED') else cash)
        cases=[([92,27,27,27,27],'MAX_SINGLE_WEIGHT'),([42,18,18,18,4],'MIN_SINGLE_WEIGHT'),([30,30,30,5,5],'SECURITY_TOP3_WEIGHT'),([45,35,10,5,5],'MINIMUM_EFFECTIVE_N')]
        for quantities,check in cases:
            args=fixture('100000'); args['explicit_action']['buy_shares']={sid:q-1 for sid,q in zip('ABCDE',quantities)}
            report=reader.inspect_saved_book(**single_frame(args)); transition=report['transitions'][0]
            self.assertFalse(transition['risk_observations']['prospective_open']['checks'][check]); self.assertEqual(transition['action_disposition'],'REJECTED_ORIGINAL_RISK'); self.assertEqual(transition['valuation_row']['fees_usd'],'0')
        args=fixture()
        for row in args['frame']['identity_risk_by_sid'].values(): row['risk_chain']='shared'
        result=reader.inspect_saved_book(**single_frame(args))['transitions'][0]
        self.assertFalse(result['risk_observations']['prospective_open']['checks']['RISK_CHAIN_TOP1_WEIGHT'])

    def test_actual_maximum_split_stale_avoids_unexecuted_postbuy_cap(self):
        args=fixture(); args['previous_state']['holdings_by_sid']['A']=5*10**11
        frame=args['frame']; frame['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='maxsplit',session=frame['session'],security_id='A',new_shares=2,old_shares=1)]; frame['open_prices_usd']['A']=frame['close_prices_usd']['A']='5'
        report=reader.inspect_saved_book(**single_frame(args)); result=report['transitions'][0]
        self.assertEqual(result['next_state']['holdings_by_sid']['A'],10**12); self.assertEqual(result['valuation_row']['fees_usd'],'0')
        self.assertEqual(result['risk_observations']['prospective_open']['status'],'NOT_EVALUATED_STALE_ACTION')
        self.assertEqual(result['action_disposition'],'REJECTED_STALE_CORPORATE_ACTION')

    def test_zero_capital_and_fractional_event_typed_block(self):
        args=path_fixture(True); args['initial_state']['cash_usd']='0'; args['initial_state']['holdings_by_sid']={}; args['initial_marks']={}
        with self.assertRaisesRegex(ValueError,'ZERO_CAPITAL'): reader.inspect_saved_book(**args)
        args=fixture(); frame=args['frame']; frame['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='fractional',session=frame['session'],security_id='A',new_shares=1,old_shares=2)]
        report=reader.inspect_saved_book(**single_frame(args)); self.assertIn('UNSUPPORTED_FRACTIONAL_SPLIT_ENTITLEMENT',report['transitions'][0]['blockers'])

    def test_complete_nontrivial_full13_hand_oracle_and_seven_later_anchors(self):
        args=path_fixture(True); original=deepcopy(args)
        oracle=json.loads((Path(__file__).resolve().parents[1]/'tmp/causal_book_nontrivial_view_oracle_c_20261009_v1/ORACLE.json').read_text(encoding='utf-8'))
        report=reader.inspect_saved_book(**args)
        for actual,manual in zip(report['transitions'],oracle['frames']):
            row=actual['valuation_row']
            for key,manual_key in [('previous_close_equity_usd','previous_close_equity'),('pre_flow_open_equity_usd','pre_flow_open_equity'),('cash_injection_usd','cashflow'),('close_equity_usd','close_equity'),('cash_after_usd','cash_after')]:
                self.assertEqual(Fraction(row[key]),Fraction(int(manual[manual_key]['numerator']),int(manual[manual_key]['denominator'])))
        for actual,manual in zip(report['views']['rows'],oracle['views']):
            self.assertEqual(actual['view_twr'],manual['correct_twr'])
            for wrong in ('wrong_drop_first_overnight','wrong_drop_first_return','wrong_drop_last_return'):
                self.assertNotEqual(actual['view_twr'],manual[wrong])
        later=[v for v in oracle['views'] if v['subtraction_is_detectable']]
        self.assertEqual(len(later),7)
        for manual in later:
            bad=deepcopy(args); bad['saved_views']['rows'][manual['window_ordinal']]['view_twr']=manual['wrong_subtract_cumulative_returns']; resign(bad['saved_views'])
            with self.assertRaises(ValueError): reader.inspect_saved_book(**bad)
        self.assertEqual(args,original); report['transitions'].clear(); self.assertEqual(args,original)

    def test_buy_fee_split_stale_full_simple_oracle(self):
        args=path_fixture(buy=True); report=reader.inspect_saved_book(**args)
        row=report['transitions'][0]['valuation_row']
        self.assertEqual((row['gross_buy_usd'],row['fees_usd'],row['cash_after_usd'],row['session_twr']),('50','0.05','1049.95',dict(numerator='-1',denominator='23000')))
        self.assertEqual(report['transitions'][1]['action_disposition'],'REJECTED_STALE_CORPORATE_ACTION')
        self.assertEqual(report['transitions'][1]['valuation_row']['fees_usd'],'0')
        self.assertEqual(report['transitions'][1]['next_state']['holdings_by_sid']['A'],4)

    def test_resigned_internal_fields_cannot_substitute_arithmetic(self):
        args=path_fixture(buy=True)
        mutators=[lambda t:t['next_state'].__setitem__('cash_usd','999'),lambda t:t['next_state']['holdings_by_sid'].__setitem__('A',9),lambda t:t['valuation_row'].__setitem__('fees_usd','0'),lambda t:t['valuation_row'].__setitem__('session_twr',dict(numerator='0',denominator='1')),lambda t:t['next_state']['applied_event_ids'].clear(),lambda t:t['next_state']['applied_action_ids'].clear(),lambda t:t['risk_observations']['prospective_open']['checks'].__setitem__('MAX_SINGLE_WEIGHT',False)]
        for mutate in mutators:
            bad=deepcopy(args); mutate(bad['saved_transitions'][0]); resign(bad['saved_transitions'][0]['next_state']); resign(bad['saved_transitions'][0])
            with self.subTest(mutate=mutate),self.assertRaises(ValueError): reader.inspect_saved_book(**bad)
        for key in ('applied_event_ids','applied_action_ids','cumulative_twr'):
            bad=deepcopy(args); state=bad['saved_bootstrap']['next_state']; state[key]=['forged'] if key!='cumulative_twr' else dict(numerator='1',denominator='2'); resign(state)
            with self.subTest(genesis=key),self.assertRaises(ValueError): reader.inspect_saved_book(**bad)

    def test_inputs_fatal_clock_lineage_duplicate_and_closed_types(self):
        args=path_fixture(True)
        changes=[lambda a:a['frames'][0].__setitem__('previous_state_sha256','0'*64),lambda a:a['explicit_actions'][0].__setitem__('information_cutoff_utc','2026-10-07T20:00:00Z'),lambda a:a['explicit_actions'][1].__setitem__('action_id','action1'),lambda a:a['scenario']['lane_coordinate'].__setitem__('extra',True),lambda a:a['initial_state']['holdings_by_sid'].__setitem__('A',True),lambda a:a['frames'][0]['source_context']['authority'].__setitem__('execution_authorized',0)]
        for change in changes:
            bad=deepcopy(args); change(bad)
            with self.subTest(change=change),self.assertRaises(ValueError): reader.inspect_saved_book(**bad)

    def test_pending_and_critical_block_stop_no_commit_full_views(self):
        for critical in (False,True):
            args=path_fixture(True); frame=args['frames'][0]; action=args['explicit_actions'][0]
            if critical: frame['source_context']['numeric_coverage']['prices']='MISSING'
            else: action.clear(); action.update(schema='EXPLICIT_RESEARCH_ACTION_V1',status='PENDING_ACTION_POLICY',reason='POLICY_MISSING',decision_session=args['initial_state']['session'],execution_session=frame['session'])
            result=producer.advance_research_book(scenario=args['scenario'],previous_state=args['saved_bootstrap']['next_state'],frame=frame,explicit_action=action)
            args['frames']=args['frames'][:1]; args['explicit_actions']=args['explicit_actions'][:1]; args['saved_transitions']=[result]
            args['saved_views']=producer.map_rolling_windows_to_book_views(window_coordinates=args['window_coordinates'],book_timeline=[],mapping_contract=args['mapping_contract'])
            report=reader.inspect_saved_book(**args); self.assertEqual(report['committed_transition_count'],0); self.assertEqual(report['numeric_status'],'BLOCKED')
            self.assertTrue(all(row['status']=='BLOCKED_WINDOW_VIEW' for row in report['views']['rows']))

    def test_endpoint_and_lineage_view_tampering(self):
        args=path_fixture(True)
        for key,value in [('stop_index',4),('start_index',2),('anchor_close_session','2026-10-06'),('anchor_state_sha256','0'*64)]:
            bad=deepcopy(args); bad['saved_views']['rows'][3][key]=value; resign(bad['saved_views'])
            with self.subTest(key=key),self.assertRaises(ValueError): reader.inspect_saved_book(**bad)
        bad=deepcopy(args); bad['mapping_contract']['book_lineage_id']='another'
        with self.assertRaises(ValueError): reader.inspect_saved_book(**bad)
        args['mapping_contract']['terminal_boundary']=None
        timeline=[]
        for t in args['saved_transitions']:
            s=t['next_state']; timeline.append(dict(sequence=s['sequence'],session=s['session'],previous_close_session=args['scenario']['calendar'][s['sequence']-1]['session'],previous_state_sha256=t['previous_state_sha256'],state_sha256=s['content_sha256'],book_lineage_id=s['book_lineage_id'],scenario_content_sha256=s['scenario_content_sha256'],session_twr=t['valuation_row']['session_twr'],status='COMPUTED'))
        args['saved_views']=producer.map_rolling_windows_to_book_views(window_coordinates=args['window_coordinates'],book_timeline=timeline,mapping_contract=args['mapping_contract'])
        self.assertEqual(reader.inspect_saved_book(**args)['views']['rows'][3]['blockers'],['BLOCKED_ENDPOINT'])

    def test_no_producer_project_import_io_or_callback(self):
        args=path_fixture(buy=True); source=Path(reader.__file__).read_text(encoding='utf-8'); tree=ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom): self.assertNotIn(node.module.split('.')[0],('backtest','data','scripts'))
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name): self.assertNotIn(node.func.id,('open','eval','exec','__import__'))
        with patch.object(producer,'advance_research_book',side_effect=AssertionError('Producer forbidden')),patch.object(producer,'check_state',side_effect=AssertionError('Validator forbidden')),patch.object(producer,'risk_snapshot',side_effect=AssertionError('Risk forbidden')),patch.object(producer,'map_rolling_windows_to_book_views',side_effect=AssertionError('Map forbidden')),patch('builtins.open',side_effect=AssertionError('IO forbidden')):
            self.assertEqual(reader.inspect_saved_book(**args)['status'],'PASS_SAVED_WHOLE_V2_PATH')


if __name__=='__main__': unittest.main()
