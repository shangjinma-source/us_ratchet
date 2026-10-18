/* Selected publication only: no discovery, account reads, orders or provider fallback. */
(function (global) {
  'use strict';
  function fillNumber(value) {
    const parts=String(value??'').split('/');
    const number=Number(parts[0])/(parts.length===2?Number(parts[1]):1);
    return parts.length<=2&&Number.isFinite(number)&&number>0?number:NaN;
  }
  function fillDay(value) {
    if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)||!Number.isFinite(Date.parse(value)))return null;
    const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(value));
    const get=type=>parts.find(p=>p.type===type).value;
    return `${get('year')}-${get('month')}-${get('day')}`;
  }
  function periodKey(day,interval) {
    if(interval==='month')return day.slice(0,7);
    if(interval==='week'){const date=new Date(day+'T00:00:00Z');date.setUTCDate(date.getUTCDate()-(date.getUTCDay()+6)%7);return date.toISOString().slice(0,10);}
    return day;
  }
  function mapFills(bars,fills,interval='day') {
    const mapped=[],outside=[],invalid=[];
    for(const fill of fills||[]){
      const day=fillDay(fill.executed_at),price=fillNumber(fill.price),quantity=fillNumber(fill.quantity);
      if(!day||!Number.isFinite(price)||!Number.isFinite(quantity)||!['BUY','SELL'].includes(fill.side)){invalid.push(fill);continue;}
      const index=bars.findIndex(bar=>periodKey(bar.date,interval)===periodKey(day,interval)&&day>=(bar.first_date||bar.date)&&day<=bar.date);
      const item={...fill,day,price,quantity,index};
      (index<0?outside:mapped).push(item);
    }
    return {mapped,outside,invalid};
  }
  const escapeText = value => String(value).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  const averages = [{period:5,color:'#c65b28'},{period:20,color:'#168bba'},{period:60,color:'#9c4ac5'},{period:120,color:'#b38a05'}];
  function movingAverage(bars, period) {
    let sum=0;
    return bars.map((bar,index)=>{sum+=bar.close;if(index>=period)sum-=bars[index-period].close;return index+1>=period?sum/period:null;});
  }
  function quoteLabel(quote) {
    if(!quote || !Number.isFinite(quote.price) || quote.price<=0 || typeof quote.as_of!=='string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(quote.as_of) || !Number.isFinite(Date.parse(quote.as_of)))return '';
    const session={PRE:'盘前价',PRE_MARKET:'盘前价',PREMARKET:'盘前价',REGULAR:'盘中价',REGULAR_MARKET:'盘中价',POST:'盘后价',POST_MARKET:'盘后价',AFTER_HOURS:'盘后价'}[String(quote.session||'').toUpperCase()]||'报价';
    return `${session} $${quote.price.toFixed(2)} · ${quote.as_of}`;
  }
  function candleSvg(bars, limit, interval, fills=[], options={}) {
    if (!Array.isArray(bars) || !bars.length) return '';
    const allBars=options.allBars||bars, start=options.start||0;
    if (allBars.length > 260 || bars.length>260) throw new Error('Too many chart bars');
    const valid = allBars.every(b => ['open', 'high', 'low', 'close'].every(k => Number.isFinite(b[k]) && b[k] > 0)
      && b.low <= Math.min(b.open, b.close) && b.high >= Math.max(b.open, b.close));
    if (!valid || start<0 || start+bars.length>allBars.length || bars.some((bar,index)=>bar!==allBars[start+index])) throw new Error('Invalid actual OHLC');
    const series=averages.map(item=>({...item,values:movingAverage(allBars,item.period).slice(start,start+bars.length)}));
    const prices = bars.flatMap(b => [b.low, b.high]);
    const markers=mapFills(bars,fills,interval).mapped;
    prices.push(...markers.map(fill=>fill.price),...series.flatMap(item=>item.values.filter(value=>value!==null)));
    const latest=allBars[allBars.length-1];
    prices.push(latest.close);
    if (Number.isFinite(limit) && limit > 0) prices.push(limit);
    const low = Math.min(...prices), high = Math.max(...prices), padding=(high-low||high*0.02)*0.10;
    const minimum=low-padding,maximum=high+padding,span=maximum-minimum;
    const y = price => 300 - (price - minimum) / span * 235;
    const step = 590 / bars.length, width = Math.max(1, Math.min(9, step * 0.65));
    const x = index => 15+step*(index+0.5);
    const candles = bars.map((bar, index) => {
      const color = bar.close >= bar.open ? '#d65353' : '#31a381';
      const title = `${bar.date} 开 ${bar.open} 高 ${bar.high} 低 ${bar.low} 收 ${bar.close}`;
      return `<g><title>${escapeText(title)}</title><line x1="${x(index)}" y1="${y(bar.high)}" x2="${x(index)}" y2="${y(bar.low)}" stroke="${color}"/><rect x="${x(index)-width/2}" y="${Math.min(y(bar.open), y(bar.close))}" width="${width}" height="${Math.max(1, Math.abs(y(bar.open)-y(bar.close)))}" fill="${color}"/></g>`;
    }).join('');
    const priceDigits = Math.min(8, Math.max(2, Math.ceil(-Math.log10(span / 5)) + 1));
    const priceLabel = price => price.toLocaleString('en-US', {minimumFractionDigits:priceDigits,maximumFractionDigits:priceDigits});
    const priceAxis = Array.from({length: 6}, (_, index) => {
      const price = minimum + span * index / 5, position = y(price);
      return `<line x1="15" x2="605" y1="${position}" y2="${position}" stroke="currentColor" opacity="0.09"/><text x="615" y="${position}" dominant-baseline="middle" fill="currentColor" font-size="11">${priceLabel(price)}</text>`;
    }).join('');
    const paths=series.map(item=>{const points=item.values.map((value,index)=>value===null?'':`${x(index)},${y(value)}`).filter(Boolean).join(' ');return points?`<polyline class="moving-average ma-${item.period}" points="${points}" fill="none" stroke="${item.color}" stroke-width="1.3"/>`:'';}).join('');
    const legend=series.map((item,index)=>{const value=item.values[item.values.length-1];return `<text x="${15+index*147}" y="44" fill="${item.color}" font-size="11">MA${item.period}: ${value===null?'不足'+item.period+'根':priceLabel(value)}</text>`;}).join('');
    const line = Number.isFinite(limit) && limit > 0
      ? `<line x1="15" x2="605" y1="${y(limit)}" y2="${y(limit)}" stroke="#d7ad53" stroke-dasharray="5 4"><title>建议限价 $${limit}</title></line>` : '';
    const closeLine=`<line class="historical-close-reference" x1="15" x2="605" y1="${y(latest.close)}" y2="${y(latest.close)}" stroke="#728393" stroke-dasharray="4 4"><title>${escapeText(latest.date)} 历史收盘 $${latest.close}，非实时</title></line>`;
    const period = {day: '日线', week: '周线', month: '月线'}[interval] || '日线';
    const extreme=(key,label,offset)=>{const value=Math[key==='high'?'max':'min'](...bars.map(bar=>bar[key])),index=bars.findIndex(bar=>bar[key]===value),position=x(index),left=position>450;return `<text class="visible-${key}" x="${position+(left?-7:7)}" y="${y(value)+offset}" text-anchor="${left?'end':'start'}" fill="currentColor" font-size="10">${label} ${priceLabel(value)}</text>`;};
    const markerSvg=markers.map(fill=>{const position=y(fill.price),label=fill.side==='BUY'?'B':'S',color=fill.side==='BUY'?'#0987da':'#dc9b13',badgeY=Math.max(66,position-23);return `<g class="actual-fill-reference"><title>${escapeText(fill.day)} ${fill.side==='BUY'?'买入':'卖出'} ${fill.quantity} 股 @ $${fill.price}；成交价与历史坐标未核验</title><circle cx="${x(fill.index)}" cy="${position}" r="3.5" fill="white" stroke="${color}" stroke-width="1.5"/><path d="M ${x(fill.index)-7} ${badgeY-11} h 14 v 15 h -5 l -2 4 l -2 -4 h -5 Z" fill="${color}"/><text x="${x(fill.index)}" y="${badgeY}" text-anchor="middle" fill="white" font-size="11" font-weight="700">${label}</text></g>`;}).join('');
    const heading=quoteLabel(options.quote)||`历史收盘 $${priceLabel(latest.close)} · ${latest.date} · 非实时`;
    return `<svg viewBox="0 0 710 330" role="img" aria-label="实际${period} OHLC 蜡烛图，红涨绿跌，右侧为美元价格纵轴" style="width:100%;height:auto"><text x="15" y="17" fill="currentColor" font-size="12" font-weight="600">${escapeText(heading)}</text><text x="615" y="44" fill="currentColor" font-size="11">价格 USD</text><text x="15" y="325" fill="currentColor" font-size="10">${escapeText(bars[0].date)}</text><text x="605" y="325" text-anchor="end" fill="currentColor" font-size="10">${escapeText(bars[bars.length-1].date)}</text>${legend}${priceAxis}${closeLine}${candles}${paths}${line}${extreme('high','高',-8)}${extreme('low','低',16)}${markerSvg}<title>MA 按完整已加载${period}收盘计算；当前周期均线；虚线为 ${escapeText(latest.date)} 历史收盘</title></svg>`;
  }

  function createSelectedStockCharts(container, loadBars) {
    let generation = 0, observer = null, controllers = [], cleanups = [], fillUpdates=[], currentFills=[];
    function clear() {
      generation += 1;
      if (observer) observer.disconnect();
      controllers.forEach(controller => controller.abort());
      controllers = [];
      cleanups.forEach(cleanup => cleanup()); cleanups = [];
      fillUpdates=[];
      container.replaceChildren();
    }
    function setSelection(publication) {
      clear();
      if (!publication || !Array.isArray(publication.stocks) || !publication.stocks.length) {
        container.textContent = '新组合待发布，暂无选中股票 K 线。';
        return;
      }
      const currentGeneration = generation;
      const label = document.createElement('p');
      label.textContent = publication.label || '已发布组合';
      container.append(label);
      observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => {
        entries.forEach(entry => { if (entry.isIntersecting) { observer.unobserve(entry.target); entry.target.loadChart(); } });
      }, {rootMargin: '100px'}) : null;
      for (const stock of publication.stocks) {
        if (!/^[A-Z0-9][A-Z0-9.\-]{0,14}$/.test(stock.ticker)) throw new Error('Invalid selected ticker');
        const card = document.createElement('article');
        card.style.cssText = 'border:1px solid #6664;border-radius:12px;padding:12px;margin:10px 0;';
        const title = document.createElement('strong'); title.textContent = stock.ticker;
        const advice = document.createElement('p');
        advice.textContent = `${stock.action || '观察'} · 限价 ${Number.isFinite(stock.limit) ? '$'+stock.limit : '待定'} · 当前报价 ${stock.quote && Number.isFinite(stock.quote.price) ? '$'+stock.quote.price+'（'+(stock.quote.as_of || '时间未知')+'）' : '暂无'}${stock.quote && stock.quote.source ? ' · '+stock.quote.source : ''}`;
        if (publication.research_only === true) {
          advice.textContent = `资金占比 ${(stock.target_weight * 100).toFixed(2)}% · 整股候选 ${stock.units} · 保存收盘 $${Number(stock.saved_close).toFixed(2)}`;
        }
        if (publication.monthly_target === true) advice.textContent = `本月目标 ${stock.quantity} 股 · 不等于待买股数`;
        if (publication.recorded_holding === true) advice.textContent = `已录真实持仓 ${stock.quantity} 股 · 历史图不代表策略目标或今日报价`;
        const header = document.createElement('div');
        header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap';
        const periods = document.createElement('div'); periods.setAttribute('role', 'group');
        periods.setAttribute('aria-label', `${stock.ticker} K 线周期`);
        periods.style.cssText = 'display:flex;gap:6px';
        let interval = 'day', allBars = [], start = 0, count = 0, drag = null;
        const buttons = [];
        [['day','日线'], ['week','周线'], ['month','月线']].forEach(([value,text]) => {
          const button = document.createElement('button'); button.type = 'button'; button.textContent = text;
          button.className = 'btn'; button.dataset.period = value;
          button.onclick = () => { if (interval !== value) { interval = value; updateButtons(); load(); } };
          buttons.push(button); periods.append(button);
        });
        function updateButtons() {
          buttons.forEach(button => { const selected = button.dataset.period === interval;
            button.setAttribute('aria-pressed', String(selected));
            button.style.cssText = selected ? 'background:#176b63;color:white;border-color:#176b63' : '';
          });
        }
        updateButtons(); header.append(title, periods);
        const status = document.createElement('p'), chart = document.createElement('div');
        chart.style.cssText = 'touch-action:pan-y;user-select:none;cursor:grab';
        chart.setAttribute('aria-label', `${stock.ticker} K线：拖拽平移，滚轮缩放`);
        const hint = document.createElement('small'); hint.textContent = '拖拽平移 · 滚轮缩放 · MA 按当前日 / 周 / 月周期计算 · 虚线为最新已载历史收盘';
        const fillNote=document.createElement('p');fillNote.setAttribute('aria-label',`${stock.ticker} 真实成交标记`);
        function stockFills(){return currentFills.filter(fill=>stock.security_id?fill.security_id===stock.security_id&&fill.ticker===stock.ticker:fill.ticker===stock.ticker);}
        function draw() {
          const fills=stockFills();
          chart.innerHTML = candleSvg(allBars.slice(start, start + count), stock.limit, interval,fills,{allBars,start,quote:stock.quote});
          const result=mapFills(allBars,fills,interval);
          const notes=[];
          if(result.mapped.length)notes.push('蓝色 B / 黄色 S 为已录真实买入 / 卖出；成交价与历史坐标未核验，仅供对照。');
          if(result.outside.length)notes.push(...result.outside.map(fill=>`${fill.day} ${fill.side==='BUY'?'买入':'卖出'} ${fill.quantity} 股 @ $${fill.price}：成交在当前历史区间外或缺少对应交易日，不标在最后一根 K 线上。`));
          if(result.invalid.length)notes.push(`${result.invalid.length} 笔成交时间或价格不完整，未标注。`);
          fillNote.textContent=notes.join(' ');
        }
        fillUpdates.push(draw);
        function release() {
          if (drag && chart.hasPointerCapture?.(drag.id)) chart.releasePointerCapture(drag.id);
          drag = null; chart.style.cursor = 'grab';
        }
        chart.onpointerdown = event => {
          if (event.button !== 0 || !count) return;
          drag = {id:event.pointerId, x:event.clientX, start};
          chart.setPointerCapture(event.pointerId); chart.style.cursor = 'grabbing';
        };
        chart.onpointermove = event => {
          if (!drag || drag.id !== event.pointerId) return;
          const width = chart.getBoundingClientRect().width * 590 / 710;
          if (width <= 0) return;
          start = Math.max(0, Math.min(allBars.length-count, drag.start-Math.round((event.clientX-drag.x)*count/width)));
          draw();
        };
        chart.onpointerup = chart.onpointercancel = event => { if (drag?.id === event.pointerId) release(); };
        chart.onlostpointercapture = () => { drag = null; chart.style.cursor = 'grab'; };
        const wheel = event => {
          if (!count || !Number.isFinite(event.deltaY) || event.deltaY === 0) return;
          event.preventDefault(); release();
          const box = chart.getBoundingClientRect(); if (box.width <= 0) return;
          const anchor = Math.max(0, Math.min(1, ((event.clientX-box.left)/box.width*710-15)/590));
          const next = Math.max(Math.min(10,allBars.length), Math.min(allBars.length, Math.round(count*(event.deltaY>0?1.2:0.8))));
          start = Math.max(0, Math.min(allBars.length-next, Math.round(start+anchor*(count-next))));
          count = next; draw();
        };
        chart.addEventListener('wheel', wheel, {passive:false});
        cleanups.push(() => { release(); chart.removeEventListener('wheel',wheel); });
        let revision = 0, active = null;
        async function load() {
          if (currentGeneration !== generation) return;
          const requestRevision = ++revision;
          if (active) active.abort();
          active = new AbortController(); controllers.push(active);
          status.textContent = '读取保存行情…'; release(); allBars = []; count = 0; chart.replaceChildren();
          try {
            const data = await loadBars(stock.ticker, interval, active.signal);
            if (currentGeneration !== generation || requestRevision !== revision) return;
            if (data.ticker !== stock.ticker) throw new Error('Ticker response mismatch');
            if (data.status !== 'AVAILABLE') {
              chart.replaceChildren(); status.textContent = data.reason || '本地日线不可用'; return;
            }
            candleSvg(data.bars, stock.limit, interval); // Validate the full response before slicing.
            allBars = data.bars; count = Math.min(60, allBars.length); start = allBars.length-count; draw();
            const basis = data.price_basis || data.adjustment_basis;
            const basisLabel = basis === 'CONDITIONAL_PROVIDER_QUOTE_CLOSE_NOT_AUTHENTICATED_NOMINAL_OR_TOTAL_RETURN' ? '提供方历史报价坐标（非名义或总回报认证）' : basis ? '已提供价格口径，需结合来源说明' : '缓存复权口径未标注';
            status.textContent = `日线截至 ${data.daily_as_of || '未知'}${data.stale ? ' · 缓存滞后' : data.stale === null ? ' · 新鲜度未核验' : ''} · ${basisLabel}${data.last_period_may_be_partial ? ' · 最后一根周/月线可能未完整' : ''}`;
          } catch (error) {
            if (currentGeneration !== generation || requestRevision !== revision || error.name === 'AbortError') return;
            chart.replaceChildren(); status.textContent = '本地 K 线暂不可用';
          }
        }
        card.loadChart = load;
        card.append(header, advice, status, chart, hint,fillNote); container.append(card);
        if (observer) observer.observe(card); else load();
      }
    }
    return {setSelection,setFills(fills){currentFills=Array.isArray(fills)?fills.map(fill=>({...fill})):[];fillUpdates.forEach(update=>update());}, destroy: clear};
  }
  const api = {candleSvg, createSelectedStockCharts,mapFills,movingAverage,quoteLabel};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else global.SelectedStockCharts = api;
})(typeof window !== 'undefined' ? window : globalThis);
