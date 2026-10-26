(function () {
  'use strict';
  const statusNames = { pending: '待分析', unanalyzed: '未分析', not_analyzed: '未分析', completed: '已分析', analyzed: '已分析', cached: '已分析（缓存）', failed: '分析失败', skipped: '未分析', unavailable: '不可用', ready: '结果可用', empty: '暂无结果' };
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
  function renderEvent(event, requestedModel) {
    const card = element('article', undefined, 'event');
    const tags = element('div', undefined, 'tags');
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
      const importanceNames = { high: '高', medium: '中', low: '低', unknown: '未判断' };
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
      const response = await fetch('/api/news/latest', { method: 'GET', cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (!data || data.schema_version !== 'news-desk-v1' || !Array.isArray(data.events)) throw new Error('新闻结果版本或格式无效');
      const container = document.getElementById('events'); container.replaceChildren();
      data.events.forEach(event => { if (event && typeof event === 'object') container.append(renderEvent(event, (data.analysis_summary || {}).model || data.model)); });
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
      status.className = 'status error'; status.textContent = '读取失败：' + (error.name === 'AbortError' ? '请求超时' : error.message) + '。可稍后刷新。';
      if (!document.getElementById('events').childElementCount) {
        document.getElementById('empty').hidden = false;
        document.getElementById('empty-title').textContent = '暂时无法读取新闻';
        document.getElementById('empty-message').textContent = '未加载新闻结果，请检查服务后重试。';
      } else status.textContent += ' 下方保留上次读取结果。';
    } finally { clearTimeout(timeout); button.disabled = false; }
  }
  function jobLabel(status) {
    return { IDLE: '暂无分析任务', RUNNING: '正在采集并分析，当前保留已有新闻。', SUCCEEDED: '任务完成，正在读取结果；各条分析状态以结果为准。', FAILED: '本次任务失败，已保留原有新闻。' }[status] || '任务状态未知';
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
  if (typeof module !== 'undefined') module.exports = { safeUrl, text, timeLabel, jobLabel };
  if (typeof document !== 'undefined') {
    document.getElementById('refresh').addEventListener('click', refresh);
    document.getElementById('analyze').addEventListener('click', startAnalysis);
    refresh();
  }
})();
