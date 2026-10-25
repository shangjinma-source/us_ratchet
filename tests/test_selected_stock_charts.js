const assert = require('node:assert/strict');
const {candleSvg, createSelectedStockCharts} = require('../web/selected_stock_charts.js');
class Element {
  constructor(tag) { this.tag=tag; this.dataset={}; this.listeners={}; this.attrs={}; this.children=[]; this.style={}; this.value=''; this.selectedIndex=0; this.textContent=''; this.innerHTML=''; }
  append(...children) { this.children.push(...children); if (this.tag==='select' && !this.value) this.value=children[0].value; }
  replaceChildren(...children) { this.children=children; this.innerHTML=''; this.textContent=''; }
  setAttribute(k,v) {this.attrs[k]=v;}
  getBoundingClientRect() {return {left:0,width:710};}
  setPointerCapture(id) {this.pointer=id;}
  hasPointerCapture(id) {return this.pointer===id;}
  releasePointerCapture() {this.pointer=null;}
  get options() {return this.children;}
  cloneNode() {const node=new Element(this.tag); node.innerHTML=this.innerHTML; return node;}
  addEventListener(k,f) {assert(!this.listeners[k]);this.listeners[k]=f;}
  removeEventListener(k) {delete this.listeners[k];}
  remove() {this.removed=true;}
  showModal() {this.visible=true;}
  close() {this.visible=false;}
}
global.document={createElement:tag=>new Element(tag),body:new Element('body')};
let observer;
global.IntersectionObserver=class {
  constructor(callback){this.callback=callback;this.targets=[];observer=this;}
  observe(card){this.targets.push(card);}
  unobserve(){}
  disconnect(){this.disconnected=true;}
};
const bars=[{date:'2026-10-01',open:10,high:13,low:9,close:12}, {date:'2026-10-02',open:12,high:14,low:10,close:11}];
function data(ticker) {return {ticker,status:'AVAILABLE',bars,daily_as_of:'2026-10-02',stale:true};}
(async()=>{
  assert.equal((candleSvg(bars,11).match(/<rect/g)||[]).length,2);
  assert.ok(candleSvg(bars,11).includes('stroke-dasharray'));
  assert.throws(()=>candleSvg([{...bars[0],open:NaN}]),/Invalid/);
  const container=new Element('div'), requests=[];
  const component=createSelectedStockCharts(container,(ticker,interval,signal)=>new Promise(resolve=>requests.push({ticker,interval,signal,resolve})));
  component.setSelection({label:'Conditional candidate',stocks:[{ticker:'AAA'},{ticker:'BBB'}]});
  assert.equal(requests.length,0,'offscreen cards should not request');
  observer.callback(observer.targets.map(target=>({target,isIntersecting:true})));
  assert.equal(requests.length,2);
  requests[0].resolve(data('AAA')); requests[1].resolve(data('BBB')); await Promise.resolve();
  for(const card of container.children.slice(1)) {
    assert.ok(card.children[3].innerHTML.includes('<svg'),'each selected card has own true candles');
    assert.ok(card.children[2].textContent.includes('缓存滞后'));
  }
  const first=container.children[1]; first.children[0].children[1].children[1].onclick();
  component.setSelection({stocks:[{ticker:'CCC'}]});
  assert.equal(requests[2].signal.aborted,true);
  requests[2].resolve(data('AAA')); await Promise.resolve();
  assert.equal(container.children[1].children[3].innerHTML,'','old selection response cannot draw new card');
  observer.callback([{target:observer.targets[0],isIntersecting:true}]);
  requests[3].resolve(data('CCC')); await Promise.resolve();
  assert.ok(container.children[1].children[3].innerHTML.includes('<svg'));
  const chart = container.children[1].children[3];
  const many=Array.from({length:90},(_,i)=>({...bars[0],date:'bar-'+i,high:13+i,close:12+i}));
  // A new card gets its own viewport; redraws never rebind the wheel listener.
  component.setSelection({stocks:[{ticker:'AAA'},{ticker:'BBB'}]});
  observer.callback(observer.targets.map(target=>({target,isIntersecting:true})));
  requests[4].resolve({...data('AAA'),bars:many});requests[5].resolve({...data('BBB'),bars:many});await Promise.resolve();
  const a=container.children[1].children[3],b=container.children[2].children[3];
  assert.equal((a.innerHTML.match(/<rect/g)||[]).length,60);
  const unchanged=b.innerHTML,listener=a.listeners.wheel;let prevented=0;
  a.listeners.wheel({deltaY:-1,clientX:300,preventDefault(){prevented++;}});
  assert.equal((a.innerHTML.match(/<rect/g)||[]).length,48);assert.equal(b.innerHTML,unchanged);
  a.onpointerdown({button:0,pointerId:7,clientX:300});assert.equal(a.pointer,7);
  a.onpointermove({pointerId:7,clientX:10000});assert.match(a.innerHTML,/bar-0</);
  a.onpointerup({pointerId:7});assert.equal(a.pointer,null);
  for(let i=0;i<30;i++)a.listeners.wheel({deltaY:-1,clientX:300,preventDefault(){}});
  assert.equal((a.innerHTML.match(/<rect/g)||[]).length,10);
  for(let i=0;i<40;i++)a.listeners.wheel({deltaY:1,clientX:300,preventDefault(){}});
  assert.equal((a.innerHTML.match(/<rect/g)||[]).length,90);
  assert.equal(a.listeners.wheel,listener);assert.match(a.innerHTML,/价格 USD/);assert.equal(prevented,1);
  a.onpointerdown({button:0,pointerId:8,clientX:300});a.onpointercancel({pointerId:8});assert.equal(a.pointer,null);
  assert.equal(container.children[1].children[0].children[1].children.length,3);
  assert(!container.children[1].children.some(n=>n.tag==='select'||n.tag==='dialog'));
  component.setSelection(null); assert.equal(a.listeners.wheel,undefined); assert.ok(container.textContent.includes('待发布'));
  assert.equal(requests.length,6,'no implicit baseline or whole-pool requests');
  component.setSelection({stocks:[{ticker:'SNDK',security_id:'sid'}]});
  observer.callback(observer.targets.map(target=>({target,isIntersecting:true})));
  requests[6].resolve({...data('SNDK'),bars:[{...bars[0],date:'2026-10-14'}]});await Promise.resolve();
  const fillCard=container.children[1],fillChart=fillCard.children[3],wheelBefore=fillChart.listeners.wheel;
  component.setFills([{security_id:'sid',ticker:'SNDK',side:'BUY',quantity:14,price:'132221/100',executed_at:'2026-10-16T15:00:00Z'}]);
  assert.match(fillCard.children[5].textContent,/当前历史区间外/);
  assert.match(fillCard.children[5].textContent,/1322.21/);
  assert(!fillChart.innerHTML.includes('actual-fill-reference'));
  assert.equal(fillChart.listeners.wheel,wheelBefore);
  component.setFills([{security_id:'wrong',ticker:'SNDK',side:'BUY',quantity:14,price:11,executed_at:'2026-10-14T15:00:00Z'}]);
  assert.equal(fillCard.children[5].textContent,'');
  component.setFills([{security_id:'sid',ticker:'SNDK',side:'SELL',quantity:1,price:11,executed_at:'2026-10-14T15:00:00Z'}]);
  assert.match(fillChart.innerHTML,/actual-fill-reference/);assert.match(fillCard.children[5].textContent,/未核验/);
  component.setSelection({monthly_target:true,stocks:[{ticker:'AAA',security_id:'A',quantity:null}]});
  assert.equal(container.children[1].children[1].textContent,'本月目标待核验');
  component.setSelection({monthly_target:true,stocks:[{ticker:'AAA',security_id:'A',quantity:5}]});
  assert.match(container.children[1].children[1].textContent,/本月目标 5 股/);
  component.destroy();
  console.log('PASS: SVG OHLC, each-card lazy render, stale label and async selection cancellation');
})().catch(error=>{console.error(error);process.exitCode=1;});
