"""Isolated successor proposals from a trusted input provider, never HTTP plans."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from threading import Lock
from zoneinfo import ZoneInfo

from backtest.return_priority_fresh_cash_quantity_search import search_fresh_cash_quantities
from data.current_research_monthly_plan import build_monthly_research_plan
from data.current_research_paper_store import ResearchPaperStore
from data.current_research_monthly_policy import route_monthly_research_policy
from data.current_research_successor_plan import build_research_successor_plan, roll_research_plan
from data.current_research_successor_inputs import SuccessorInputLoader

MONTHLY_CONTRACT = 'research_contracts/user_monthly_target_preference_20261014_v1.json'


def unavailable_input_provider(input_id):
    raise ValueError('后续决策行情输入尚未配置：UNAVAILABLE')


class CurrentResearchSuccessorService:
    """Provider bundles are trusted Python inputs, not user-submitted payloads.

    Required keys: decision_date, active_date, calendar, valuation_quotes,
    source_hashes, held_unit_continuity, market_session, decision_session.
    RESELECT also requires search_arguments. input_id denotes immutable inputs.
    Memory proposals are lost on restart; no raw-plan fallback is accepted.
    """
    def __init__(self, *, base_service, input_provider=None, search=search_fresh_cash_quantities):
        self.base = base_service
        self.input_provider = input_provider or SuccessorInputLoader(root=base_service.root)
        self.search = search
        self.lock = Lock()
        self.proposals = {}
        self.keys = {}

    @staticmethod
    def _require(ok, message):
        if not ok:
            raise ValueError(message)

    def _timing(self, bundle):
        from data.current_research_successor_inputs import validate_successor_time_chain
        now = self.base._now()
        validate_successor_time_chain(bundle, root=self.base.root, now=now)
        pins = bundle['source_hashes']
        sessions = []
        for key, day in [('decision_session', bundle['decision_date']), ('market_session', bundle['active_date'])]:
            session = bundle[key]
            self._require(session['date'] == day and session['timezone'] == 'America/New_York', '交易时段日期或时区不匹配')
            opening, closing = (datetime.fromisoformat(session[field]) for field in ('open_at', 'close_at'))
            for stamp in (opening, closing):
                ny = stamp.astimezone(ZoneInfo('America/New_York')) if stamp.tzinfo else None
                self._require(ny is not None and stamp.date().isoformat() == day and ny.date().isoformat() == day
                              and stamp.utcoffset() == ny.utcoffset(), '交易时段必须是明确纽约时间')
            self._require(opening < closing, '交易时段起止无效')
            refs = session.get('source_references', [])
            self._require(isinstance(refs, list), '交易时段来源格式无效')
            refs = list(refs) + ([session['source']] if 'source' in session else [])
            self._require(refs and all(isinstance(ref, str) and ref in pins for ref in refs), '交易时段来源未绑定')
            sessions.append((opening, closing))
        self._require(now >= sessions[0][1], '决策日尚未收盘，不能生成后续计划')
        self._require(sessions[1][0] > sessions[0][1] and now < sessions[1][1], '后续有效交易时段已失效或不是新时段')

    def available_input(self, account_id, expected_revision):
        state = self.base._read_account(account_id)
        self._require(state['revision'] == expected_revision, '账户版本已变化：STALE_ACCOUNT_REVISION')
        finder = getattr(self.input_provider, 'find_for_account', None)
        self._require(callable(finder), '后续决策输入发现尚不可用：UNAVAILABLE')
        result = deepcopy(finder(account_id, expected_revision, state['plan']['plan_id']))
        self._require(result.get('account_id') == account_id and result.get('revision') == expected_revision
                      and result.get('parent_plan_id') == state['plan']['plan_id'], '可用输入账户绑定不匹配')
        from datetime import date
        decision, active = result['decision_date'], result['active_date']
        self._require(date.fromisoformat(decision).isoformat() == decision
                      and date.fromisoformat(active).isoformat() == active and decision < active, '可用输入日期无效')
        bundle = self.input_provider(result['input_id'])
        self._require(all(bundle.get(k) == result.get(k) for k in ('account_id','revision','parent_plan_id','decision_date','active_date')), '可用输入加载绑定不一致')
        self._timing(bundle)
        self._require(self.base._read_account(account_id)['revision'] == expected_revision, '读取期间账户已变化：STALE_ACCOUNT_REVISION')
        return dict(result, expected_revision=expected_revision, current_revision=expected_revision,
                    research_only=True, execution_blocked=True, search_calls_this_request=0)

    def preview(self, account_id, input_id, expected_revision):
        self._require(isinstance(input_id, str) and bool(input_id.strip()), '需要明确的已审条件输入编号')
        with self.lock:
            state = self.base._read_account(account_id)
            self._require(state['revision'] == expected_revision, '账户版本已变化，请刷新：STALE_ACCOUNT_REVISION')
            key = (account_id, expected_revision, input_id)
            if key in self.keys:
                record = self.proposals[self.keys[key]]
                self._require(self.input_provider(input_id) == record['bundle'], '已审输入已变更或撤回，请重新准备预览')
                self._timing(record['bundle'])
                return deepcopy(dict(record['response'], cache_hit=True, search_calls_this_request=0))
            bundle = deepcopy(self.input_provider(input_id))
            self._require(isinstance(bundle, dict), '已审条件输入包不可用')
            self._require(bundle.get('account_id') == account_id and bundle.get('revision') == expected_revision
                          and bundle.get('parent_plan_id') == state['plan']['plan_id'], '输入包账户、版本或父计划不匹配')
            self._timing(bundle)
            parameters = {name: bundle[name] for name in ('decision_date','active_date','calendar','valuation_quotes',
                'source_hashes','held_unit_continuity','market_session')}
            mode = bundle.get('policy_mode', 'BOUND_MONTHLY_POLICY')
            self._require(mode in ('BOUND_MONTHLY_POLICY', 'ADOPT_INITIAL_FROZEN_MONTHLY_POLICY'), '不支持的月度政策模式')
            if mode == 'ADOPT_INITIAL_FROZEN_MONTHLY_POLICY':
                self._require(len(state['plans']) == 1 and state['plan']['strategy_version'] == 'PAPER_FROZEN_QUANTITY_V1'
                    and 'target_month' not in state['plan']['causal_inputs']['research_snapshot'], '仅允许显式接纳单个初始冻结计划')
                self._require(MONTHLY_CONTRACT in bundle['source_hashes'], '初始政策接纳缺少用户月度偏好来源')
                contract = (self.base.root / MONTHLY_CONTRACT).read_bytes()
                self._require(hashlib.sha256(contract).hexdigest() == bundle['source_hashes'][MONTHLY_CONTRACT], '用户月度偏好来源指纹不符')
                route = route_monthly_research_policy(decision_date=bundle['decision_date'],active_date=bundle['active_date'],
                    calendar=bundle['calendar'],current_target_month=state['plan']['active_date'][:7])
                parameters['target_month'] = route['target_month']
                if route['action'] == 'RESELECT':
                    self._require(bundle.get('search_arguments') is not None, '月度重选缺少完整参数')
                    result = build_research_successor_plan(state,expected_revision=expected_revision,search_arguments=bundle['search_arguments'],search=self.search,**parameters)
                else:
                    result = roll_research_plan(state,expected_revision=expected_revision,**parameters)
                result['route'] = route
            else:
                result = build_monthly_research_plan(state, expected_revision=expected_revision,
                    search_arguments=bundle.get('search_arguments'), search=self.search, **parameters)
            # A separate process may have changed the account during search.
            self._require(self.base._read_account(account_id)['revision'] == expected_revision, '计算期间账户已变化：STALE_ACCOUNT_REVISION')
            self._timing(bundle)
            preview_id = hashlib.sha256(json.dumps(dict(account_id=account_id, revision=expected_revision,
                input_id=input_id, bundle=bundle, plan_id=result['plan']['plan_id']), sort_keys=True,
                ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            response = dict(account_id=account_id, input_id=input_id, preview_id=preview_id,
                current_revision=expected_revision, expected_revision=expected_revision, plan=result['plan'],
                policy_mode=mode,
                market_session=deepcopy(bundle['market_session']), route=result['route'],
                research_only=True, execution_blocked=True, activation_performed=False,
                cache_hit=False, search_calls_this_request=1 if result['route']['action']=='RESELECT' else 0)
            self.proposals[preview_id] = dict(bundle=bundle, response=deepcopy(response))
            self.keys[key] = preview_id
            return deepcopy(response)

    def activate(self, account_id, preview_id, event_id, expected_revision):
        with self.lock:
            self._require(isinstance(preview_id, str) and preview_id in self.proposals,
                          '预览已失效，请重新预览；不接受外部计划')
            record = self.proposals[preview_id]
            response = record['response']
            self._require(response['account_id'] == account_id and response['expected_revision'] == expected_revision,
                          '预览账户或版本不匹配')
            self._require(isinstance(event_id, str) and bool(event_id.strip()), '需要明确激活事件编号')
            state = self.base._read_account(account_id)
            event = dict(event_id=event_id, mode='PAPER_MANUAL_FILL', event_type='ACTIVATE_PLAN',
                plan_id=response['plan']['plan_id'], expected_revision=expected_revision)
            existing = next((item for item in state['events'] if item['event_id']==event_id), None)
            if existing is None:
                self._require(self.input_provider(response['input_id']) == record['bundle'], '已审输入已变更或撤回，不能激活')
                self._require(state['revision'] == expected_revision, '账户版本已变化：STALE_ACCOUNT_REVISION')
                self._timing(record['bundle'])
            # Existing exact event goes through ledger idempotency even after expiry.
            updated = ResearchPaperStore(self.base.directory).activate_plan(account_id, response['plan'], event)
            return dict(self.base._response(updated), preview_id=preview_id, input_id=response['input_id'],
                        activation_performed=True, idempotent_replay=existing is not None)


from data.current_research_paper_service import SERVICE as BASE_SERVICE

SERVICE = CurrentResearchSuccessorService(base_service=BASE_SERVICE)
