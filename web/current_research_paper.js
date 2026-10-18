(function (root) {
  'use strict';
  const VERSIONS = new Set(['CURRENT_FRESH_QUANTITY_V1_BOUNDED_8192_NO_46_RULES', 'CURRENT_SEALED_TOP1_V1_CASH_FLOOR_NO_RESELECTION']);
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function amount(value) {
    const text = String(value);
    if (!/^\d+(?:\.\d+)?(?:\/\d+)?$/.test(text) || text.length > 160) throw Error('金额格式无效');
    const parts = text.split('/');
    const number = Number(parts[0]) / (parts.length === 2 ? Number(parts[1]) : 1);
    if (!Number.isFinite(number) || number < 0) throw Error('金额超出显示范围');
    return number.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
  }
  function create(doc, fetcher, uuid, chartsApi = root.SelectedStockCharts) {
    let research = null, payload = null, binding = null, epoch = 0, busy = false, controller = null;
    let proposal = null, errorMessage = '';
    let chartController = null, performanceController = null;
    function clearPerformance() { if(performanceController) performanceController.destroy(); performanceController=null; }
    function clearCharts() { if(chartController) chartController.destroy(); chartController=null; }
    const details = doc.getElementById('researchPaperDetails');
    const body = doc.getElementById('researchPaperBody');
    const intraday = root.ResearchIntraday && root.ResearchIntraday.create(doc.getElementById('researchIntradayBody'),fetcher);
    const intradayPaper = root.ResearchIntradayPaper && root.ResearchIntradayPaper.create(doc.getElementById('intradayPaperDetails'),doc.getElementById('intradayPaperBody'),fetcher,uuid,open=>{if(intraday) intraday.setOpen(details.open && !open);});
    function invalidate() {
      clearPerformance();
      if(intradayPaper) intradayPaper.invalidate();
      if(intraday) intraday.invalidate();
      clearCharts();
      epoch++; if (controller) controller.abort(); controller = null;
      research = null; payload = null; binding = null; busy = false;
      proposal = null; errorMessage = '';
      body.textContent = '研究现金或版本已变化，请重新读取候选后展开。';
    }
    function validate(data) {
      const p = data && data.plan, r = data && data.review;
      if (!data || data.genesis_research_id !== research.research_id ||
          typeof data.genesis_plan_id !== 'string' || !/^[a-f0-9]{64}$/.test(data.genesis_plan_id) ||
          data.account_id !== 'paper-' + data.genesis_plan_id.slice(0,24) ||
          (binding && (data.account_id !== binding.account_id || data.genesis_plan_id !== binding.genesis_plan_id ||
                       data.genesis_research_id !== binding.genesis_research_id))) throw Error('模拟账户初始谱系不一致');
      if (!p || data.research_only !== true || data.execution_blocked !== true || !data.market_session || data.market_session.date !== p.active_date ||
          !/^[a-f0-9]{24}$/.test(p.research_id) || p.research_only !== true || p.execution_blocked !== true || p.adopted !== false ||
          typeof p.plan_id !== 'string' || typeof data.account_id !== 'string' || !Array.isArray(p.orders) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(p.active_date)) throw Error('模拟计划版本或安全标记不一致');
      [p.available_cash,p.reserved_cash,p.unreserved_cash].forEach(amount);
      p.orders.forEach(o => { if (!['BUY','SELL'].includes(o.side) || !Number.isSafeInteger(o.quantity) || o.quantity <= 0 || typeof o.order_id !== 'string') throw Error('订单格式无效'); amount(o.limit); });
      if (r && (r.plan_id !== p.plan_id || r.research_id !== p.research_id || r.account_id !== data.account_id ||
          r.research_only !== true || r.execution_blocked !== true || r.adopted !== false || typeof r.revision !== 'string' || !Array.isArray(r.orders))) throw Error('模拟账户版本不一致');
      if (r) { [r.cash,r.reserved_cash,r.unreserved_cash,r.total_recorded_fees].forEach(amount);
        r.orders.forEach(o => { if (!p.orders.some(x => x.order_id === o.order_id) || !Number.isSafeInteger(o.filled_quantity) || !Number.isSafeInteger(o.unfilled_quantity) || o.filled_quantity < 0 || o.unfilled_quantity < 0) throw Error('模拟成交数量无效'); }); }
      const market = data.market_review;
      if (market) {
        if (!r || market.plan_id !== p.plan_id || market.research_id !== p.research_id || market.revision !== r.revision ||
            !Array.isArray(market.orders) || market.orders.length !== p.orders.length ||
            new Set(market.orders.map(o => o.order_id)).size !== p.orders.length ||
            !market.orders.every(o => {
              const recorded = r.orders.find(x => x.order_id === o.order_id);
              return p.orders.some(x => x.order_id === o.order_id) && recorded &&
                ['YES','NO','UNKNOWN'].includes(o.observed_touch) && o.filled_quantity === recorded.filled_quantity &&
                o.unfilled_quantity === recorded.unfilled_quantity && o.order_status === recorded.order_status;
            })) throw Error('触价复盘版本或订单不一致');
      }
      if (!r && (p.research_id !== data.genesis_research_id || p.plan_id !== data.genesis_plan_id)) throw Error('未开启模拟计划与初始谱系不一致');
      return data;
    }
    async function request(path, data) {
      if (busy || !research) return;
      const successorPreview = path.startsWith('successor/input?');
      const expectedAccount = payload && payload.account_id, expectedRevision = payload && payload.review && payload.review.revision;
      proposal = null; errorMessage = '';
      busy = true; const token = epoch; controller = new AbortController(); render();
      try {
        const fetchJSON = async (endpoint, content) => {
        const response = await fetcher('/api/research_paper/' + endpoint, {method:content === undefined ? 'GET':'POST', signal:controller.signal,
          cache:'no-store', headers:{'Content-Type':'application/json'}, ...(content === undefined ? {}:{body:JSON.stringify(content)})});
        const result = await response.json();
        if (!response.ok) throw Error(result.detail || result.reason || result.message || '模拟请求失败，请重新读取');
        return result;
        };
        let result = await fetchJSON(path, data);
        if (token !== epoch) return;
        if (successorPreview) {
          if (result.account_id !== expectedAccount || result.expected_revision !== expectedRevision || result.current_revision !== expectedRevision || result.parent_plan_id !== payload.plan.plan_id || typeof result.input_id !== 'string' || !result.input_id || result.research_only !== true || result.execution_blocked !== true) throw Error('后续输入账户版本不一致');
          const inputId=result.input_id;
          result=await fetchJSON('successor/preview',{account_id:expectedAccount,input_id:inputId,expected_revision:expectedRevision});
          if(token!==epoch) return;
          validateProposal(result,expectedAccount,expectedRevision,inputId);
          proposal=result;
        } else {
        payload = validate(result);
        binding = {account_id:payload.account_id,genesis_plan_id:payload.genesis_plan_id,genesis_research_id:payload.genesis_research_id};
        }
      } catch (error) {
        if (token !== epoch) return;
        errorMessage = successorPreview && /后续决策输入登记尚不存在|没有匹配账户版本的后续输入|未登记的后续决策输入/.test(error.message)
          ? '尚无已核对的后续交易日行情，当前计划保持不变。'
          : '请求未完成：' + error.message + '。可恢复读取确认状态，不会自动重试写入。';
      } finally { if (token === epoch) { busy = false; controller = null; } }
      if (token === epoch) render();
    }
    function validateProposal(value,account,revision,inputId) {
      const p=value.plan,m=value.market_session;
      if(value.account_id!==account || value.current_revision!==revision || value.expected_revision!==revision || value.input_id!==inputId ||
         typeof value.preview_id!=='string' || !value.preview_id || value.research_only!==true || value.execution_blocked!==true ||
         !p || p.account_revision!==revision || p.research_only!==true || p.execution_blocked!==true || p.adopted!==false ||
         !/^[a-f0-9]{64}$/.test(p.plan_id) || !/^[a-f0-9]{24}$/.test(p.research_id) || p.plan_id===payload.plan.plan_id ||
         !/^\d{4}-\d{2}-\d{2}$/.test(p.signal_asof) || !/^\d{4}-\d{2}-\d{2}$/.test(p.active_date) || p.signal_asof<payload.plan.active_date || p.active_date<=p.signal_asof ||
         !m || m.date!==p.active_date || m.timezone!=='America/New_York' || !String(m.open_at).startsWith(p.active_date+'T') || !String(m.close_at).startsWith(p.active_date+'T') ||
         !/[+-]\d{2}:\d{2}$/.test(m.open_at) || !/[+-]\d{2}:\d{2}$/.test(m.close_at) || !(Date.parse(m.open_at)<Date.parse(m.close_at)) ||
         !Array.isArray(p.orders) || !p.target_quantities || !['ROLL','RESELECT'].includes(value.route && value.route.action)) throw Error('后续草案版本或交易日不一致');
      [p.available_cash,p.reserved_cash,p.unreserved_cash].forEach(amount);
      if(!Object.values(p.target_quantities).every(q=>Number.isSafeInteger(q)&&q>=0) || new Set(p.orders.map(o=>o.order_id)).size!==p.orders.length) throw Error('后续目标数量无效');
      p.orders.forEach(o=>{if(!['BUY','SELL'].includes(o.side)||!Number.isSafeInteger(o.quantity)||o.quantity<=0||typeof o.order_id!=='string') throw Error('后续订单无效');amount(o.limit);});
    }
    function render() {
      clearPerformance();
      clearCharts();
      if (!payload) { body.textContent = errorMessage || (busy ? '正在读取条件纸面计划…' : '展开后读取条件纸面计划。'); return; }
      const p=payload.plan, r=payload.review;
      body.innerHTML = '<p class="preview-caption">封存模拟计划 · 不是当前实盘挂单建议，价格不随盘中更新，不写入真实账户。触价未知，不能视为成交。佣金已确认 0；其他费用未知，每次模拟成交须明确填写费用。</p>' +
        (errorMessage ? '<p class="info-strip">'+esc(errorMessage)+'</p>' : '') +
        (proposal ? '<div class="info-strip"><strong>后续模拟草案 · '+(proposal.route.action==='ROLL'?'月内目标不变':'月度重新选择')+'</strong><p>有效日 '+esc(proposal.plan.active_date)+' · 尚未采用</p><p>目标股数：'+esc(Object.entries(proposal.plan.target_quantities).map(([sid,q])=>((proposal.plan.causal_inputs && proposal.plan.causal_inputs.securities && proposal.plan.causal_inputs.securities[sid]) || sid)+': '+q).join('，'))+'</p>'+proposal.plan.orders.map(o=>'<p>'+esc(o.ticker || o.security_id)+' '+esc(o.side)+' · '+o.quantity+' 股 · 限价 $'+amount(o.limit)+'</p>').join('')+'<button class="btn btn-small" data-action="adopt">采用此模拟计划</button></div>' : '') +
        '<p>决策日：'+esc(p.signal_asof || (p.causal_inputs && p.causal_inputs.decision_date) || '未标注')+' · 适用日：'+esc(p.active_date)+' · '+esc(payload.market_session.timezone)+' · '+esc(payload.market_session.open_at)+' 至 '+esc(payload.market_session.close_at)+' · 计划版本 '+esc(p.plan_id.slice(0,12))+'</p>' +
        '<p>现金 $'+amount(r ? r.cash:p.available_cash)+' · 预留 $'+amount(r ? r.reserved_cash:p.reserved_cash)+' · 未预留 $'+amount(r ? r.unreserved_cash:p.unreserved_cash)+'</p>' +
        '<div class="preview-table-wrap"><table class="preview-table"><thead><tr><th>股票 / 方向</th><th>封存模拟限价</th><th>计划数量</th><th>已填 / 未填</th><th>状态</th></tr></thead><tbody>' +
        p.orders.map(o => { const row=r && r.orders.find(x=>x.order_id===o.order_id); return '<tr><td>'+esc(o.ticker || o.security_id)+' / '+esc(o.side)+'</td><td>$'+amount(o.limit)+'</td><td>'+o.quantity+'</td><td>'+ (row ? row.filled_quantity+' / '+row.unfilled_quantity:'—')+'</td><td>'+esc(row ? row.order_status:'未开启模拟')+'</td></tr>'; }).join('')+'</tbody></table></div>' +
        (payload.market_review ? '<p class="preview-footnote">同版本行情复盘 · 观察截至 '+esc(payload.market_review.observed_through || '未知')+'。日线触价不代表成交；不知道盘中撤单前后顺序，不计算假收益。</p><div class="preview-table-wrap"><table class="preview-table"><thead><tr><th>股票</th><th>当日行情触价</th><th>已录成交</th><th>状态</th></tr></thead><tbody>'+payload.market_review.orders.map(o=>{
          const order=p.orders.find(x=>x.order_id===o.order_id);
          const reason={ORDER_SESSION_AFTER_OBSERVATION_CUTOFF:'尚无该交易日的完整行情',MATCHING_COMPLETED_SESSION_BAR_MISSING:'缺少对应交易日行情',COMPLETED_DAILY_RANGE_ONLY:'仅按当日高低价判断'}[o.reason] || '行情状态待核';
          return '<tr><td>'+esc(order.ticker || order.security_id)+'</td><td>'+({'YES':'是','NO':'否','UNKNOWN':'待完整行情'}[o.observed_touch])+'<br><small>'+reason+'</small></td><td>'+o.filled_quantity+'</td><td>'+esc(o.order_status)+'</td></tr>';
        }).join('')+'</tbody></table></div>' : '') +
        (r ? '<p>模拟持股：'+esc(Object.entries(r.shares).map(([s,q])=>s+': '+q).join('，') || '无')+' · 累计已录费用 $'+amount(r.total_recorded_fees)+'</p><button class="btn btn-small" data-action="restore">恢复读取</button><button class="btn btn-small" data-action="review">查看本计划触价复盘</button><button class="btn btn-small" data-action="successor">预览后续计划</button>' : '<button class="btn btn-small" data-action="start">开启模拟记录</button>') +
        (r && r.orders.some(o=>o.order_status==='OPEN') ? '<form id="paperFillForm" class="planner-controls"><label>模拟订单<select name="order">'+p.orders.filter(o=>r.orders.some(x=>x.order_id===o.order_id && x.order_status==='OPEN')).map(o=>'<option value="'+esc(o.order_id)+'">'+esc(o.ticker || o.security_id)+' '+o.side+'</option>').join('')+'</select></label><label>整股数量<input name="qty" type="number" min="1" step="1" required></label><label>成交价<input name="price" type="number" min="0.000001" step="any" required></label><label>实际费用（必填）<input name="fees" type="number" min="0" step="any" required></label><label>发生交易日<input name="session" type="date" value="'+esc(p.active_date)+'" required></label><button class="btn btn-small" type="submit">记录模拟成交</button><button class="btn btn-small" type="button" data-action="cancel">取消所选模拟单</button><button class="btn btn-small" type="button" data-action="expire">确认所选单当日已结束并到期</button></form><p class="preview-footnote">到期需服务器确认收盘；只释放未填预留，不变更已记现金或持股。</p>':'') +
        (r ? '<details class="preview-chart-details" id="paperPerformanceDetails"><summary>已录模拟表现</summary><div id="paperPerformanceBody"></div></details>' : '') +
        (r ? '<details class="preview-chart-details" id="paperPlanCharts"><summary>当前模拟计划 K 线 · 正目标与实际模拟持股</summary><div id="paperPlanChartBody"></div></details>' : '');
      if(r && root.ResearchPaperPerformance) {
        const performanceDetails=body.querySelector('#paperPerformanceDetails');
        if(performanceDetails) performanceController=root.ResearchPaperPerformance.create(performanceDetails,body.querySelector('#paperPerformanceBody'),fetcher,{account_id:payload.account_id,revision:r.revision,plan_id:p.plan_id,genesis_research_id:payload.genesis_research_id});
      }
      body.querySelectorAll('button,input,select').forEach(el=>{el.disabled=busy;});
      body.querySelectorAll('[data-action]').forEach(el=>el.addEventListener('click',()=>act(el.dataset.action)));
      const form=body.querySelector('#paperFillForm');
      if(form) form.addEventListener('submit',event=>{event.preventDefault();if(form.reportValidity()) act('fill');});
      const chartDetails=body.querySelector('#paperPlanCharts');
      if(chartDetails) chartDetails.addEventListener('toggle',()=>{
        clearCharts();if(!chartDetails.open || busy) return;
        const container=body.querySelector('#paperPlanChartBody');
        if(!chartsApi) {container.textContent='K线组件暂不可用';return;}
        const securities=p.causal_inputs && p.causal_inputs.securities;
        const ids=[...new Set([...Object.entries(p.target_quantities || {}),...Object.entries(r.shares)].filter(([,q])=>q>0).map(([sid])=>sid))];
        if(!securities || ids.some(sid=>!securities[sid])) {container.textContent='当前计划缺少证券身份，无法读取K线';return;}
        const byTicker=new Map(ids.map(sid=>[securities[sid],sid]));
        const captured=payload, token=epoch;
        chartController=chartsApi.createSelectedStockCharts(container,async(ticker,interval,signal)=>{
          const sid=byTicker.get(ticker);
          const query=new URLSearchParams({account_id:captured.account_id,expected_plan_id:p.plan_id,security_id:sid,interval});
          const response=await fetcher('/api/research_paper/bars?'+query,{signal,cache:'no-store'});
          const value=await response.json();
          if(token!==epoch || payload!==captured || signal.aborted) throw Error('图表计划已失效');
          if(!response.ok) return {ticker,status:'UNAVAILABLE',reason:value.message || '当前计划来源不可用，无替代图表'};
          if(value.account_id!==captured.account_id || value.plan_id!==p.plan_id || value.research_id!==p.research_id || value.security_id!==sid || value.ticker!==ticker || value.interval!==interval || value.daily_as_of!==p.signal_asof || value.research_only!==true || value.execution_blocked!==true) throw Error('图表版本不一致');
          return value;
        });
        chartController.setSelection({label:'计划内封存原始历史价格坐标；未认证全段名义股数口径，不绘制限价线。仅截至决策日。',stocks:ids.map(sid=>({ticker:securities[sid],action:'模拟目标 '+(p.target_quantities[sid] || 0)+' 股 / 持有 '+(r.shares[sid] || 0)+' 股'}))});
      });
    }
    function act(action) {
      if(busy || !payload || !research) return;
      if(action==='successor' && payload.review) return request('successor/input?account_id='+encodeURIComponent(payload.account_id)+'&expected_revision='+encodeURIComponent(payload.review.revision));
      if(action==='adopt' && proposal && payload.review) return request('successor/activate',{account_id:payload.account_id,preview_id:proposal.preview_id,event_id:uuid(),expected_revision:payload.review.revision});
      if(action==='start') return request('start',{research_id:research.research_id,expected_plan_id:payload.plan.plan_id});
      if(action==='restore') return request('account?account_id='+encodeURIComponent(payload.account_id));
      if(action==='review') return request('review?account_id='+encodeURIComponent(payload.account_id));
      const form=body.querySelector('#paperFillForm'), r=payload.review;
      if(!form || !r) return;
      const value=name=>form.elements.namedItem(name).value;
      const event={event_id:uuid(),mode:'PAPER_MANUAL_FILL',plan_id:payload.plan.plan_id,order_id:value('order'),expected_revision:r.revision};
      if(action==='fill') { const qty=Number(value('qty')); if(!Number.isSafeInteger(qty) || qty<=0 || !value('fees').trim() || !value('price').trim()) return;
        Object.assign(event,{qty,price:value('price'),fees:value('fees'),session:value('session')});
      } else { event.event_type=action==='cancel'?'CANCEL':'EXPIRE'; if(action==='expire') event.completed_session=payload.plan.active_date; }
      return request(action==='fill'?'fill':'order',{account_id:payload.account_id,event});
    }
    function setResearch(data) {
      invalidate();
      if(data && data.research_version === 'CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH') {
        body.textContent = '此处保留旧版本模拟计划。V2 请使用“新组合限价与模拟记录”；旧版本限价已撤下。';
        return;
      }
      if(!data || !VERSIONS.has(data.research_version) || data.research_only!==true || data.execution_blocked!==true || !/^[a-f0-9]{24}$/.test(data.research_id)) return;
      research=data; if(intradayPaper) intradayPaper.setParentOpen(details.open); if(intraday) intraday.setOpen(details.open && !(intradayPaper && intradayPaper.isOpen())); if(intradayPaper) intradayPaper.setResearch(data); if(intraday) intraday.setResearch(data); if(details.open) request('preview',{research_id:data.research_id});
    }
    details.addEventListener('toggle',()=>{if(intraday) intraday.setOpen(details.open && !(intradayPaper && intradayPaper.isOpen()));if(intradayPaper){intradayPaper.setParentOpen(details.open);if(!details.open)intradayPaper.suspend();else if(research&&intradayPaper.isOpen())intradayPaper.setResearch(research);}if(details.open && research && !busy) request('preview',{research_id:research.research_id});});
    if(intraday) intraday.setOpen(details.open && !(intradayPaper && intradayPaper.isOpen()));
    return {setResearch,invalidate};
  }
  if(typeof module!=='undefined' && module.exports) module.exports={create,amount};
  if(root.document) root.ResearchPaper=create(root.document,root.fetch.bind(root),()=>root.crypto.randomUUID());
})(typeof window!=='undefined'?window:globalThis);
