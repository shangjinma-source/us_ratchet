"""Exact rational boxes, PSD supporting planes and PER_K cover checking."""
from copy import deepcopy
from fractions import Fraction as F
from backtest.ndx_continuous_joint_projection_research import (
    TAU, rat, require, digest, validate_competition, check_support, _witness)


def axis(lo, hi, lc=True, uc=True):
    return dict(lower=str(lo),upper=str(hi),lower_closed=lc,upper_closed=uc)


def root_region(c, support):
    core = c['core']
    check_support(core,support)
    V = F(core['V'])
    require(V > 0 and core['T'] is not None, 'Bounded reciprocal domain requires V>0 and budget>=0')
    r = core['risk']
    lo, hi = max(F(0),F(r['min_single_weight'])-TAU),min(F(1),F(r['max_single_weight'])+TAU)
    return dict(support=list(support),holding_count=len(support),
        axes={**{s:axis(lo,hi,lo>0,True) for s in support},
              '$y':axis(1/(V+F(core['T'])),1/V)})


def check_region(c, region):
    require(type(region) is dict and set(region) == {'support','holding_count','axes'}, 'Closed region shape')
    support = region['support']
    check_support(c['core'],support)
    require(type(region['holding_count']) is int and region['holding_count'] == len(support), 'Region k drift')
    root = root_region(c,support)
    require(type(region['axes']) is dict and set(region['axes']) == set(root['axes']), 'Region axes exact')
    for key,a in region['axes'].items():
        require(type(a) is dict and set(a) == {'lower','upper','lower_closed','upper_closed'}, 'Closed axis shape')
        require(type(a['lower_closed']) is bool and type(a['upper_closed']) is bool, 'Endpoint ownership bool')
        lo,hi = rat(a['lower'],'lower'),rat(a['upper'],'upper')
        base = root['axes'][key]
        require(F(base['lower']) <= lo <= hi <= F(base['upper']), 'Region outside full domain')
        if lo == F(base['lower']) and not base['lower_closed']:
            require(not a['lower_closed'], 'Open support boundary cannot close')
        require(lo < hi or a['lower_closed'] and a['upper_closed'], 'Empty half-open singleton')


def contains(region, witness):
    if region['support'] != witness['support']:
        return False
    values = {**witness['weights'],'$y':witness['y']}
    for key,a in region['axes'].items():
        v,lo,hi = F(values[key]),F(a['lower']),F(a['upper'])
        if not (lo <= v <= hi) or v == lo and not a['lower_closed'] or v == hi and not a['upper_closed']:
            return False
    return True


def equal_waterfill(lower, upper):
    """Exact minimizer of sum w² on the box/simplex; None if mass impossible."""
    keys = sorted(lower)
    if any(lower[s] > upper[s] for s in keys) or sum(lower.values(),F(0)) > 1 or sum(upper.values(),F(0)) < 1:
        return None
    if sum(lower.values(),F(0)) == 1:
        return dict(lower)
    levels = sorted(set(lower.values())|set(upper.values()))
    for a,b in zip(levels,levels[1:]):
        active = [s for s in keys if lower[s] <= a and upper[s] > a]
        fixed = sum((min(upper[s],max(lower[s],a)) for s in keys if s not in active),F(0))
        if active:
            level = (1-fixed)/len(active)
            if a <= level <= b:
                return {s:min(upper[s],max(lower[s],level)) for s in keys}
    if sum(upper.values(),F(0)) == 1:
        return dict(upper)
    return None


def affine_simplex_min(gradient, lower, upper):
    if equal_waterfill(lower,upper) is None:
        return None
    w = dict(lower)
    mass = 1-sum(w.values(),F(0))
    for s in sorted(w,key=lambda s:(gradient[s],s)):
        add = min(mass,upper[s]-w[s])
        w[s] += add
        mass -= add
    require(mass == 0, 'Internal simplex bound failure')
    return sum((gradient[s]*w[s] for s in w),F(0))


