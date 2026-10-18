"""Read-only server-owned, explicitly reviewed successor input registry."""
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

from data.current_portfolio_preview import ROOT

REGISTRY_SCHEMA = 'RESEARCH_SUCCESSOR_INPUT_REGISTRY_V1'
DEFAULT_REGISTRY = 'data/research_paper/successor_input_registry.json'


def validate_successor_time_chain(bundle, *, root, now=None):
    """Receipt bytes bind capture time; legacy explicit inputs need no fake receipt."""
    def require(ok, message):
        if not ok:raise ValueError(message)
    require(isinstance(bundle.get('admission'), dict) and isinstance(bundle['admission'].get('reviewed_at'), str), 'EXPLICIT_REVIEW_TIME_REQUIRED')
    reviewed = datetime.fromisoformat(bundle['admission']['reviewed_at'])
    close = datetime.fromisoformat(bundle['decision_session']['close_at'])
    require(reviewed.tzinfo is not None and close.tzinfo is not None and close <= reviewed,
            'REVIEW_BEFORE_DECISION_CLOSE')
    if now is not None:
        require(now.tzinfo is not None and reviewed <= now, 'REVIEW_AFTER_SERVER_NOW')
    observations = bundle.get('saved_quote_observations')
    if bundle.get('quote_reference_policy') == 'EXACT_RAW_DECISION_CLOSE_NO_ROUNDING':
        require(isinstance(observations, dict)
                and set(observations) == {q['security_id'] for q in bundle['valuation_quotes']}, 'SAVED_OBSERVATION_DOMAIN_REQUIRED')
    if observations is None:return
    require(isinstance(observations, dict), 'INVALID_SAVED_OBSERVATIONS')
    pins = bundle['source_hashes']; loader = SuccessorInputLoader(root=root)
    for observation in observations.values():
        sources = observation['source_hashes']
        require(sources and all(pins.get(p) == h for p,h in sources.items()), 'OBSERVATION_PINS_NOT_BOUND')
        receipts = [p for p in sources if Path(p).name == observation['ticker']+'.receipt.json']
        require(len(receipts) == 1, 'OBSERVATION_RECEIPT_REQUIRED')
        path = receipts[0]; raw = loader._path(path).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == pins[path], 'OBSERVATION_RECEIPT_HASH_MISMATCH')
        receipt = json.loads(raw)
        raw_paths = [p for p in sources if Path(p).name == observation['ticker']+'.response.bin']
        require(len(raw_paths) == 1 and receipt.get('raw_sha256') == pins[raw_paths[0]], 'OBSERVATION_RECEIPT_RAW_MISMATCH')
        received = datetime.fromisoformat(receipt['received_at_utc'])
        require(receipt['ticker'] == observation['ticker'] and received.tzinfo is not None
                and received == datetime.fromisoformat(observation['received_at']), 'OBSERVATION_RECEIPT_TIME_MISMATCH')
        require(observation['decision_date'] == bundle['decision_date']
                and datetime.fromisoformat(observation['declared_session_close_at']) == close,
                'OBSERVATION_DECISION_TIME_MISMATCH')
        require(close <= received <= reviewed, 'CAPTURE_AFTER_REVIEW_OR_BEFORE_CLOSE')


