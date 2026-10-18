"""HTTP actual cash constraint across sell fills and a later fixed-target buy."""
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_v2_paper import create_router,PREFIX
from data.current_quantity_v2_monthly_continuation_factory import attach_monthly_continuation
from test_current_quantity_v2_monthly_continuation_sources import fixture


class MonthlyContinuationCompositionTests(unittest.TestCase):
    def test_sell_proceeds_only_after_fill_then_new_buy_and_exact_retry(self):
        with TemporaryDirectory() as folder:
            source,original,state,clock,quotes,rss=fixture(folder)
            parts=attach_monthly_continuation(original,monthly_sources=source)
            paper=parts['paper'];aid=state['ledger']['account_id']
            target=deepcopy(state['ledger']['target_quantities']);genesis=deepcopy(state['genesis'])
            initial_cash=Fraction(state['ledger']['cash']);initial_fees=Fraction(state['ledger']['recorded_fees'])
            app=FastAPI();app.include_router(create_router(service=paper))
            with TestClient(app) as client:
                def preview():
                    current=paper.store.read(aid)
                    response=client.post(PREFIX+'/continuation/preview',json=dict(account_id=aid,expected_revision=current['ledger']['revision']))
                    self.assertEqual(response.status_code,200,response.text)
                    result=response.json();self.assertEqual(result['target_quantities'],target)
                    self.assertFalse(result['unit_review']['coverage_complete'])
                    self.assertEqual(result['unit_review']['policy'],'MONTHLY_BOUNDED_PUBLIC_KNOWN_ACTIONS_V1')
                    return result
                def accept(proposal,operation):
                    request=dict(account_id=aid,proposal_id=proposal['proposal_id'],operation_id=operation,expected_revision=proposal['prior_revision'])
                    response=client.post(PREFIX+'/continuation/accept',json=request)
                    self.assertEqual(response.status_code,200,response.text)
                    return request
                def event(order,kind,**values):
                    current=paper.store.read(aid);clock[0]+=timedelta(seconds=1)
                    e=dict(event_id='root-'+kind+'-'+order['order_id'],type=kind,order_id=order['order_id'],expected_revision=current['ledger']['revision'],**values)
                    e['executed_at' if kind=='FILL' else 'cancelled_at']=clock[0].isoformat()
                    response=client.post(PREFIX+'/event',json=dict(account_id=aid,event=e))
                    self.assertEqual(response.status_code,200,response.text)
                    return paper.store.read(aid)
                first=preview();buy_before=next(o for o in first['orders'] if o['side']=='BUY')
                self.assertLessEqual(Fraction(first['reserved_buy_cash']),initial_cash)
                self.assertTrue(first['wait_cash'])
                accept(first,'root-before-sell')
                current=paper.store.read(aid)
                sell=next(o for o in current['ledger']['orders'].values() if o['side']=='SELL')
                sold=event(sell,'FILL',quantity=sell['quantity'],price=sell['limit_price'],fees='1/10')
                cash_after_sell=initial_cash+sell['quantity']*Fraction(sell['limit_price'])-Fraction('1/10')
                self.assertEqual(Fraction(sold['ledger']['cash']),cash_after_sell)
                pending=next(o for o in sold['ledger']['orders'].values() if o['side']=='BUY')
                closed=event(pending,'CANCEL')
                self.assertEqual(Fraction(closed['ledger']['cash']),cash_after_sell)
                self.assertEqual(closed['ledger']['target_quantities'],target)
                clock[0]+=timedelta(seconds=1)
                second=preview();buy_after=next(o for o in second['orders'] if o['side']=='BUY')
                self.assertGreater(buy_after['quantity'],buy_before['quantity'])
                self.assertLessEqual(Fraction(second['reserved_buy_cash']),cash_after_sell)
                request=accept(second,'root-after-sell')
                current=paper.store.read(aid);buy=next(o for o in current['ledger']['orders'].values() if o['side']=='BUY')
                filled=event(buy,'FILL',quantity=2,price=buy['limit_price'],fees='0')
                self.assertEqual(Fraction(filled['ledger']['cash']),cash_after_sell-2*Fraction(buy['limit_price']))
                self.assertEqual(Fraction(filled['ledger']['recorded_fees']),initial_fees+Fraction('1/10'))
                self.assertEqual(filled['ledger']['target_quantities'],target)
                self.assertEqual(filled['genesis'],genesis)
                self.assertEqual(rss,[1,1]);self.assertEqual(quotes,['AAA','BBB','BBB'])
                source.fetch=lambda _:self.fail('retry must not fetch quotes')
                source.review_reader.fetch=lambda:self.fail('retry must not fetch RSS')
                source._current=None;parts['bridge']._proposals.clear()
                clock[0]+=timedelta(days=90)
                response=client.post(PREFIX+'/continuation/accept',json=request)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(paper.store.read(aid),filled)


if __name__=='__main__':unittest.main()