def bound_region(c, region, supporting_point=None):
    """Every inequality is valid on a closed relaxation of the original region."""
    check_region(c,region)
    core, support = c['core'],region['support']
    a = region['axes']
    yl,yu = F(a['$y']['lower']),F(a['$y']['upper'])
    lower = {s:F(a[s]['lower']) for s in support}
    upper = {s:F(a[s]['upper']) for s in support}
    for s in support:
        v = F(core['old_amounts'].get(s,'0'))
        lower[s] = max(lower[s],v*yl)
        if s not in core['buy_security_ids']:
            upper[s] = min(upper[s],v*yu)
    reasons = []
    if any(lower[s] > upper[s] for s in support): reasons.append('FROZEN_PROJECTION_BOX_CONTRADICTION')
    normpoint = equal_waterfill(lower,upper)
    if normpoint is None: reasons.append('SIMPLEX_MASS_CONTRADICTION')
    # Open singleton zero cannot be a positive support point, even though the
    # closed relaxation used by other bounds admits zero at a boundary.
    if any(upper[s] <= 0 for s in support): reasons.append('NO_STRICT_POSITIVE_SUPPORT')
    r = {k:F(v) for k,v in core['risk'].items()}
    if sum(sorted(lower.values(),reverse=True)[:3]) > r['top_weight_cap']+TAU:
        reasons.append('TOP3_LOWER_BOUND')
    chains = {}
    for s in support:
        chain = core['metadata'][s]['risk_chain']
        chains[chain] = chains.get(chain,F(0))+lower[s]
    if max(chains.values()) > r['risk_chain_top1_cap']+TAU: reasons.append('CHAIN_LOWER_BOUND')
    h = r['minimum_effective_n_ratio']*len(support)-TAU
    if h > 0 and normpoint is not None and sum(v*v for v in normpoint.values()) > 1/h:
        reasons.append('EFFECTIVE_N_MIN_NORM_BOUND')
    variance_lower, plane = F(0),None
    if not reasons:
        ids = c['synthetic_covariance']['security_ids']
        matrix = c['synthetic_covariance']['values']
        pos = {s:i for i,s in enumerate(ids)}
        if supporting_point is None:
            u = normpoint
        else:
            require(type(supporting_point) is dict and set(supporting_point) == set(support), 'Exact supporting point fields')
            u = {s:rat(v,'supporting point') for s,v in supporting_point.items()}
        gradient = {s:2*sum((F(matrix[pos[s]][pos[t]])*u[t] for t in support),F(0)) for s in support}
        fu = sum((u[s]*gradient[s]/2 for s in support),F(0))
        constant = -fu
        affine_lb = affine_simplex_min(gradient,lower,upper)+constant
        variance_lower = max(F(0),affine_lb)
        plane = dict(point={s:str(v) for s,v in u.items()},gradient={s:str(v) for s,v in gradient.items()},
                     constant=str(constant),affine_simplex_lower=str(affine_lb))
    V,W = F(core['V']),F(core['W0'])
    tl,tu = (1/yu-V)/W,(1/yl-V)/W
    result = dict(schema='SYNTHETIC_CONTINUOUS_REGION_BOUND_V1',competition_id=c['competition_id'],
        scope='PER_K',holding_count=len(support),region=deepcopy(region),
        infeasibility_reasons=reasons,closure_only_relaxation=True,
        tightened_lower={s:str(v) for s,v in lower.items()},tightened_upper={s:str(v) for s,v in upper.items()},
        variance_lower=str(variance_lower),turnover_lower=str(tl),turnover_upper=str(tu),turnover_span=str(tu-tl),
        supporting_plane=plane,method='EXACT_PSD_SUPPORTING_PLANE_BOX_SIMPLEX_AND_INTERVAL_CONTRADICTIONS')
    result['certificate_id'] = digest(result)
    return result


def verify_continuous_region_certificate(*, competition, region, certificate):
    c = validate_competition(competition)
    point = certificate.get('supporting_plane')
    rebuilt = bound_region(c,region,None if point is None else point['point'])
    require(digest(certificate) == digest(rebuilt), 'Region certificate drift or unsupported claim')
    return rebuilt


