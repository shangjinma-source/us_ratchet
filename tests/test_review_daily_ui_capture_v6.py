"""Synthetic four-column DOM plus independent API evidence, no browser/network."""
from copy import deepcopy
import unittest
from scripts.review_daily_ui_capture_v6 import review, HEADERS, UNREVIEWED
import test_review_daily_ui_capture_v3 as fixtures


def capture_fixture():
    old = fixtures.FrontierReviewTests().capture()
    old['state']['target']['proposal_targets'][0]['ticker']='TEST'
    row=old['visible_rows'][0]
    parts=dict(position='0 → 2',monthly_note='',actions=['买入 2 股'],limits=['限价 $10.00'],
               reason=row['explanation'],ai_label='AI 复核 · 研究预览',ai_text=UNREVIEWED)
    result={k:deepcopy(v) for k,v in old.items() if k not in ('state','visible_rows')}
    result.update(capture_schema='DAILY_FOUR_COLUMN_DOM_CAPTURE_V2',scope='READ_ONLY_PAGE_CAPTURE',
                  ui_controls=dict(cash_button_text='更新现金并查看建议',cash_button_disabled=False,refresh_button_disabled=False),
                  cash_posts_intercepted=0,api_state=deepcopy(old['state']),table_headers=list(HEADERS),dom_row_count=1,
                  dom_rows=[dict(ticker='TEST',dom_parts=parts)])
    sync(result)
    return result


def sync(capture):
    for row in capture['dom_rows']:
        p=row['dom_parts']
        row['dom_cells']=[row['ticker'],p['position']+p['monthly_note'],
                          ''.join(a+(p['limits'][i] if i<len(p['limits']) else '') for i,a in enumerate(p['actions'])),
                          p['reason']+p['ai_label']+p['ai_text']]
    capture['page_text']='\n'.join(['\t'.join(capture['table_headers'])]+['\t'.join(r['dom_cells']) for r in capture['dom_rows']])


