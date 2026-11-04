from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import patch
import test_review_daily_ui_capture_v6 as prior
from scripts.review_daily_ui_capture_v7 import review,timestamp


def adapt(c):
    c=deepcopy(c);c['capture_schema']='DAILY_FOUR_COLUMN_DOM_CAPTURE_V3';c['scheduled_context']={}
    for row in c['dom_rows']:row['scheduled_notes']=[]
    return c


def fixture():
    c=adapt(prior.capture_fixture());c['dom_rows'][0]['ticker']='MRNA'
    c['api_state']['target']['proposal_targets'][0]['ticker']='MRNA'
    now=timestamp(c['observed_at']);scheduled=now+timedelta(days=1)
    c['scheduled_context']={'status':'CONTEXT_ONLY','events':[dict(ticker='MRNA',event_kind='EARNINGS_CALL',eligible_as_new_trigger=False,may_refresh_event_window=False,scheduled_at=scheduled.isoformat(),observed_at=now.isoformat())]}
    from zoneinfo import ZoneInfo
    local=scheduled.astimezone(ZoneInfo('Asia/Shanghai'))
    c['dom_rows'][0]['scheduled_notes']=[f'财报会议：{local.month}/{local.day} {local.hour:02d}:{local.minute:02d}（北京时间）；非业绩结论']
    sync(c);return c


def sync(c):
    prior.sync(c)
    for row in c['dom_rows']:row['dom_cells'][3]+=''.join(row['scheduled_notes'])
    c['page_text']='\n'.join(['\t'.join(c['table_headers'])]+['\t'.join(r['dom_cells']) for r in c['dom_rows']])


class FinancialRegression(prior.FourColumnTests):
    def setUp(self):
        original_review=review
        self.patcher=patch.object(prior,'review',lambda c:original_review(adapt(c)))
        self.patcher.start();self.addCleanup(self.patcher.stop)


class CalendarTests(unittest.TestCase):
    def test_exact_match_immutable(self):
        c=fixture();before=deepcopy(c)
        self.assertEqual(review(c)['calendar_rows_matched'],1);self.assertEqual(c,before)
    def test_unverified_is_not_accepted_calendar(self):
        c=fixture();c['dom_rows'][0]['scheduled_notes']=['财报安排未核实'];c['scheduled_context']={};sync(c)
        self.assertEqual(review(c)['calendar_rows_matched'],0)
    def test_reject_changed_expired_forged_and_unknown(self):
        for kind in ('reschedule','expiry','future_observation','fake_text','unknown_ai','missing_context','duplicate','page_tamper'):
            c=fixture();event=c['scheduled_context']['events'][0]
            if kind=='reschedule':event['scheduled_at']=(timestamp(event['scheduled_at'])+timedelta(hours=1)).isoformat()
            elif kind=='expiry':event['observed_at']=(timestamp(c['observed_at'])-timedelta(days=2)).isoformat()
            elif kind=='future_observation':event['observed_at']=event['scheduled_at']
            elif kind=='fake_text':c['dom_rows'][0]['scheduled_notes']=['明天必涨'];sync(c)
            elif kind=='unknown_ai':c['dom_rows'][0]['dom_parts']['ai_text']='放心买入';sync(c)
            elif kind=='missing_context':c.pop('scheduled_context')
            elif kind=='duplicate':c['dom_rows'][0]['scheduled_notes']*=2;sync(c)
            else:c['page_text']=c['page_text'].replace('非业绩结论','可以买入')
            with self.subTest(kind=kind),self.assertRaises(ValueError):review(c)

if __name__=='__main__':unittest.main()
