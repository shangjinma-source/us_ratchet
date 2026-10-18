"""One pure conditional price predictor. No IO, parameter search or portfolio fit.

Method parameters are ROOT_RESEARCH_METHOD, not user preferences. Only prices
at/before the requested cutoff are inspected; future values are never touched.
"""
from datetime import date
import math

FEATURE_NAMES = ('log_price_change_21','log_price_change_63','log_price_change_126',
                 'daily_log_return_standard_deviation_21')
METHOD = 'ROOT_RESEARCH_PRICE_RIDGE_21_V1'


def require(condition,message):
    if not condition:
        raise ValueError(message)


def features_at(prices,index):
    """Exact common-calendar indices; no missing-price compression or filling."""
    require(type(index) is int and index >= 0,'Nonboolean feature index')
    require(hasattr(prices,'__len__') and index < len(prices),'Feature index within supplied common calendar')
    if index < 126:
        return None,['FEATURE_HISTORY_SHORTER_THAN_126_COMMON_INTERVALS']
    needed = {index,index-21,index-63,index-126} | set(range(index-21,index+1))
    require(all(prices[i] is None or type(prices[i]) in (int,float) and math.isfinite(prices[i]) and prices[i]>0 for i in needed),'Finite positive required feature prices or None')
    missing = sorted(i for i in needed if prices[i] is None)
    if missing:
        return None,['MISSING_FEATURE_PRICE_AT_COMMON_INDEX_'+str(i) for i in missing]
    changes = [math.log(prices[index])-math.log(prices[index-period]) for period in (21,63,126)]
    daily = [math.log(prices[i])-math.log(prices[i-1]) for i in range(index-20,index+1)]
    mean = math.fsum(daily)/21
    std = math.sqrt(math.fsum((value-mean)**2 for value in daily)/20)
    values = changes+[std]
    require(all(math.isfinite(value) for value in values),'Finite four-feature vector')
    return values,[]


def mature_label(prices,anchor,cutoff):
    require(type(anchor) is int and type(cutoff) is int and 0<=anchor<=cutoff,'Nonnegative nonboolean label coordinates, anchor cannot follow cutoff')
    end=anchor+21
    if end > cutoff:
        return None,['LABEL_END_NOT_MATURE_AT_CUTOFF']
    require(hasattr(prices,'__len__') and cutoff < len(prices) and end < len(prices),'Mature label coordinates within supplied common calendar')
    require(all(prices[i] is None or type(prices[i]) in (int,float) and math.isfinite(prices[i]) and prices[i]>0 for i in range(anchor,end+1)),'Finite positive mature label prices or None')
    missing=[i for i in range(anchor,end+1) if prices[i] is None]
    if missing:
        return None,['MISSING_TARGET_PRICE_AT_COMMON_INDEX_'+str(i) for i in missing]
    label=math.log(prices[end])-math.log(prices[anchor])
    require(math.isfinite(label),'Finite log21 target')
    return label,[]


def solve_linear(matrix,rhs):
    """Small5x5 Gaussian elimination with partial pivoting; no solver callbacks."""
    count=len(rhs)
    require(count==5 and len(matrix)==5 and all(len(row)==5 for row in matrix),'Fixed5x5 system')
    rows=[list(row)+[value] for row,value in zip(matrix,rhs)]
    require(all(math.isfinite(value) for row in rows for value in row),'Finite normal equations')
    for column in range(count):
        pivot=max(range(column,count),key=lambda row:abs(rows[row][column]))
        require(rows[pivot][column]!=0,'Nonsingular registered ridge equations')
        rows[column],rows[pivot]=rows[pivot],rows[column]
        divisor=rows[column][column]
        rows[column]=[value/divisor for value in rows[column]]
        for row in range(count):
            if row==column:
                continue
            factor=rows[row][column]
            rows[row]=[value-factor*base for value,base in zip(rows[row],rows[column])]
    beta=[rows[row][-1] for row in range(count)]
    require(all(math.isfinite(value) for value in beta),'Finite registered coefficients')
    return beta