class FourColumnTests(unittest.TestCase):
    def test_ready_immutable_and_honest_scope(self):
        capture=capture_fixture();before=deepcopy(capture);result=review(capture)
        self.assertEqual(result['status'],'INTRADAY_UI_CHECKS_PASS')
        self.assertFalse(result['ai_risk_plan_accepted']);self.assertEqual(capture,before)
        self.assertIn('separately captured API',result['evidence_scope'])

    def test_dom_and_ai_fail_closed(self):
        for field,value in [('position','1 → 2'),('monthly_note','本月目标 99 股'),('actions',['卖出 2 股']),('limits',['限价 $11.00']),('reason',''),('ai_text','已采用 卖出')]:
            c=capture_fixture();c['dom_rows'][0]['dom_parts'][field]=value;sync(c)
            with self.subTest(field=field),self.assertRaises(ValueError):review(c)

    def test_financial_guards(self):
        for kind in ('expiry','cash','account','proposal','future_quote','price','fraction','gate','unfilled_sale'):
            c=capture_fixture();s=c['api_state'];d=s['daily'];order=d['new_orders'][0]
            if kind=='expiry':d['reference_quotes']['S']['reference_valid_until']=c['observed_at']
            elif kind in ('cash','unfilled_sale'):
                s['account']['available_cash']='0';c['account_before']=deepcopy(s['account']);c['account_after']=deepcopy(s['account'])
            elif kind=='account':c['account_after']['revision']='changed'
            elif kind=='proposal':d['proposal_id']='b'*64
            elif kind=='future_quote':d['reference_quotes']['S']['observed_at']='2026-10-23T14:02:00Z'
            elif kind=='price':d['reference_quotes']['S']['buy']='11'
            elif kind=='fraction':order['quantity']=1.5
            else:d['daily_gate']['rows'][0]['action']='SELL'
            with self.subTest(kind=kind),self.assertRaises(ValueError):review(c)

    def test_monthly_note_actual_and_hold(self):
        c=capture_fixture();s=c['api_state'];s['target']['proposal_targets'][0]['quantity']=4
        s['target']['risk_monthly_targets']['S']=4;s['daily']['risk_monthly_targets']['S']=4
        c['dom_rows'][0]['dom_parts']['monthly_note']='本月目标 4 股';sync(c)
        self.assertEqual(review(c)['orders'],1)
        c=capture_fixture();s=c['api_state'];s['account']['holdings']=[dict(security_id='S',ticker='TEST',quantity=2)]
        c['account_before']=deepcopy(s['account']);c['account_after']=deepcopy(s['account'])
        s['daily'].update(status='HOLD',new_orders=[]);s['daily']['daily_gate']['rows']=[dict(security_id='S',action='HOLD',held=2,effective_target=2)]
        c['dom_rows'][0]['dom_parts'].update(position='2 → 2',actions=['无需操作'],limits=[]);sync(c)
        self.assertEqual(review(c)['status'],'HOLD_UI_CHECKS_PASS')

    def test_sell_and_excess_sell_rejected(self):
        c=capture_fixture();state=c['api_state'];daily=state['daily']
        state['account']['holdings']=[dict(security_id='S',ticker='TEST',quantity=5)]
        c['account_before']=deepcopy(state['account']);c['account_after']=deepcopy(state['account'])
        order=daily['new_orders'][0];order.update(side='SELL',quantity=3,estimated_cash_change='30')
        daily['daily_gate']['rows'][0].update(action='SELL',held=5,effective_target=2)
        c['dom_rows'][0]['dom_parts'].update(position='5 → 2',actions=['卖出 3 股']);sync(c)
        self.assertEqual(review(c)['status'],'INTRADAY_UI_CHECKS_PASS')
        self.assertEqual(review(c)['buy_cash'],'0')
        order['quantity']=4;c['dom_rows'][0]['dom_parts']['actions']=['卖出 4 股'];sync(c)
        with self.assertRaisesRegex(ValueError,'EXCESS_SELL'):review(c)

    def test_nontrading_rows_no_price_and_complete_domain(self):
        c=capture_fixture();state=c['api_state'];daily=state['daily']
        state['account']['holdings']=[dict(security_id='T',ticker='HELD',quantity=3)]
        c['account_before']=deepcopy(state['account']);c['account_after']=deepcopy(state['account'])
        state['target']['proposal_targets'].append(dict(security_id='T',ticker='HELD',quantity=3))
        for item in (state['target'],daily):item['risk_monthly_targets']['T']=3
        daily['effective_target_quantities']['T']=3
        daily['daily_gate']['rows'].append(dict(security_id='T',action='HOLD',held=3,effective_target=3))
        held=deepcopy(c['dom_rows'][0]);held['ticker']='HELD'
        held['dom_parts'].update(position='3 → 3',actions=['无需操作'],limits=[],reason='继续持有。')
        c['dom_rows'].append(held);c['dom_row_count']=2;sync(c)
        self.assertEqual(review(c)['orders'],1)
        for mutation in ('price','action','missing','extra_alias'):
            bad=deepcopy(c)
            if mutation=='price':bad['dom_rows'][1]['dom_parts']['limits']=['限价 $10.00']
            elif mutation=='action':bad['dom_rows'][1]['dom_parts']['actions']=['卖出 3 股']
            elif mutation=='missing':bad['dom_rows'].pop();bad['dom_row_count']=1
            else:
                # API holding alias must not allow a second displayed row for the same SID.
                bad['api_state']['account']['holdings'][0]['ticker']='ALIAS'
                bad['account_before']=deepcopy(bad['api_state']['account']);bad['account_after']=deepcopy(bad['api_state']['account'])
                alias=deepcopy(held);alias['ticker']='ALIAS';bad['dom_rows'].append(alias);bad['dom_row_count']=3
            sync(bad)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):review(bad)
        waiting=deepcopy(c);waiting['api_state']['daily']['daily_gate']['rows'][1]['action']='WAIT'
        waiting['dom_rows'][1]['dom_parts']['actions']=['等待'];sync(waiting)
        self.assertEqual(review(waiting)['orders'],1)

    def test_capture_scope_identity_and_wait(self):
        for kind in ('write','hidden_state','header','duplicate','extra','page','busy','refresh_busy','missing_controls'):
            c=capture_fixture()
            if kind=='busy':c['ui_controls']['cash_button_disabled']=True
            elif kind=='refresh_busy':c['ui_controls']['refresh_button_disabled']=True
            elif kind=='missing_controls':del c['ui_controls']
            elif kind=='write':c['cash_posts_intercepted']=1
            elif kind=='hidden_state':c['state']=deepcopy(c['api_state'])
            elif kind=='header':c['table_headers'][1]='OLD'
            elif kind=='duplicate':c['dom_rows']*=2;c['dom_row_count']=2
            elif kind=='extra':c['dom_rows'][0]['ticker']='UNKNOWN';sync(c)
            else:c['page_text']=''
            with self.subTest(kind=kind),self.assertRaises(ValueError):review(c)
        c=capture_fixture();c['api_state']['daily'].update(status='WAIT',new_orders=[])
        c['dom_rows'][0]['dom_parts'].update(actions=['等待'],limits=[]);sync(c)
        self.assertEqual(review(c)['status'],'NOT_ACCEPTED_WAIT')


if __name__=='__main__':unittest.main()