class SuccessorInputLoader:
    """Hash closure proves stored bytes, not quote truth or event completeness.

    The server owns the registry. Every entry must point to a explicitly reviewed
    conditional bundle; no market IO or automatic continuity inference occurs.
    """
    def __init__(self, *, root=ROOT, registry_path=DEFAULT_REGISTRY):
        self.root = Path(root).resolve()
        self.registry_path = registry_path

    @staticmethod
    def _require(ok, message):
        if not ok:
            raise ValueError(message)

    def _path(self, value):
        self._require(isinstance(value, str) and bool(value.strip()), '输入来源路径必须明确')
        path = Path(value)
        self._require(not path.is_absolute() and not path.drive and '..' not in path.parts,
                      '输入来源路径必须在研究root内，禁止绝对路径或上级目录')
        resolved = (self.root / path).resolve()
        self._require(resolved.is_relative_to(self.root), '输入来源符号链接逃逸root')
        return resolved

    def find_for_account(self, account_id, revision, parent_plan_id):
        registry_file = self._path(self.registry_path)
        self._require(registry_file.is_file(), '后续决策输入登记尚不存在：UNAVAILABLE')
        registry = json.loads(registry_file.read_bytes())
        self._require(registry.get('schema') == REGISTRY_SCHEMA and isinstance(registry.get('entries'), dict), '输入登记schema无效')
        matches = []
        for input_id, entry in registry['entries'].items():
            if isinstance(entry, dict) and all(entry.get(k) == v for k, v in [('account_id', account_id), ('revision', revision), ('parent_plan_id', parent_plan_id)]):
                bundle = self(input_id)
                matches.append((bundle['decision_date'], bundle['active_date'], input_id, bundle))
        self._require(bool(matches), '该账户版本暂无已审输入：UNAVAILABLE')
        latest = max((item[0], item[1]) for item in matches)
        matches = [item for item in matches if item[:2] == latest]
        self._require(len(matches) == 1, '同一最新交易日期存在多个输入：AMBIGUOUS')
        decision, active, input_id, bundle = matches[0]
        return dict(account_id=account_id, revision=revision, parent_plan_id=parent_plan_id,
                    input_id=input_id, decision_date=decision, active_date=active,
                    admission=bundle['admission'])

    def __call__(self, input_id):
        try:
            return self._load(input_id)
        except (OSError, KeyError, TypeError, AttributeError) as error:
            raise ValueError('已审输入缺文件或结构不完整：UNAVAILABLE') from error

    def _load(self, input_id):
        self._require(isinstance(input_id, str) and re.fullmatch('[0-9a-f]{64}', input_id),
                      'input_id必须为输入内容SHA256')
        registry_file = self._path(self.registry_path)
        self._require(registry_file.is_file(), '后续决策输入登记尚不存在：UNAVAILABLE')
        registry = json.loads(registry_file.read_bytes())
        self._require(registry.get('schema') == REGISTRY_SCHEMA and isinstance(registry.get('entries'), dict),
                      '输入登记schema无效')
        self._require(input_id in registry['entries'], '未登记的后续决策输入：UNAVAILABLE')
        entry = registry['entries'][input_id]
        self._require(isinstance(entry, dict) and entry.get('sha256') == input_id, '输入登记内容哈希不一致')
        raw = self._path(entry['bundle_path']).read_bytes()
        self._require(hashlib.sha256(raw).hexdigest() == input_id, '输入包字节已变化')
        bundle = json.loads(raw)
        self._require(isinstance(bundle, dict), '输入包必须为对象')
        for key in ('account_id', 'revision', 'parent_plan_id'):
            self._require(isinstance(entry.get(key), str) and entry[key].strip()
                          and bundle.get(key) == entry[key], '输入包与登记账户绑定不一致：' + key)
        for key in ('decision_date', 'active_date'):
            value = bundle[key]
            self._require(type(value) is str and date.fromisoformat(value).isoformat() == value, '输入交易日期无效')
        calendar = bundle['calendar']
        self._require(isinstance(calendar, list) and len(calendar) >= 2
                      and all(type(day) is str and date.fromisoformat(day).isoformat() == day for day in calendar)
                      and calendar == sorted(set(calendar)), '输入日历必须明确有序且不重复')
        self._require(bundle['decision_date'] in calendar, '决策日未在输入日历内')
        index = calendar.index(bundle['decision_date'])
        self._require(index + 1 < len(calendar) and calendar[index+1] == bundle['active_date'], '输入交易日不相邻')
        pins = bundle['source_hashes']
        self._require(isinstance(pins, dict) and bool(pins), '缺少输入来源指纹')
        for path, expected in pins.items():
            self._require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), '来源指纹格式无效')
            self._require(hashlib.sha256(self._path(path).read_bytes()).hexdigest() == expected,
                          '输入来源文件字节已变化：' + path)

        def refs(value):
            self._require(isinstance(value, list) and bool(value)
                          and all(isinstance(ref, str) and ref in pins for ref in value), '审阅或行情引用未绑定来源')

        admission = bundle.get('admission')
        self._require(isinstance(admission, dict) and admission.get('status') == 'ACCEPTED_CONDITIONAL_RESEARCH_INPUT',
                      '输入尚未获得显式来源审阅接纳：UNAVAILABLE')
        self._require(isinstance(admission.get('reviewer'), str) and admission['reviewer'].strip(), '缺少来源审阅者')
        reviewed = datetime.fromisoformat(admission['reviewed_at'])
        self._require(reviewed.tzinfo is not None, '审阅时间须有时区')
        refs(admission.get('evidence_references'))
        limits = admission.get('limitations')
        self._require(isinstance(limits, list) and limits and all(isinstance(item, str) and item.strip() for item in limits),
                      '条件输入必须明确保留限制')
        self._require(isinstance(bundle['valuation_quotes'], list)
                      and isinstance(bundle['held_unit_continuity'], dict), '缺少明确报价或单位连续性输入')
        for quote in bundle['valuation_quotes']:
            refs(quote['source_references'])
        for declaration in bundle['held_unit_continuity'].values():
            refs(declaration['source_references'])
        for key in ('market_session', 'decision_session'):
            session = bundle[key]
            references = session.get('source_references', [])
            self._require(isinstance(references, list), '交易时段来源引用无效')
            refs(references + ([session['source']] if 'source' in session else []))
        validate_successor_time_chain(bundle, root=self.root)
        return bundle


DEFAULT_INPUT_PROVIDER = SuccessorInputLoader()
