import unittest
from fractions import Fraction as F
from scripts.research.overnight_book_20261105 import run_book
from scripts.research.run_overnight_fixed_20261105 import merge_pins, rebuild_rosters, validate_mapped_action


class OvernightBookTests(unittest.TestCase):
    def inputs(self):
        days=['2024-09-27','2024-09-30','2024-10-01','2024-10-02']
        prices={'OLD':{d:dict(open='10',close='10') for d in days}}
        return dict(days=days,prices=prices,rosters=[dict(decision=days[0],selected=['OLD'])],
                    initial_cash=100,slippage_bps=0)

    def test_quantity_causal_and_insufficient_slot_rejected(self):
        args=self.inputs();args['prices']['OLD']['2024-09-30']['close']='11'
        result=run_book(**args)
        self.assertEqual(result['rejections'][0]['quantity'],10)
        self.assertEqual(result['rejections'][0]['reason'],'FIXED_SLOT_CASH_EXCEEDED')
        self.assertFalse(any(o['day']=='2024-09-30' for o in result['orders']))

    def test_split_before_open_sale_and_dividend_earmarked(self):
        args=self.inputs();args['prices']['NEW']={d:dict(open='1',close='1') for d in args['days']}
        args['rosters'].append(dict(decision='2024-09-30',selected=['NEW']))
        args['splits']=[dict(date='2024-10-01',old_sid='OLD',new_sid='NEW',ratio='10')]
        args['dividends']=[dict(sid='NEW',ex_date='2024-10-01',amount='0.1',payment_date=None)]
        result=run_book(**args)
        sale=next(o for o in result['orders'] if o['side']=='SELL')
        self.assertEqual((sale['sid'],sale['quantity']),('NEW',100))
        self.assertEqual(F(result['terminal_equity']),110)
        self.assertEqual(F(result['cash']),100)
        self.assertEqual(F(result['receivables'][0]['amount']),10)

    def test_control_holds_and_gate_sees_own_real_exposure(self):
        args=self.inputs();seen=[]
        args['exposure_check']=lambda previous,day,held:seen.append((day,held))
        result=run_book(**args,mode='monthly_hold')
        self.assertEqual(len(result['orders']),2)
        self.assertEqual(seen[-1][1],{'OLD':10})
        self.assertEqual(result['holdings'],{})

    def test_unknown_signal_rejected_and_paid_dividend_not_used_same_close(self):
        args=self.inputs();args['rosters'][0]['decision']='2024-09-30'
        with self.assertRaisesRegex(ValueError,'ROSTER_NOT_KNOWN'):
            run_book(**args)
        args=self.inputs();args['dividends']=[dict(sid='OLD',ex_date='2024-10-01',amount='1',payment_date='2024-10-01')]
        result=run_book(**args)
        buys=[o for o in result['orders'] if o['side']=='BUY']
        self.assertEqual([o['quantity'] for o in buys],[10,10])
        self.assertEqual(F(result['terminal_equity']),110)

    def test_qqq_hold_retries_after_initial_rejection(self):
        args=self.inputs();args['prices']['OLD']['2024-09-30']['close']='11'
        result=run_book(**args,mode='monthly_hold',retry_until_first_fill=True)
        buys=[o for o in result['orders'] if o['side']=='BUY']
        self.assertEqual([(o['day'],o['quantity']) for o in buys],[('2024-10-01',9)])
        control=run_book(**args,mode='monthly_hold')
        self.assertEqual(control['orders'],[])

    def test_parent_roster_reconstruction_and_pin_conflict(self):
        book=dict(selection_account_states=[dict(decision_date='2024-09-27',valuation_quotes=[
            dict(security_id='A',ticker='A',price='2'),dict(security_id='B',ticker='B',price='1')])],
            provider_audit=[dict(target_decision_date='2024-09-27',selection=dict(target_quantities={'A':1,'B':3}))])
        roster=rebuild_rosters(book,['2024-09-27','2024-09-30'])[0]
        self.assertEqual(roster['selected'],['B','A'])
        self.assertEqual(roster['earliest_buy_session'],'2024-09-30')
        with self.assertRaisesRegex(ValueError,'PIN_CONFLICT'):
            merge_pins({'source':'old'},{'source':'new'})

    def test_nominal_dividend_and_split_ratio_tampering_rejected(self):
        raw=dict(kind='dividends',date='2024-10-01')
        event=dict(sid='A',ex_date=raw['date'],amount='0.04',payment_date='2024-10-20')
        row=dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id='A',ex_date=raw['date'],
                 amount_per_share='0.04',payment_date=event['payment_date'],currency='USD',source_references=['issuer'])
        review=dict(rows=[row],source_hashes={'issuer':'fixed'})
        validate_mapped_action(raw,'A',[event],[],review)
        with self.assertRaisesRegex(ValueError,'NOMINAL_AMOUNT'):
            validate_mapped_action(raw,'A',[dict(event,amount='0.004')],[],review)
        raw=dict(kind='splits',date='2024-10-01',provider_payload=dict(numerator=10,denominator=1))
        row=dict(type='split_identity',security_id='A',date=raw['date'],new_security_id='B',new_shares=10,old_shares=1,observed_provider_events=[raw])
        with self.assertRaisesRegex(ValueError,'RATIO_OR_IDENTITY'):
            validate_mapped_action(raw,'A',[],[dict(old_sid='A',new_sid='B',date=raw['date'],ratio='1')],dict(rows=[row]))


if __name__=='__main__':
    unittest.main()
