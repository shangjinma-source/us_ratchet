(function () {
  'use strict';
  const statusNames = { pending: '待分析', unanalyzed: '未分析', not_analyzed: '未分析', completed: '已分析', analyzed: '已分析', cached: '已分析（缓存）', failed: '分析失败', skipped: '未分析', unavailable: '不可用', ready: '结果可用', empty: '暂无结果', skipped_metadata_only: '仅申报信息，未分析', skipped_insufficient_text: '内容不足，未分析' };
  function text(value, fallback = '未提供') {
    if (typeof value === 'string' || typeof value === 'number') return String(value) || fallback;
    return fallback;
  }
  function safeUrl(value) {
    try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; }
    catch (_) { return null; }
  }
  function element(tag, value, className) {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = text(value, '');
    if (className) node.className = className;
    return node;
  }
  function timeLabel(value) {
    if (!value) return '未知';
    const parsed = new Date(value);
    return Number.isNaN(parsed.valueOf()) ? '未知（时间格式无效）' : parsed.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) + ' 北京时间';
  }
  function list(parent, title, values, fallback) {
    parent.append(element('div', title, 'section-title'));
    const items = Array.isArray(values) ? values : (values ? [values] : []);
    const ul = element('ul');
    if (!items.length) ul.append(element('li', fallback, 'muted'));
    items.forEach(item => {
      const li = element('li', typeof item === 'object' && item ? text(item.text || item.claim || item.summary, '未提供说明') : text(item));
      const url = item && typeof item === 'object' ? safeUrl(item.url) : null;
      if (url) { const link = element('a', ' 查看来源'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; li.append(link); }
      ul.append(li);
    });
    parent.append(ul);
  }
  function holdingsSnapshot(data) {
    if (!data || data.status !== 'READY' || !data.account || !Array.isArray(data.account.holdings)) return {known:false, tickers:[], unresolved:0};
    const tickers = new Set(); let unresolved = 0;
    data.account.holdings.forEach(row => {
      if (!row || !Number.isSafeInteger(row.quantity) || row.quantity <= 0 || typeof row.ticker !== 'string' || !/^[A-Z0-9][A-Z0-9.-]{0,19}$/.test(row.ticker)) { unresolved++; return; }
      tickers.add(row.ticker);
    });
    return {known:true, tickers:[...tickers], unresolved};
  }
  function relatedTickers(event, holdings) {
    return holdings.known && Array.isArray(event.tickers) ? event.tickers.filter(ticker => holdings.tickers.includes(ticker)) : [];
  }
  function targetSnapshot(data) {
    const unknown = {known:false,tickers:[],rows:[]};
    if (!data || data.status !== 'SAVED_TARGET' || !/^\d{4}-\d{2}$/.test(data.server_month || '') || data.target_month !== data.server_month || !/^[0-9a-f]{64}$/.test(data.target_id || '') || !/^[0-9a-f]{64}$/.test(data.proposal_id || '') || !Array.isArray(data.proposal_targets) || !data.risk_monthly_targets || typeof data.risk_monthly_targets !== 'object' || Array.isArray(data.risk_monthly_targets)) return unknown;
    const rows = [], seen = new Set();
    for (const row of data.proposal_targets) {
      if (!row || typeof row.security_id !== 'string' || !row.security_id || seen.has(row.security_id) || typeof row.ticker !== 'string' || !/^[A-Z0-9][A-Z0-9.-]{0,19}$/.test(row.ticker) || !Number.isSafeInteger(row.quantity) || row.quantity < 0 || !Object.hasOwn(data.risk_monthly_targets,row.security_id) || data.risk_monthly_targets[row.security_id] !== row.quantity) return unknown;
      seen.add(row.security_id);
      if (row.quantity > 0) rows.push({ticker:row.ticker,quantity:row.quantity});
    }
    if (Object.keys(data.risk_monthly_targets).length !== seen.size) return unknown;
    return {known:true,tickers:[...new Set(rows.map(row=>row.ticker))],rows,month:data.target_month};
  }
  function targetLabel(event, targets) {
    const matched = relatedTickers(event,targets);
    return matched.length ? '月目标关注股：' + matched.join('、') + ' · 非当前买入建议' : '';
  }
  function targetCoverageLabels(events,targets) {
    if (!targets.known) return ['当前有效月目标未知。'];
    if (!targets.rows.length) return ['本月已保存提案无正股数目标。'];
    return targets.rows.map(row => row.ticker + ' · 目标 ' + row.quantity + ' 股 · ' + (events.some(event=>relatedTickers(event,targets).includes(row.ticker) && hasBody(event)) ? '本批次有正文片段' : '本批次无正文覆盖'));
  }
  function orderedEvents(events, holdings, targets = {known:false,tickers:[]}) {
    return events.filter(event => event && typeof event === 'object').map((event,index) => ({event,index})).sort((a,b) => Number(relatedTickers(b.event,holdings).length > 0) - Number(relatedTickers(a.event,holdings).length > 0) || Number(relatedTickers(b.event,targets).length > 0) - Number(relatedTickers(a.event,targets).length > 0) || a.index-b.index).map(item => item.event);
  }
  function hasBody(event) {
    return ['ISSUER_RELEASE_BODY','OFFICIAL_RELEASE_BODY'].includes(event.content_kind) && typeof event.source_text === 'string' && event.source_text.trim().length > 0;
  }
  function relationLabel(event, holdings) {
    const related = relatedTickers(event, holdings);
    if (related.length) return '关联已录持仓：' + related.join('、');
    if (event.relevance === 'macro') return '宏观事件 · 非个股持仓结论';
    if (!holdings.known || holdings.unresolved) return '持仓关联尚不能完整确认';
    if (!Array.isArray(event.tickers) || !event.tickers.length) return '股票关联未知';
    return '非已录持仓消息';
  }
  function coverageLabels(events, holdings) {
    if (!holdings.known) return ['持仓读取不可用，不能判断持仓覆盖。'];
    const result = holdings.tickers.map(ticker => {
      const related = events.filter(event => Array.isArray(event.tickers) && event.tickers.includes(ticker));
      return ticker + '：' + (related.some(hasBody) ? '本批次有公告正文片段' : related.length ? '本批次无公告正文，仅有摘要或申报信息' : '本批次无关联消息、无公告正文');
    });
    if (holdings.unresolved) result.push('另有 ' + holdings.unresolved + ' 条持仓无法确认股票代码或数量，覆盖未知。');
    if (!holdings.tickers.length && !holdings.unresolved) result.push('工具当前未记录持仓。');
    return result;
  }
  function renderEvent(event, requestedModel, holdings, targets) {
    const card = element('article', undefined, 'event');
    const tags = element('div', undefined, 'tags');
    tags.append(element('span', relationLabel(event, holdings), 'tag'));
    const targetTag = targetLabel(event,targets); if (targetTag) tags.append(element('span',targetTag,'tag'));
    const state = text(event.analysis_status, '未分析');
    tags.append(element('span', statusNames[state.toLowerCase()] || state, 'tag accent'));
    const tickers = Array.isArray(event.tickers) ? event.tickers : [];
    tickers.forEach(ticker => tags.append(element('span', text(ticker), 'tag')));
    if (!tickers.length) tags.append(element('span', '股票关联未提供', 'tag'));
    card.append(tags, element('h2', text(event.title, '未提供标题')));
    const metadata = element('div', undefined, 'metadata');
    metadata.append(element('span', '发布：' + timeLabel(event.published_at)), element('span', '采集：' + timeLabel(event.collected_at)));
    const source = text(event.source, '来源未提供');
    const url = safeUrl(event.url);
    if (url) { const link = element('a', source); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; metadata.append(link); }
    else metadata.append(element('span', source + ' · 无可用原文链接'));
    card.append(metadata, element('div', ['analyzed', 'cached', 'completed'].includes(state.toLowerCase()) ? '分析摘要' : '来源摘要 · 尚未完成 AI 分析', 'section-title'), element('p', text(event.summary, '尚无摘要；未生成分析结论。')));
    list(card, '证据', event.evidence, '尚无可核验证据。');
    list(card, '不确定性', event.uncertainty, '尚未提供不确定性评估。');
    if (['analyzed', 'cached', 'completed'].includes(state.toLowerCase())) {
      card.append(element('div', '影响机制', 'section-title'), element('p', text(event.mechanism, '尚未提供作用机制。')));
      const importanceNames = { high: '高', medium: '中', low: '低', unknown: '未判断', unclear: '未判断' };
      const info = element('div', undefined, 'metadata');
      const importance = text(event.importance, '未判断');
      info.append(element('span', '重要性：' + (importanceNames[importance.toLowerCase()] || importance)), element('span', '持续时间：' + text(event.horizon, '尚未判断')));
      card.append(info);
    }
    const detail = element('details'); detail.append(element('summary', '分析信息'));
    detail.append(element('p', '模型：' + text(event.model, '尚未记录')), element('p', '分析时间：' + timeLabel(event.analyzed_at)));
    if (!event.model && requestedModel) detail.append(element('p', '计划使用模型：' + text(requestedModel) + '（不代表分析已成功）'));
    card.append(detail); return card;
  }
  async function refresh() {
    const button = document.getElementById('refresh'), status = document.getElementById('status');
    button.disabled = true; status.className = 'status muted'; status.textContent = '正在读取已保存结果…';
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const [response, holdings, targets] = await Promise.all([
        fetch('/api/news/latest', { method: 'GET', credentials:'same-origin', cache: 'no-store', signal: controller.signal }),
        fetch('/api/strategy-account', { method:'GET', credentials:'same-origin', cache:'no-store', signal:controller.signal })
          .then(response => response.ok ? response.json() : null).then(holdingsSnapshot).catch(() => holdingsSnapshot(null)),
        fetch('/api/strategy-account/target', {method:'GET',credentials:'same-origin',cache:'no-store',signal:controller.signal})
          .then(response=>response.ok ? response.json() : null).then(targetSnapshot).catch(()=>targetSnapshot(null))
      ]);
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (!data || data.schema_version !== 'news-desk-v1' || !Array.isArray(data.events)) throw new Error('新闻结果版本或格式无效');
      const container = document.getElementById('events'); container.replaceChildren();
      const events = orderedEvents(data.events, holdings, targets);
      events.forEach(event => container.append(renderEvent(event, (data.analysis_summary || {}).model || data.model, holdings, targets)));
      const targetCoverage = document.getElementById('target-coverage'); targetCoverage.replaceChildren();
      list(targetCoverage,'月目标关注股 · 非当前买入建议',targetCoverageLabels(events,targets),'');
      const coverage = document.getElementById('holdings-coverage'); coverage.replaceChildren();
      list(coverage, '已录持仓的本批次正文覆盖', coverageLabels(events, holdings), '');
      coverage.append(element('p', '仅关联工具已录持仓；按本次读取快照排序。正文片段不代表完整公告或全部新闻覆盖，也不代表风险已排除。账户数据仅在本页使用，不发送给模型。', 'muted'));
      document.getElementById('empty').hidden = container.childElementCount > 0;
      document.getElementById('empty-title').textContent = '暂无新闻结果';
      document.getElementById('empty-message').textContent = text(data.message, '尚未采集或分析，等待后端生成可核验的结果。');
      status.textContent = '已读取 ' + container.childElementCount + ' 条事件 · ' + (statusNames[text(data.status).toLowerCase()] || text(data.status, '状态未提供'));
      document.getElementById('overview').replaceChildren(element('span', '结果更新：' + timeLabel(data.generated_at)), element('span', '模型：' + text(data.model || (data.analysis_summary || {}).model, '尚未记录')));
      const warnings = document.getElementById('warnings'); warnings.replaceChildren();
      const analysis = data.analysis_summary || {};
      if (text(analysis.status, '').toLowerCase() === 'failed') {
        const failureCodes = { CODEX_ANALYSIS_TIMEOUT: '模型分析超时', CODEX_ANALYSIS_FAILED: '模型分析失败', CODEX_NOT_AVAILABLE: '模型服务不可用' };
        const code = text(analysis.message || analysis.error_code, 'ANALYSIS_FAILED');
        const publicCode = /^[A-Z][A-Z0-9_]{1,80}$/.test(code) ? code : 'ANALYSIS_FAILED';
        warnings.append(element('p', (failureCodes[publicCode] || '本次模型分析未完成') + '（' + publicCode + '）。已保留来源摘要，刷新不会重新调用模型。', 'error'));
      }
      if (Array.isArray(data.fetch_errors) && data.fetch_errors.length) list(warnings, '部分来源采集失败', data.fetch_errors.map(item => typeof item === 'object' && item ? text(item.source || item.url, '来源') + '：' + text(item.error || item.message, '采集失败') : item), '');
      if (Array.isArray(data.limitations) && data.limitations.length) list(warnings, '本次结果边界', data.limitations, '');
    } catch (error) {
      document.getElementById('target-coverage').replaceChildren(element('p','本次刷新失败，月目标关联不能确认。','error'));
      document.getElementById('holdings-coverage').replaceChildren(element('p', '本次刷新失败；下方若保留旧消息，其持仓关联与覆盖也是旧快照，请勿视作当前状态。', 'error'));
      status.className = 'status error'; status.textContent = '读取失败：' + (error.name === 'AbortError' ? '请求超时' : error.message) + '。可稍后刷新。';
      if (!document.getElementById('events').childElementCount) {
        document.getElementById('empty').hidden = false;
        document.getElementById('empty-title').textContent = '暂时无法读取新闻';
        document.getElementById('empty-message').textContent = '未加载新闻结果，请检查服务后重试。';
      } else status.textContent += ' 下方保留上次读取结果。';
    } finally { clearTimeout(timeout); button.disabled = false; }
  }
  function jobLabel(status) {
    return { IDLE: '暂无分析任务', RUNNING: '正在采集并分析，当前保留已有新闻。', SUCCEEDED: '采集分析已完成；各条分析状态以结果为准。', FAILED: '本次任务失败，已保留原有新闻。' }[status] || '任务状态未知';
  }
  async function startAnalysis() {
    const button = document.getElementById('analyze'), status = document.getElementById('job-status');
    if (button.disabled) return;
    button.disabled = true; status.className = 'status muted'; status.textContent = '正在请求采集并分析…';
    const deadline = Date.now() + 240000;
    async function request(url, options) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), Math.max(1, Math.min(15000, deadline - Date.now())));
      try { return await fetch(url, { ...options, credentials: 'same-origin', cache: 'no-store', signal: controller.signal }); }
      finally { clearTimeout(timer); }
    }
    try {
      const response = await request('/api/news/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      if (response.status === 409) { status.textContent = '已有分析任务进行中，请稍后读取最新结果。'; return; }
      if (response.status === 429) { status.textContent = '当前处于冷却期或已达到今日预算，请稍后再试。'; return; }
      if (response.status !== 202) throw new Error('HTTP ' + response.status);
      status.textContent = jobLabel('RUNNING');
      while (Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, Math.min(3000, Math.max(0, deadline - Date.now()))));
        if (Date.now() >= deadline) break;
        const poll = await request('/api/news/job', { method: 'GET' });
        if (!poll.ok) throw new Error('HTTP ' + poll.status);
        const job = await poll.json();
        if (!['IDLE', 'RUNNING', 'SUCCEEDED', 'FAILED'].includes(job.status)) throw new Error('任务状态格式无效');
        status.textContent = jobLabel(job.status);
        if (job.status === 'SUCCEEDED' || job.status === 'FAILED') {
          if (job.status === 'FAILED') status.className = 'status error';
          await refresh();
          return;
        }
      }
      status.textContent = '已停止等待（4分钟）。任务可能仍在后端运行，可稍后读取最新结果。';
    } catch (error) {
      status.className = 'status error';
      status.textContent = '无法确认任务状态：' + (error.name === 'AbortError' ? '请求超时' : error.message) + '。未自动重试分析，请稍后读取最新结果。';
    } finally { button.disabled = false; }
  }
  if (typeof module !== 'undefined') module.exports = { safeUrl, text, timeLabel, jobLabel, targetSnapshot, targetLabel, targetCoverageLabels, holdingsSnapshot, relatedTickers, orderedEvents, hasBody, relationLabel, coverageLabels };
  if (typeof document !== 'undefined') {
    document.getElementById('refresh').addEventListener('click', refresh);
    document.getElementById('analyze').addEventListener('click', startAnalysis);
    refresh();
  }
})();