def fit_registered_ridge(feature_rows,labels):
    require(len(feature_rows)==len(labels) and feature_rows,'Nonempty matching regression examples')
    require(all(len(row)==4 and all(type(v) in (int,float) and math.isfinite(v) for v in row) for row in feature_rows)
            and all(type(v) in (int,float) and math.isfinite(v) for v in labels),'Four finite features and labels')
    count=len(labels)
    means=[math.fsum(row[j] for row in feature_rows)/count for j in range(4)]
    scales=[math.sqrt(math.fsum((row[j]-means[j])**2 for row in feature_rows)/count) for j in range(4)]
    scales=[value if value>0 else 1. for value in scales]
    design=[[1.]+[(row[j]-means[j])/scales[j] for j in range(4)] for row in feature_rows]
    matrix=[[math.fsum(row[i]*row[j] for row in design)+(1. if i==j and i>0 else 0.) for j in range(5)] for i in range(5)]
    rhs=[math.fsum(row[j]*label for row,label in zip(design,labels)) for j in range(5)]
    beta=solve_linear(matrix,rhs)
    return dict(feature_means=means,feature_scales=scales,intercept=beta[0],coefficients=beta[1:],
                ridge_penalty=1.,normalizer_std_ddof=0,intercept_penalized=False,training_examples=count)


def project_feature_vector(model,features):
    require(type(model) is dict and {'intercept','coefficients','feature_means','feature_scales'}<=set(model),'Typed model projection fields')
    vectors=(features,model['coefficients'],model['feature_means'],model['feature_scales'])
    require(all(type(vector) in (list,tuple) and len(vector)==4
                and all(type(value) in (int,float) and math.isfinite(value) for value in vector) for vector in vectors),'Exactly four finite nonboolean projection coordinates')
    require(type(model['intercept']) in (int,float) and math.isfinite(model['intercept']),'Finite nonboolean intercept')
    require(all(scale>0 for scale in model['feature_scales']),'Positive projection scales')
    prediction=model['intercept']+math.fsum(coefficient*(value-mean)/scale for coefficient,value,mean,scale in
        zip(model['coefficients'],features,model['feature_means'],model['feature_scales']))
    require(math.isfinite(prediction),'Finite conditional predicted log21 change')
    try:
        simple=math.expm1(prediction)
    except OverflowError:
        return None,['NONFINITE_SIMPLE_PRICE_PROJECTION']
    annual=12*prediction
    if not math.isfinite(simple) or not math.isfinite(annual):
        return None,['NONFINITE_PRICE_OR_ANNUAL_LOG_PROJECTION']
    return dict(predicted_log_change_21=prediction,simple_price_change_21=simple,
                annualized_log_price_projection=annual,guaranteed_annual_return=False),[]


