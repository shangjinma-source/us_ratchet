from copy import deepcopy
from datetime import datetime,timezone
import json
import unittest
from scripts import ndx_current101_price_independent_audit_20260919 as module


def epoch(date):return int(datetime.fromisoformat(date+'T14:00:00+00:00').timestamp())
def fixture():
    times=[epoch(d) for d in ('2024-06-03','2024-06-04','2024-06-05')];event=dict(date=times[1],numerator=2.,denominator=1.,splitRatio='2:1')
    body=dict(chart=dict(error=None,result=[dict(meta=dict(symbol='TEST',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),timestamp=times,
        indicators=dict(quote=[dict(open=[5.,6.,7.],close=[5.5,6.5,7.5])]),events=dict(splits={str(times[1]):event}))]))
    task=dict(ticker='TEST',mode='NEW_CONDITIONAL_RECONSTRUCTION',exclude_on_or_after='2024-06-05')
    rows=[]
    for i,date in enumerate(('2024-06-03','2024-06-04')):
        factor=2 if i==0 else 1
        rows.append(dict(session=date,ticker='TEST',currency='USD',provider_timestamp=times[i],quote_open=5.+i,quote_close=5.5+i,nominal_open=(5.+i)*factor,nominal_close=(5.5+i)*factor,
            split_factor_numerator=str(factor),split_factor_denominator='1',split_factor=float(factor)))
    return body,task,rows


class Tests(unittest.TestCase):
    def test_raw_ratio_two_prices_and_completed_calendar(self):
        body,task,rows=fixture();info=module.inspect_raw(json.dumps(body).encode(),'TEST')
        result=module.audit_rows(rawinfo=info,task=task,rows=rows)
        self.assertEqual(result['row_count'],2);self.assertEqual(result['maximum_absolute_decimal_error'],'0')
        self.assertEqual(result['calendar'],['2024-06-03','2024-06-04'])
    def test_missing_unfinalized_bool_nan_and_forged_factors_reject(self):
        for defect in ('missing','receipt','bool','nan','factor','price','ticker'):
            body,task,rows=fixture();info=module.inspect_raw(json.dumps(body).encode(),'TEST')
            if defect=='missing':rows.pop()
            elif defect=='receipt':rows.append(dict(rows[-1],session='2024-06-05'))
            elif defect=='bool':rows[0]['nominal_open']=True
            elif defect=='nan':rows[0]['nominal_close']=float('nan')
            elif defect=='factor':rows[0].update(split_factor=1.,split_factor_numerator='1')
            elif defect=='price':rows[0]['nominal_close']+=1
            else:rows[0]['ticker']='OTHER'
            with self.subTest(defect=defect),self.assertRaises(ValueError):module.audit_rows(rawinfo=info,task=task,rows=rows)
    def test_duplicate_raw_dates_split_ratio_and_wrong_meta_reject(self):
        for defect in ('dates','ratio','market'):
            body,_,_=fixture();data=body['chart']['result'][0]
            if defect=='dates':data['timestamp'][1]=data['timestamp'][0]
            elif defect=='ratio':next(iter(data['events']['splits'].values()))['splitRatio']='3:1'
            else:data['meta']['symbol']='WRONG'
            with self.subTest(defect=defect),self.assertRaises(ValueError):module.inspect_raw(json.dumps(body).encode(),'TEST')
    def test_hard_final_index_complete_partition_and_no_relabel(self):
        plan=module.loads(module.PLAN.read_bytes());index=module.loads(module.INDEX.read_bytes());module.validate_index(index,plan)
        for defect in ('partial','duplicate','blocked','flag'):
            value=deepcopy(index)
            if defect=='partial':value['status']='PARTIAL'
            elif defect=='duplicate':value['entries'][-1]=deepcopy(value['entries'][0])
            elif defect=='blocked':next(e for e in value['entries'] if e['ticker']=='TRI')['mode']='NEW_CONDITIONAL_RECONSTRUCTION'
            else:value['promotion_allowed']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):module.validate_index(value,plan)
        with self.assertRaisesRegex(ValueError,'Hard final'):module.build(index_path=module.INDEX,index_sha256='0'*64)


if __name__=='__main__':unittest.main()