(function(){
  if(typeof document==='undefined')return;
  function node(tag,value){const n=document.createElement(tag);n.textContent=value;return n;}
  async function loadHistory(){
    const box=document.getElementById('history-content');if(!box)return;
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try{
      const response=await fetch('/api/news/history',{method:'GET',cache:'no-store',signal:controller.signal});
      if(!response.ok)throw new Error('unavailable');
      const data=await response.json();box.replaceChildren();
      box.append(node('p','仅展示本机留存观察；入库时间不是新闻最早可得时间。文本不同不代表已证实的更正或真假冲突。'));
      if(data.status==='NO_RECORDED_HISTORY'){box.append(node('p','尚未留存历史；从下次正常采集开始记录，不回填过去。'));return;}
      if(data.status!=='RECORDED_HISTORY'||!data.evidence||!Array.isArray(data.evidence.observations))throw new Error('invalid');
      const e=data.evidence,rows=e.observations;
      box.append(node('p',rows.length+' 条观察；'+e.same_url_groups.filter(g=>g.has_observed_text_variants).length+' 组同链接不同文本；'+e.exact_text_groups.length+' 组跨链接相同片段。'));
      if(data.truncated)box.append(node('p','已达到本次读取上限；较早记录仍保留在本地。'));
      const display=rows.slice(0,50);if(rows.length>50)box.append(node('p','页面仅展开前50条观察。'));
      for(const row of display){
        const detail=node('details','');detail.append(node('summary',row.title||'未提供标题'));
        detail.append(node('p','发布：'+(row.published_at||'未知')+'；采集：'+(row.collected_at||'未知')));
        detail.append(node('p',row.source_text||'未提供原文片段'));
        for(const warning of row.source_uncertainty||[])detail.append(node('p',warning));
        try{const url=new URL(row.url);if(['https:','http:'].includes(url.protocol)&&!url.username&&!url.password){const link=node('a','原始来源');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';detail.append(link);}}catch(_){}
        box.append(detail);
      }
    }catch(_){box.replaceChildren(node('p','历史读取失败，不能视作没有记录。'));}
    finally{clearTimeout(timer);}
  }
  document.getElementById('refresh').addEventListener('click',loadHistory);
  loadHistory();
})();