def cover_region(c, region, bound, witness):
    point = bound.get('supporting_plane')
    require(bound == bound_region(c,region,None if point is None else point['point'])
            and not bound['infeasibility_reasons'], 'Verified nonempty relaxation required')
    rebuilt = _witness(c,witness['support'],witness['y'],witness['weights'])
    require(digest(witness) == digest(rebuilt), 'Feasible witness drift')
    require(witness['holding_count'] == region['holding_count'], 'PER_K cover requires same k; cross-k GLOBAL only')
    f,t = F(witness['objectives']['variance']),F(witness['objectives']['turnover'])
    require(f <= F(bound['variance_lower'])+F(c['epsilon_variance'])
            and t <= F(bound['turnover_lower'])+F(c['epsilon_turnover']), 'Epsilon objective coverage not proven')
    return dict(scope='PER_K',holding_count=region['holding_count'],region=deepcopy(region),
        bound_certificate_id=bound['certificate_id'],witness=deepcopy(witness),
        epsilon_variance=c['epsilon_variance'],epsilon_turnover=c['epsilon_turnover'],
        claim='TRAINING_OBJECTIVE_VALUES_ONLY_ALL_ACTION_FAMILIES_RETAINED')


def verify_continuous_cover_certificate(*, competition, region, bound, certificate):
    c = validate_competition(competition)
    require(type(certificate) is dict and certificate.get('scope') == 'PER_K', 'PER_K certificate required')
    rebuilt = cover_region(c,region,bound,certificate['witness'])
    require(digest(rebuilt) == digest(certificate), 'Coverage certificate drift')
    return rebuilt


def split_region(region):
    """Partition into disjoint half-open children, including parent endpoints."""
    keys = [s for s in sorted(region['axes']) if F(region['axes'][s]['upper']) > F(region['axes'][s]['lower'])]
    if not keys: return None
    key = max(keys,key=lambda s:(F(region['axes'][s]['upper'])-F(region['axes'][s]['lower']),s))
    left,right = deepcopy(region),deepcopy(region)
    a = region['axes'][key]
    mid = (F(a['lower'])+F(a['upper']))/2
    left['axes'][key]['upper'],left['axes'][key]['upper_closed'] = str(mid),False
    right['axes'][key]['lower'],right['axes'][key]['lower_closed'] = str(mid),True
    return left,right


def inherited_bound_relation(c, child, parent_certificate):
    """Check subdomain ownership; the certificate continues naming its parent."""
    check_region(c,child)
    parent = parent_certificate['region']
    check_region(c,parent)
    require(child['support'] == parent['support'], 'Inherited bound support mismatch')
    for key,a in child['axes'].items():
        p = parent['axes'][key]
        lo,hi,pl,pu = F(a['lower']),F(a['upper']),F(p['lower']),F(p['upper'])
        require(pl <= lo <= hi <= pu, 'Child is not a parent subdomain')
        require(not (lo == pl and a['lower_closed'] and not p['lower_closed'])
                and not (hi == pu and a['upper_closed'] and not p['upper_closed']), 'Child endpoint ownership exceeds parent')
    return dict(scope='PER_K',holding_count=child['holding_count'],
        parent_certificate_id=parent_certificate['certificate_id'],parent_region_id=digest(parent),
        child_region_id=digest(child),relation='EXACT_SUBDOMAIN_INCLUDING_OPEN_ENDPOINT_OWNERSHIP',
        certificate_region_remains='ORIGINAL_PARENT_REGION_NOT_RELABELLED_CHILD')


def verify_inherited_parent_bound(*, competition, child_region, parent_certificate):
    c = validate_competition(competition)
    point = parent_certificate.get('supporting_plane')
    rebuilt = bound_region(c,parent_certificate['region'],None if point is None else point['point'])
    require(digest(parent_certificate) == digest(rebuilt), 'Original parent certificate drift')
    return inherited_bound_relation(c,child_region,rebuilt)


def propose_witnesses(c, region):
    core, support = c['core'],region['support']
    a = region['axes']
    ys = sorted(set([F(a['$y']['lower']),F(a['$y']['upper']),
                     (F(a['$y']['lower'])+F(a['$y']['upper']))/2]))
    found, checks = [],0
    for y in ys:
        lower,upper = {},{}
        for s in support:
            v = F(core['old_amounts'].get(s,'0'))
            lower[s] = max(F(a[s]['lower']),v*y)
            upper[s] = F(a[s]['upper']) if s in core['buy_security_ids'] else min(F(a[s]['upper']),v*y)
        weights = equal_waterfill(lower,upper)
        if weights is None: continue
        checks += 1
        try:
            witness = _witness(c,support,y,weights)
        except ValueError:
            continue
        if contains(region,witness): found.append(witness)
    return found,len(ys),checks
