import unittest
from copy import deepcopy
from scripts.review_daily_ui_capture_v1 import review

class ReviewTests(unittest.TestCase):
    def capture(self):
        order=dict(security_id='S',side='BUY',quantity=2,limit_price='10',estimated_cash_change='-20',reference_valid_until='2026-10-23T14:02:00Z')
        account=dict(revision='r',holdings=[],available_cash='100')
        daily=dict(status='READY',account_revision='r',target_id='t',new_orders=[order],reference_quotes={'S':dict(observed_at='2026-10-23T14:00:30Z',buy='10',sell='10',reference_valid_until=order['reference_valid_until'])},effective_target_quantities={'S':2})
        return dict(observed_at='2026-10-23T14:01:00Z',account_before=account,account_after=deepcopy(account),cash_posts_intercepted=1,unexpected_writes=[],state=dict(busy=False,error=None,account=account,target={'target_id':'t','targets':[dict(security_id='S',quantity=2)]},daily=daily),visible_rows=[dict(security_id='S',orders=[order],explanation='补足目标2股')])
    def dom(self,c):
        from fractions import Fraction
        daily=c['state']['daily'];held={r['security_id']:r['quantity'] for r in c['state']['account']['holdings']}
        daily['daily_gate']=dict(status='DAILY_TARGET_READY',rows=[dict(security_id=o['security_id'],action=o['side'],held=held.get(o['security_id'],0),effective_target=daily['effective_target_quantities'][o['security_id']]) for o in daily['new_orders']])
        monthly={r['security_id']:r['quantity'] for r in c['state']['target']['targets']}
        for row in c['visible_rows']:
            order=row['orders'][0]
            row.update(dom_match_count=1,dom_cells=[row['security_id'],str(held.get(row['security_id'],0)),str(monthly.get(row['security_id'],'—')),str(daily['effective_target_quantities'][row['security_id']]),('买入' if order['side']=='BUY' else '卖出')+' '+str(order['quantity'])+' 股',f"${float(Fraction(order['limit_price'])):,.2f}",row['explanation']])
        return c
    def test_valid_capture(self): self.assertEqual(review(self.dom(self.capture()))['status'],'INTRADAY_UI_CHECKS_PASS')
    def test_orders_require_matching_validated_daily_target(self):
        for change in ('missing','side','held','target','duplicate'):
            c=self.dom(self.capture());gate=c['state']['daily']['daily_gate']
            if change=='missing':gate['status']='WAIT'
            elif change=='side':gate['rows'][0]['action']='HOLD'
            elif change=='held':gate['rows'][0]['held']=99
            elif change=='target':gate['rows'][0]['effective_target']=1
            else:gate['rows'].append(deepcopy(gate['rows'][0]))
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'ORDER_'):review(c)
    def test_numeric_columns_match_authoritative_state(self):
        for column,reason in [(1,'DOM_HELD_MISMATCH'),(2,'DOM_MONTHLY_TARGET_MISMATCH'),(3,'DOM_EFFECTIVE_TARGET_MISMATCH')]:
            c=self.dom(self.capture());c['visible_rows'][0]['dom_cells'][column]='999'
            with self.subTest(column=column),self.assertRaisesRegex(ValueError,reason):review(c)

    def test_wait_never_passes(self):
        c=self.capture();c['state']['daily'].update(status='WAIT',new_orders=[],reason='WAIT_POLICY_REVIEW_SESSION')
        self.assertEqual(review(c)['status'],'NOT_ACCEPTED_WAIT')
    def test_rejects_failures(self):
        changes=[lambda c:c['account_after'].update(revision='other'),lambda c:c['state']['daily'].update(account_revision='old'),lambda c:c.update(observed_at='2026-10-23T14:03:00Z'),lambda c:c['visible_rows'][0].update(explanation=''),lambda c:c['state']['account'].update(available_cash='19'),lambda c:c['state']['daily']['effective_target_quantities'].update(S=1)]
        for change in changes:
            c=self.dom(self.capture());change(c)
            with self.assertRaises(ValueError):review(c)
    def test_sell_cannot_exceed_holdings_or_risk_difference(self):
        c=self.capture();c['state']['account']['holdings']=[dict(security_id='S',quantity=14)];c['account_after']=deepcopy(c['account_before'])
        c['state']['daily']['effective_target_quantities']['S']=6;c['state']['daily']['new_orders'][0].update(side='SELL',quantity=8,estimated_cash_change='80')
        self.assertEqual(review(self.dom(c))['status'],'INTRADAY_UI_CHECKS_PASS')
        c['state']['daily']['new_orders'][0]['quantity']=9
        with self.assertRaisesRegex(ValueError,'EXCESS_SELL'):review(self.dom(c))
    def test_old_future_or_naive_quote_is_not_rescued_by_valid_order(self):
        for value in ('2026-10-22T14:00:30Z','2026-10-23T14:01:01Z','2026-10-23T14:00:30'):
            c=self.capture();c['state']['daily']['reference_quotes']['S']['observed_at']=value
            with self.assertRaisesRegex(ValueError,'QUOTE'):review(self.dom(c))
    def test_source_expiry_and_price_must_match_visible_order(self):
        c=self.capture();c['state']['daily']['reference_quotes']['S']['reference_valid_until']='2026-10-23T14:01:00Z'
        with self.assertRaisesRegex(ValueError,'EXPIRED_PRICE'):review(self.dom(c))
        c=self.capture();c['state']['daily']['reference_quotes']['S']['buy']='9'
        with self.assertRaisesRegex(ValueError,'QUOTE_PRICE_MISMATCH'):review(self.dom(c))
    def test_consistent_but_stale_ui_account_is_rejected(self):
        c=self.capture()
        c['state']['account']=deepcopy(c['state']['account'])
        c['state']['account'].update(revision='stale',available_cash='1000')
        c['state']['daily']['account_revision']='stale'
        with self.assertRaisesRegex(ValueError,'UI_ACCOUNT_MISMATCH'):review(c)

    def test_sale_proceeds_cannot_fund_concurrent_buy(self):
        c=self.capture()
        account=c['state']['account']
        account.update(available_cash='19',holdings=[dict(security_id='T',quantity=10)])
        c['account_after']=deepcopy(account)
        daily=c['state']['daily']
        sell=dict(security_id='T',side='SELL',quantity=10,limit_price='10',
                  estimated_cash_change='100',reference_valid_until='2026-10-23T14:02:00Z')
        daily['new_orders'].append(sell)
        daily['effective_target_quantities']['T']=0
        daily['reference_quotes']['T']=deepcopy(daily['reference_quotes']['S'])
        c['visible_rows'].append(dict(security_id='T',orders=[sell],explanation='退出10股'))
        with self.assertRaisesRegex(ValueError,'USES_UNFILLED_SALE_CASH'):review(self.dom(c))
        # Only cash actually available, including buy fees, may fund the order.
        account['available_cash']='21'
        c['account_after']=deepcopy(account)
        daily['new_orders'][0]['estimated_cash_change']='-21'
        self.assertEqual(review(self.dom(c))['buy_cash'],'21')
        daily['new_orders'][0]['estimated_cash_change']='-22'
        with self.assertRaisesRegex(ValueError,'USES_UNFILLED_SALE_CASH'):review(c)
    def test_stale_or_missing_dom_is_not_rescued_by_correct_state(self):
        for field,value,reason in [(4,'等待','DOM_ACTION_MISMATCH'),(5,'$9.00','DOM_PRICE_MISMATCH'),(6,'旧原因','DOM_REASON_MISMATCH')]:
            c=self.dom(self.capture());c['visible_rows'][0]['dom_cells'][field]=value
            with self.assertRaisesRegex(ValueError,reason):review(c)
        c=self.dom(self.capture());c['visible_rows'][0]['dom_match_count']=2
        with self.assertRaisesRegex(ValueError,'MISSING_DOM_ROW'):review(c)

    def test_hold_requires_complete_matching_target_and_visible_reason(self):
        c=self.capture()
        c['state']['account']['holdings']=[dict(security_id='S',quantity=2)]
        c['account_after']=deepcopy(c['account_before'])
        c['state']['target']['targets']=[dict(security_id='S',quantity=2)]
        c['state']['daily'].update(status='HOLD',new_orders=[],effective_target_quantities=None,
            daily_gate=dict(status='DAILY_TARGET_READY',rows=[dict(security_id='S',action='HOLD',held=2,effective_target=2)]))
        c['visible_rows']=[dict(security_id='S',orders=[],dom_match_count=1,
            dom_cells=['S','2','2','2','持有，无需操作','暂无有效建议','已符合今日持仓目标，无需买卖。'],
            explanation='已符合今日持仓目标，无需买卖。')]
        self.assertEqual(review(c)['status'],'HOLD_UI_CHECKS_PASS')
        for column in (1,2,3):
            changed=deepcopy(c);changed['visible_rows'][0]['dom_cells'][column]='999'
            with self.subTest(column=column),self.assertRaisesRegex(ValueError,'DOM_'):review(changed)
        for kind in ('missing_gate','missing_row','wrong_target','stale_dom'):
            changed=deepcopy(c)
            if kind=='missing_gate':changed['state']['daily'].pop('daily_gate')
            elif kind=='missing_row':changed['state']['daily']['daily_gate']['rows']=[]
            elif kind=='wrong_target':changed['state']['daily']['daily_gate']['rows'][0]['effective_target']=1
            else:changed['visible_rows'][0]['dom_cells'][4]='买入 2 股'
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'HOLD_'):review(changed)
if __name__=='__main__':unittest.main()