def fit_predict_price_projection(*,calendar,prices_by_ticker,cutoff_index,declared_price_basis):
    require(type(calendar) is list and type(cutoff_index) is int and 0<=cutoff_index<len(calendar),'Explicit common calendar/cutoff index')
    require(type(declared_price_basis) is str and declared_price_basis.startswith('CONDITIONAL_') and len(declared_price_basis)>len('CONDITIONAL_'),'Explicit conditional provider price-basis assumption')
    prefix_dates=calendar[:cutoff_index+1]
    require(all(type(day) is str and date.fromisoformat(day).isoformat()==day for day in prefix_dates)
            and prefix_dates==sorted(set(prefix_dates)),'Canonical sorted common-calendar prefix')
    require(type(prices_by_ticker) is dict and prices_by_ticker
            and all(type(ticker) is str and ticker.strip() for ticker in prices_by_ticker),'Explicit ticker domain')
    prices={}
    for ticker,series in prices_by_ticker.items():
        require(type(series) is list and len(series)>=cutoff_index+1,'Aligned price prefix for each declared ticker')
        # Never inspect or validate values after the cutoff.
        prefix=series[:cutoff_index+1]
        require(all(value is None or type(value) in (int,float) and math.isfinite(value) and value>0 for value in prefix),
                'Prefix prices must be finite positive int/float or None; bool/NaN denied')
        prices[ticker]=prefix
    anchors=[cutoff_index-21*n for n in range(1,7)]
    training=[];blocked_training=[];prediction_features={};features_blocked={}
    for ticker in sorted(prices):
        values=prices[ticker]
        vector,reasons=features_at(values,cutoff_index)
        if reasons:features_blocked[ticker]=reasons
        else:prediction_features[ticker]=vector
        for anchor in anchors:
            if anchor<0:
                blocked_training.append(dict(ticker=ticker,anchor_index=anchor,reasons=['ANCHOR_BEFORE_COMMON_CALENDAR']))
                continue
            vector,feature_reasons=features_at(values,anchor)
            label,label_reasons=mature_label(values,anchor,cutoff_index)
            reasons=feature_reasons+label_reasons
            if reasons:
                blocked_training.append(dict(ticker=ticker,anchor_index=anchor,reasons=reasons))
            else:
                training.append(dict(ticker=ticker,anchor_index=anchor,anchor_date=prefix_dates[anchor],
                    label_end_index=anchor+21,label_end_date=prefix_dates[anchor+21],features=vector,target_log_change_21=label))
    distinct_anchors=sorted({row['anchor_index'] for row in training})
    model_reasons=[]
    if len(training)<30:model_reasons.append('FEWER_THAN_30_MATURE_TRAINING_EXAMPLES')
    if len(distinct_anchors)<3:model_reasons.append('FEWER_THAN_3_DISTINCT_MATURE_ANCHORS')
    model=None
    if not model_reasons:
        model=fit_registered_ridge([row['features'] for row in training],[row['target_log_change_21'] for row in training])
    forecasts=[]
    for ticker in sorted(prices):
        reasons=features_blocked.get(ticker,[])+model_reasons
        projection=None
        if not reasons:
            projection,reasons=project_feature_vector(model,prediction_features[ticker])
        forecasts.append(dict(ticker=ticker,status='BLOCKED' if reasons else 'CONDITIONAL_MODEL_PROJECTION',
            reasons=reasons,features=prediction_features.get(ticker),projection=projection,
            security_id=None,security_qualification_established=False))
    return dict(schema='RETURN_PRIORITY_PRICE_PREDICTOR_RESEARCH_V1',method_id=METHOD,
        status='CONDITIONAL_PRICE_MODEL_FITTED_NOT_VALIDATED_ALPHA' if model is not None else 'BLOCKED_INSUFFICIENT_MATURE_TRAINING',
        cutoff_index=cutoff_index,cutoff_date=prefix_dates[-1],declared_price_basis=declared_price_basis,
        price_basis_certification='CONDITIONAL_NOT_CERTIFIED',feature_names=list(FEATURE_NAMES),feature_std_ddof=1,
        training_decision_anchors=anchors,distinct_used_training_anchors=distinct_anchors,
        training_examples=training,blocked_training_examples=blocked_training,model=model,forecasts=forecasts,
        training_label_intervals_nonoverlapping=True,prediction_uses_future_prices=False,
        model_parameters_authority='ROOT_RESEARCH_METHOD_NOT_USER_PREFERENCE',
        dividends_included=False,predictive_alpha_causally_validated=False,guaranteed_future_returns=False,
        hyperparameter_search_performed=False,portfolio_search_performed=False,
        fullPIT_or_security_identity_qualification=False,current_adoption_allowed=False,orders_created=False,
        six_cutoff_thirteen_real_book_goal_complete=False,future_one_year_independent_oos_mature=False)
