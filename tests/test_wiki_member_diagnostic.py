import csv
import json
from scripts.diagnose_wiki_member_subset import diagnose
from scripts.prepare_bull_bear_member_diagnostic import prepare


def test_member_intervals_and_duplicate_rejection(tmp_path):
    source=tmp_path/'members.csv'
    source.write_text('date,tickers\n2007-01-01,A\n2008-01-10,B\n2011-01-01,C\n')
    result=prepare(source)
    assert result['member_labels']==['A','B']
    assert result['memberships'][0]['start']=='2007-12-01'
    assert result['memberships'][0]['end']=='2008-01-09'
    source.write_text('date,tickers\n2007-01-01,"A,A"\n')
    try:prepare(source)
    except ValueError as error:assert str(error)=='DUPLICATE_MEMBER_LABEL'
    else:raise AssertionError('Duplicate members accepted')


def test_duplicate_rows_and_missing_member_preserved(tmp_path):
    request=tmp_path/'request.json';subset=tmp_path/'subset.csv'
    request.write_text(json.dumps(dict(member_labels=['AAPL','MISSING'],memberships=[dict(ticker=t,start='2007-01-01',end='2010-12-31') for t in ['AAPL','MISSING']])))
    fields=['ticker','date','open','high','low','close','split_ratio','ex-dividend']
    with subset.open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(fields)
        for ticker in ['AAPL','MSFT','INTC','AAPL']:writer.writerow([ticker,'2007-12-31',1,2,1,2,1,0])
    result=diagnose(request,subset)
    assert result['duplicate_rows']==[['AAPL','2007-12-31']]
    assert result['absent_member_labels']==['MISSING']
    assert result['windows'][0]['members']==['AAPL','MISSING']
    assert result['windows'][0]['incomplete']['MISSING']==['2007-12-31']


def test_empty_subset_explicitly_rejected(tmp_path):
    request=tmp_path/'request.json';subset=tmp_path/'subset.csv'
    request.write_text(json.dumps(dict(member_labels=['AAPL'],memberships=[])))
    subset.write_text('ticker,date,open,high,low,close,split_ratio,ex-dividend\n')
    try:diagnose(request,subset)
    except ValueError as error:assert str(error)=='MISSING_REFERENCE_SERIES'
    else:raise AssertionError('Empty subset accepted')
