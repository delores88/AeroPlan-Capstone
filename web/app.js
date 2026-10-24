'use strict';
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const h = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = v => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
  const n = (v, d = 0) => num(v) ? Number(v).toLocaleString(undefined, {maximumFractionDigits:d, minimumFractionDigits:d}) : '—';
  const pct = (v, d = 2) => num(v) ? n(Number(v) * 100, d) + '%' : '—';
  const signed = (v, d = 2) => num(v) ? (Number(v) > 0 ? '+' : '') + n(v, d) : '—';
  const pp = v => num(v) ? signed(Number(v) * 100, 2) + ' pp' : '—';
  const date = v => v ? new Date(v).toLocaleDateString(undefined, {month:'short', day:'numeric',year:'numeric',...(/^\d{4}-\d{2}-\d{2}$/.test(v)?{timeZone:'UTC'}:{})}) : '—';
  const compact = v => num(v) ? Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:2}).format(v) : '—';
  const pretty = s => String(s || '').replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
  const icons = {
    overview:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    inventory:'M3 7l9-4 9 4-9 4-9-4 M3 7v10l9 4 9-4V7 M12 11v10',
    forecasts:'M3 3v18h18 M6 15l4-5 4 3 6-8',
    cohorts:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M16 3a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
    runs:'M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3 M16 3h5v5 M10 14L21 3 M7 17h5',
    data:'M20 6c0 2-3.6 3-8 3S4 8 4 6s3.6-3 8-3 8 1 8 3 M4 6v12c0 2 3.6 3 8 3s8-1 8-3V6 M4 12c0 2 3.6 3 8 3s8-1 8-3',
    plus:'M12 5v14 M5 12h14', arrow:'M5 12h14 M13 6l6 6-6 6',
    download:'M12 3v12 M7 10l5 5 5-5 M5 16v5h14v-5',
    search:'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
    check:'M5 12l4 4L19 6', alert:'M12 3L2 21h20L12 3 M12 9v5 M12 18h.01',
    close:'M6 6l12 12 M6 18L18 6', menu:'M3 6h18 M3 12h18 M3 18h18',
    chevron:'M9 5l7 7-7 7', clock:'M12 8v4l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
    upload:'M12 16V3 M7 8l5-5 5 5 M4 16v5h16v-5',
    refresh:'M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 13 3 M18 18a8 8 0 0 1-13-3',
    shield:'M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6'
  };
  const icon = (key, size = 18) => '<svg class="icon" width="'+size+'" height="'+size+'" viewBox="0 0 24 24" aria-hidden="true"><path d="'+(icons[key]||icons.overview)+'"/></svg>';
  const badge = (text, cls = '') => '<span class="badge '+cls+'">'+h(text)+'</span>';
  const opt = (value, label, selected) => '<option value="'+h(value)+'"'+(String(value)===String(selected)?' selected':'')+'>'+h(label)+'</option>';
  const routes = ['overview','inventory','forecasts','cohorts','runs','data'];
  const S = {state:null,overview:null,runs:[],route:'overview',runId:'',summary:null,summaryError:'',view:null,viewError:'',busy:false,
    page:0,q:'',site:'',family:'',criticality:'',group:'site',forecastKey:'',forecast:null,forecastError:'',rawTable:'history',rawPage:0,raw:null,
    progress:null,compare:[],comparison:null,sequence:0,modal:null,stage:null,toastTimer:null,forecastWindow:'52'};
  let pollTimer, searchTimer, modalTrigger;
  const selectedRun = () => S.runs.find(r=>r.id===S.runId);
  const cost = x => x && (x.carrying_cost ?? x.cost);
  const parts = () => {const s=S.summary?.summary||{};return {b:s.baseline||{},a:s.selected||{}};};
  const activeMeta = () => S.overview?.metadata || S.state?.datasets?.find(x=>x.id===S.state.active_dataset) || {};
  const runName = r => r?.config?.name || r?.name || ('Run '+(r?.id || '').slice(0,8));
  const modelLabel = key => ({ma8:'MA(8)',naive:'Last-observation naïve',seasonal52:'Seasonal naïve (52 weeks)',ses:'SES',sba:'SBA',tsb:'TSB'})[key] || S.state?.models?.[key] || key || '—';
  const modelMarkup = key => '<span title="'+h(S.state?.models?.[key]||modelLabel(key))+'">'+h(modelLabel(key))+'</span>';
  const policyLabel = mode => mode==='cost_service'?'Cost and service':'Forecast accuracy';
  function policyBadge(row) {
    const retained=row.baseline_fallback===true||String(row.selection_status||'').startsWith('baseline_fallback');
    const optimized=row.selection_status==='cost_saving_candidate'||row.baseline_fallback===false;
    if(!retained&&!optimized)return '';
    return '<span class="badge '+(retained?'blue':'teal')+'" title="'+h(row.selection_reason||'')+'">'+(retained?'Baseline retained':'Optimized')+'</span>';
  }
  function validationBadge(row) {
    const target=typeof row.validation_absolute_target_met==='boolean'?row.validation_absolute_target_met:row.validation_feasible;
    if(row.validation_fill===null||typeof target!=='boolean')return badge('Not available');
    return '<span title="Absolute validation service target">'+badge(target?'Target met':'Target unmet',target?'teal':'amber')+'</span>';
  }
  const complete = r => r?.status === 'complete';
  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-AeroPlan-Token':S.state?.token||''},body:JSON.stringify(body)});
    const data = await response.json().catch(()=>({error:'The local service returned an unreadable response.'}));
    if(!response.ok) throw Error(data.error || 'Request failed ('+response.status+').');
    return data;
  }
  function toast(message) {
    const el=$('#toast'); el.textContent=message;el.classList.add('visible');
    clearTimeout(S.toastTimer);S.toastTimer=setTimeout(()=>el.classList.remove('visible'),5000);
  }
  function statusBadge(r) {return badge(pretty(r?.status||'unknown'),complete(r)?'teal':r?.status==='failed'?'red':r?.status==='running'?'blue':'amber');}
  function datasetBadge(meta) {return meta.synthetic === true || ['demo','kaggle'].includes(meta.source_kind) ? badge('Synthetic data','amber') : badge('Local data','blue');}
  function runStrip() {
    const completed=S.runs.filter(r=>complete(r)&&(r.dataset===S.state.active_dataset||r.id===S.runId));
    return '<div class="run-strip"><div class="run-picker"><label for="run-picker">Selected analysis</label><select id="run-picker" '+(!completed.length?'disabled':'')+'>'+(!completed.length?opt('','No completed analyses',''):completed.map(r=>opt(r.id,runName(r)+' · '+r.id.slice(0,8),S.runId)).join(''))+'</select></div><div class="run-context">'+(selectedRun()?'<span>'+date(selectedRun().created)+'</span>'+badge(policyLabel(selectedRun().config?.policy_mode),'teal')+(selectedRun().dataset!==S.state.active_dataset?'<span class="run-dataset">'+h(S.summary?.dataset?.title||selectedRun().dataset)+'</span>':''):'<span>Run an analysis to compare inventory policies.</span>')+'</div>'+(S.runId?'<div class="actions"><button class="small" data-action="run-details" data-id="'+h(S.runId)+'">Settings</button><a class="button small" href="/api/export/'+encodeURIComponent(S.runId)+'/zip">'+icon('download',15)+'Export run</a></div>':'')+'</div>';
  }
  function pageHeader(title,desc,extra='') {
    return '<div class="page-header"><div><div class="eyebrow">Inventory intelligence</div><h1>'+h(title)+'</h1><p>'+h(desc)+'</p></div><div class="actions">'+extra+'<button class="primary" data-action="new-run" '+(S.state?.active_run?'disabled':'')+'>'+icon('plus')+'New analysis</button></div></div>';
  }
  function loading() {return '<div class="loading" role="status" aria-live="polite"><div class="skeleton big"></div><div class="loading-grid"><div class="skeleton big"></div><div class="skeleton big"></div></div><span class="muted tiny">Loading results…</span></div>';}
  function error(message, retry='retry') {return '<div class="error-banner" role="alert">'+icon('alert')+'<div>'+h(message)+'</div><button class="small" data-action="'+retry+'">Try again</button></div>';}
  function empty(title,desc,action=true) {return '<div class="card empty">'+icon('forecasts',36)+'<h2>'+h(title)+'</h2><p>'+h(desc)+'</p>'+(action?'<button class="primary" data-action="new-run" '+(S.state?.active_run?'disabled':'')+'>'+icon('plus')+'New analysis</button>':'')+'</div>';}
  function shell() {
    const focus=document.activeElement?.id, start=document.activeElement?.selectionStart;
    const meta=activeMeta();
    $('#app').innerHTML='<div class="app-shell"><aside class="sidebar" aria-label="Main navigation"><a class="brand" href="#overview"><span class="brand-mark">A</span><span><span class="brand-name">AeroPlan</span><span class="brand-sub">Inventory intelligence</span></span></a><div class="nav-label">Workspace</div><nav class="nav-list">'+routes.map(r=>'<a class="nav-link '+(S.route===r?'active':'')+'" href="#'+r+'" '+(S.route===r?'aria-current="page"':'')+'>'+icon(r)+'<span>'+pretty(r)+'</span></a>').join('')+'</nav><div class="sidebar-footer"><div class="connection"><span class="dot"></span>Local workspace</div><span>Version '+h(S.state.version)+'</span></div></aside><button class="mobile-overlay" data-action="close-menu" aria-label="Close navigation"></button><div class="main-shell"><header class="topbar"><div class="breadcrumb"><button class="mobile-menu ghost" data-action="menu" aria-label="Toggle navigation">'+icon('menu')+'</button><span>Workspace</span>'+icon('chevron',12)+'<strong>'+pretty(S.route)+'</strong></div><div class="top-right"><button class="dataset-button" data-action="data">'+icon('data',16)+'<span>'+h(meta.title||'Dataset')+'</span></button>'+datasetBadge(meta)+'<span class="avatar" aria-label="Local workspace">AP</span></div></header><main id="main" class="content" tabindex="-1">'+progressPanel()+'<div id="page-content">'+pageContent()+'</div></main></div></div>';
    if(focus){const el=document.getElementById(focus);if(el){el.focus({preventScroll:true});if(typeof start==='number'&&el.setSelectionRange)try{el.setSelectionRange(start,start);}catch{}}}
  }
  function progressPanel() {
    const id=S.progress?.active||S.state?.active_run;if(!id)return '<div id="progress-region"></div>';
    const p=S.progress?.runs?.[id]||{done:0,total:1,message:'Preparing analysis'};
    const fraction=Math.min(100,Math.max(0,(p.done||0)/(p.total||1)*100));
    return '<div id="progress-region" class="progress-panel"><div class="progress-copy"><span><strong>Analysis in progress</strong> <span class="muted">'+h(p.message)+'</span></span><button class="small" data-action="cancel">Cancel</button></div><div class="progress-track" role="progressbar" aria-label="Analysis progress" aria-valuenow="'+Math.round(fraction)+'" aria-valuemin="0" aria-valuemax="100"><div class="progress-bar" style="width:'+fraction+'%"></div></div></div>';
  }
  function chart(rows, lines, options={}) {
    if(!rows?.length)return '<div class="chart-placeholder">No observations available.</div>';
    const w=860,height=options.height||260,left=60,right=18,top=15,bottom=40;
    const values=rows.flatMap(r=>lines.map(l=>r[l.key]).concat(options.band?[r[options.band.lower],r[options.band.upper]]:[])).filter(num).map(Number);
    if(!values.length)return '<div class="chart-placeholder">No observations available.</div>';
    let lo=options.min??Math.min(0,...values),hi=options.max??Math.max(...values);if(hi===lo)hi=lo+1;
    const x=i=>left+i/Math.max(1,rows.length-1)*(w-left-right),y=v=>top+(hi-v)/(hi-lo)*(height-top-bottom);
    let svg='<svg class="chart" viewBox="0 0 '+w+' '+height+'" role="img" aria-label="'+h(options.label||'Time series chart')+'">';
    for(let i=0;i<5;i++){let v=lo+(hi-lo)*i/4;svg+='<line class="gridline" x1="'+left+'" y1="'+y(v)+'" x2="'+(w-right)+'" y2="'+y(v)+'"/><text class="chart-axis-label" x="'+(left-10)+'" y="'+(y(v)+4)+'" text-anchor="end">'+h(options.percent?pct(v,0):compact(v))+'</text>';}
    if(options.band){
      let segment=[];const flush=()=>{if(segment.length>1){const upper=segment.map(([r,i])=>x(i).toFixed(1)+','+y(Number(r[options.band.upper])).toFixed(1));const lower=[...segment].reverse().map(([r,i])=>x(i).toFixed(1)+','+y(Number(r[options.band.lower])).toFixed(1));svg+='<path d="M'+upper.join(' L')+' L'+lower.join(' L')+' Z" fill="'+(options.band.color||'#dfc68e')+'" fill-opacity="0.32" stroke="none"/>';}segment=[];};
      rows.forEach((r,i)=>{if(num(r[options.band.lower])&&num(r[options.band.upper]))segment.push([r,i]);else flush();});flush();
      for(const key of [options.band.lower,options.band.upper]){let edge='',drawing=false;rows.forEach((r,i)=>{if(num(r[key])){edge+=(drawing?'L':'M')+x(i).toFixed(1)+','+y(Number(r[key])).toFixed(1)+' ';drawing=true;}else drawing=false;});svg+='<path d="'+edge+'" fill="none" stroke="#b99b5d" stroke-opacity="0.65" stroke-width="1"/>';}
    }
    for(const line of lines){let path='',drawing=false;rows.forEach((r,i)=>{const v=r[line.key];if(num(v)){path+=(drawing?'L':'M')+x(i).toFixed(1)+','+y(Number(v)).toFixed(1)+' ';drawing=true;}else drawing=false;});svg+='<path class="trace" d="'+path+'" stroke="'+line.color+'" '+(line.dash?'stroke-dasharray="6 5"':'')+'/>';}
    [...new Set([0,Math.floor((rows.length-1)/3),Math.floor((rows.length-1)*2/3),rows.length-1])].forEach(i=>{const raw=rows[i].week||rows[i].date||String(i+1);const d=new Date(raw);const label=Number.isNaN(d.getTime())?raw:d.toLocaleDateString(undefined,{month:'short',year:'2-digit'});svg+='<text class="chart-axis-label" x="'+x(i)+'" y="'+(height-10)+'" text-anchor="'+(i===0?'start':i===rows.length-1?'end':'middle')+'">'+h(label)+'</text>';});
    return svg+'</svg>';
  }
  function legend(lines) {return '<div class="legend">'+lines.map(l=>'<span><i class="swatch" style="background:'+l.color+'"></i>'+h(l.label)+'</span>').join('')+'</div>';}
  function metric(label,value,detail,delta='') {return '<article class="card metric"><div class="metric-head">'+h(label)+'</div><div class="metric-value">'+h(value)+'</div><div class="metric-detail">'+detail+'</div>'+(delta?'<div class="delta">'+delta+'</div>':'')+'</article>';}
  function deltaCost(a,b) {return num(a)&&num(b)&&Number(b)!==0?(Number(a)-Number(b))/Number(b):null;}
  function costChange(a,b) {const value=deltaCost(a,b);return num(value)?signed(value*100)+'%':'—';}
  function direction(value,lower=true) {return !num(value)||Number(value)===0?'muted':((Number(value)<0)===lower?'positive':'negative');}
  function resultNotReady() {return S.summaryError?error(S.summaryError):!S.runId?empty('Build your first comparison','Evaluate selected policies against a matched baseline to see cost and service outcomes.'):!S.summary?loading():null;}
  function inferenceValue(root, aliases) {for(const k of aliases){if(root?.[k]!==undefined)return root[k];}return undefined;}
  function decisionRows() {
    const inf=S.summary?.inference||{}, b=parts().b,a=parts().a;
    const saving=inferenceValue(inf,['cost_saving','cost','cost_test'])||{};
    const service=inferenceValue(inf,['service_noninferiority','service_non_inferiority','service','fill_test'])||{};
    const costPass=inferenceValue(saving,['reject_null','rejected','significant'])??inferenceValue(inf,['cost_improvement_met','cost_null_rejected']);
    const servicePass=inferenceValue(service,['reject_null','rejected','noninferior'])??inferenceValue(inf,['noninferiority_met','service_noninferiority_met']);
    const absolute=S.summary?.absolute_target_met;
    const rows=[
      {title:'Carrying cost',desc:costPass===true?'Cost reduction supported.':costPass===false?'Cost reduction not supported.':'Selected '+n(cost(a))+' · Baseline '+n(cost(b))+' cost units.',pass:costPass,value:costChange(cost(a),cost(b))},
      {title:'Service tolerance',desc:servicePass===true?'Within the baseline tolerance.':servicePass===false?'Baseline tolerance not established.':'Compare the paired service estimate with the configured tolerance.',pass:servicePass,value:pp(num(a.fill_rate)&&num(b.fill_rate)?a.fill_rate-b.fill_rate:null)},
      {title:'Absolute service target',desc:'Selected fill '+pct(a.fill_rate)+' · Target '+pct(S.summary?.config?.target??.95,0),pass:absolute,value:absolute===true?'Met':absolute===false?'Not met':'Pending'}
    ];
    const critical=(S.summary?.optimization?.evaluation_cohort_checks||[]).find(row=>row.dimension==='criticality'&&String(row.key).trim().toUpperCase()==='A');
    if(critical){
      const known=num(critical.baseline_fill)&&num(critical.selected_fill);
      const delta=known?Number(critical.selected_fill)-Number(critical.baseline_fill):null;
      rows.push({title:'Criticality A service',desc:'Baseline '+pct(critical.baseline_fill)+' · Selected '+pct(critical.selected_fill)+' · No-decline guard',pass:known?Number(critical.selected_fill)>=Number(critical.baseline_fill)-1e-12:undefined,value:known?pp(delta):'Not available'});
    }
    return '<div class="decision-list">'+rows.map(x=>'<div class="decision"><div class="decision-icon '+(x.pass===false?'amber':'')+'">'+icon(x.pass===true?'check':x.pass===false?'alert':'forecasts',16)+'</div><div><strong>'+x.title+'</strong><p>'+h(x.desc)+'</p></div>'+badge(x.value,x.pass===true?'teal':x.pass===false?'amber':'')+'</div>').join('')+'</div>';
  }
  function overview() {
    const o=S.overview||{},meta=activeMeta(),head=pageHeader('Overview','Demand, inventory investment, and service performance in one workspace.');
    let top='<div class="hero-band"><div class="hero-copy"><span class="eyebrow">Active dataset</span><h2>'+h(meta.title||'Inventory dataset')+'</h2><p>'+date(meta.start)+' — '+date(meta.end)+'</p></div><div class="mini-facts"><div><strong>'+n(meta.series??o.series?.length)+'</strong><span>Site–part series</span></div><div><strong>'+n(meta.parts)+'</strong><span>Parts</span></div><div><strong>'+n(o.sites?.length)+'</strong><span>Sites</span></div></div></div>';
    const {a,b}=parts();
    let results;
    if(S.summary){results='<div class="metrics">'+metric('Carrying cost',compact(cost(a)),'Baseline '+n(cost(b))+' cost units','<span class="'+direction(deltaCost(cost(a),cost(b)))+'">'+costChange(cost(a),cost(b))+'</span> vs. baseline')+metric('Immediate fill rate',pct(a.fill_rate),'Baseline '+pct(b.fill_rate),'<span class="'+direction(a.fill_rate-b.fill_rate,false)+'">'+pp(a.fill_rate-b.fill_rate)+'</span> vs. baseline')+metric('Average inventory value',compact(a.avg_inventory_value),'Baseline '+n(b.avg_inventory_value)+' cost units','Across the evaluation period')+metric('Stockout series-weeks',n(a.stockout_weeks,1),'Baseline '+n(b.stockout_weeks,1),'Mean across paired simulations')+'</div><div class="grid-two"><section class="card"><div class="card-head"><div><h2>Demand over time</h2><p>Recorded weekly demand across the active dataset</p></div>'+badge('Units')+'</div><div class="card-body">'+chart(o.trend,[{key:'demand',color:'#057d80'}],{label:'Recorded weekly demand'})+'</div></section><section class="card"><div class="card-head"><div><h2>Policy comparison</h2><p>Cost, baseline tolerance, and service target</p></div></div><div class="card-body">'+decisionRows()+'</div><div class="card-footer"><span class="muted tiny">Joint improvement</span>'+badge(S.summary.joint_claim===true?'Supported':S.summary.joint_claim===false?'Not supported':'Not available',S.summary.joint_claim===true?'teal':'amber')+'</div></section></div>';}
    else results=(S.summaryError?error(S.summaryError):S.runId?loading():'<div class="metrics">'+metric('Recorded demand',compact(o.total_demand),'Units across the full dataset')+metric('Zero-demand weeks',pct(o.zero_demand_share),'Share of site–part observations')+metric('Latest on-hand value',compact(o.latest_on_hand_value),'Cost units · Recorded snapshot')+metric('Purchase orders',compact(meta.purchase_orders),'Imported order records')+'</div><div class="grid-two"><section class="card"><div class="card-head"><div><h2>Demand over time</h2><p>Recorded weekly demand</p></div></div><div class="card-body">'+chart(o.trend,[{key:'demand',color:'#057d80'}])+'</div></section>'+empty('Compare inventory policies','Run the selected-policy evaluation to inspect investment and availability.')+'</div>');
    return head+top+runStrip()+results+'<div class="grid-two equal"><section class="card"><div class="card-head"><div><h2>Demand profiles</h2><p>Full-history descriptive classification</p></div></div><div class="card-body">'+bars(Object.entries(o.segments||{}).map(([key,value])=>({key,value})))+'</div></section><section class="card"><div class="card-head"><div><h2>Workspace snapshot</h2><p>Recorded data and analysis scope</p></div><a href="#data" class="button small">View data '+icon('arrow',14)+'</a></div><div class="card-body"><dl class="detail-list"><dt>Observations</dt><dd>'+n(meta.history_rows)+'</dd><dt>Latest backorders</dt><dd>'+n(o.latest_backorders)+' units</dd><dt>Latest blocked stock</dt><dd>'+n(o.latest_blocked)+' units</dd><dt>Data type</dt><dd>'+datasetBadge(meta)+'</dd><dt>Cost denomination</dt><dd>Source cost units</dd></dl></div></section></div>';
  }
  function bars(rows) {const max=Math.max(1,...rows.map(x=>Number(x.value)||0));return '<div class="bar-rows">'+rows.map(x=>'<div class="bar-row"><span>'+h(x.key)+'</span><div class="bar-track"><div class="bar-fill" style="width:'+(Number(x.value)/max*100)+'%"></div></div><strong>'+n(x.value)+'</strong></div>').join('')+'</div>';}
  function filters() {
    const f=S.view?.filters||{sites:S.overview?.sites||[],families:S.overview?.families||[],criticalities:S.overview?.criticalities||[]};
    const exportQuery=new URLSearchParams({q:S.q,site:S.site,family:S.family,criticality:S.criticality});
    return '<div class="toolbar"><label class="search-field">'+icon('search',16)+'<input id="result-search" data-filter="q" aria-label="Search parts and sites" placeholder="Search parts, sites, models…" value="'+h(S.q)+'"></label>'+[['site','Site','sites'],['family','Family','families'],['criticality','Criticality','criticalities']].map(([k,label,fk])=>'<select id="filter-'+k+'" data-filter="'+k+'" aria-label="'+label+'">'+opt('','All '+fk,S[k])+(f[fk]||[]).map(v=>opt(v,v,S[k])).join('')+'</select>').join('')+'<button class="small ghost" data-action="clear-filters">Reset</button><a class="button small" href="/api/export/'+S.runId+'/csv?'+h(exportQuery)+'">'+icon('download',15)+'Export filtered CSV</a></div>';
  }
  function pagination(data,raw=false) {
    const count=data?.rows?.length||0,total=data?.total??count,page=data?.page??0,limit=data?.limit??50;
    return '<div class="pagination"><span>'+(!total?'0 results':n(page*limit+1)+'–'+n(page*limit+count)+' of '+n(total))+'</span><div class="actions"><button class="small" data-action="'+(raw?'raw-prev':'prev')+'" '+(page===0?'disabled':'')+'>Previous</button><span class="tiny muted">Page '+n(page+1)+'</span><button class="small" data-action="'+(raw?'raw-next':'next')+'" '+((page+1)*limit>=total?'disabled':'')+'>Next</button></div></div>';
  }
  function inventory() {
    const head=pageHeader('Inventory','Compare cost and availability for every site–part policy.')+runStrip();
    const not=resultNotReady();if(not)return head+not;
    return head+'<section class="card">'+filters()+(S.viewError?error(S.viewError):S.busy?loading():inventoryTable())+'</section>';
  }
  function inventoryTable() {
    const rows=S.view?.rows||[];
    if(!rows.length)return '<div class="empty compact"><h3>No matching inventory</h3><p>Adjust your search or filters.</p></div>';
    return '<div class="table-wrap"><table><thead><tr><th>Part / site</th><th>Policy</th><th class="number">Demand</th><th class="number">Baseline cost</th><th class="number">Selected cost</th><th class="number">Cost change</th><th class="number">Baseline fill</th><th class="number">Selected fill</th><th class="number">Fill change</th></tr></thead><tbody>'+rows.map(r=>{
      const bc=r.baseline_cost??cost(r.baseline),ac=r.selected_cost??cost(r.selected),bf=r.baseline_fill??r.baseline?.fill_rate,af=r.selected_fill??r.selected?.fill_rate;
      const delta=num(af)&&num(bf)?af-bf:null;
      return '<tr><td><button class="cell-button" data-action="open-forecast" data-key="'+h(r.key||r.site_id+'|'+r.part_id)+'">'+h(r.part_id)+'</button><span class="sub">'+h(r.site_id)+' · '+h(r.family)+' · '+h(r.criticality)+'</span></td><td>'+modelMarkup(r.model||r.selected_model)+'<span class="sub">Buffer z '+n(r.buffer_z??r.z,2)+'</span>'+policyBadge(r)+'</td><td class="number">'+n(r.demand??r.total_demand)+'</td><td class="number">'+n(bc)+'</td><td class="number">'+n(ac)+'</td><td class="number '+direction(deltaCost(ac,bc))+'">'+(num(deltaCost(ac,bc))?signed(deltaCost(ac,bc)*100)+'%':'—')+'</td><td class="number">'+pct(bf)+'</td><td class="number">'+pct(af)+'</td><td class="number '+direction(delta,false)+'">'+pp(delta)+'</td></tr>';
    }).join('')+'</tbody></table></div>'+pagination(S.view);
  }
  function forecastPlot() {
    const f=S.forecast;if(!f)return '<div class="chart-placeholder">Select a series to view its forecast.</div>';
    const allHistory=f.history||[],history=S.forecastWindow==='all'?allHistory:allHistory.slice(-Number(S.forecastWindow)),future=f.future||f.future_13||[];
    const rows=history.map(r=>({week:r.date||r.week,actual:r.actual??r.demand,predicted:r.predicted??r.forecast}));
    const last=rows[rows.length-1];
    if(last&&future.length)last.future=last.predicted??last.actual;
    future.forEach(r=>rows.push({week:r.date||r.week,future:r.yhat??r.predicted??r.forecast??r.value,lower:r.yhat_lower,upper:r.yhat_upper}));
    const lines=[{key:'actual',label:'Recorded demand',color:'#057d80'},{key:'predicted',label:'Rolling prediction',color:'#407dc5'},{key:'future',label:'Future forecast',color:'#a27b29',dash:true}];
    const interval=f.intervals||{},hasBands=future.some(r=>num(r.yhat_lower)&&num(r.yhat_upper)),level=pct(interval.level??.95,0);
    const counts=future.map(r=>r.calibration_n).filter(num),countText=counts.length?(Math.min(...counts)===Math.max(...counts)?n(counts[0]):n(Math.min(...counts))+'–'+n(Math.max(...counts))):'—';
    const chartLegend=lines.concat(hasBands?[{label:level+' prediction interval',color:'#eadbb9'}]:[]);
    const chartNote=hasBands?level+' empirical prediction interval · '+countText+' historical origins per horizon · Nominal coverage':(interval.method?'Prediction interval unavailable: insufficient calibration history.':'Future values are point estimates; no prediction interval is available.');
    const forecastValues='<details class="source-detail"><summary>Forecast values and calibration</summary><div class="table-wrap"><table><thead><tr><th>Week</th><th class="number">Forecast</th><th class="number">Lower bound</th><th class="number">Upper bound</th><th class="number">Calibration n</th></tr></thead><tbody>'+future.map(r=>'<tr><td>'+date(r.date||r.week)+'</td><td class="number">'+n(r.yhat??r.predicted,2)+'</td><td class="number">'+n(r.yhat_lower,2)+'</td><td class="number">'+n(r.yhat_upper,2)+'</td><td class="number">'+n(r.calibration_n)+'</td></tr>').join('')+'</tbody></table></div>'+(hasBands?'<p class="tiny muted">Horizon-specific absolute forecast errors from earlier rolling origins; nonnegative lower bounds. The stated coverage is nominal, not guaranteed. Bands apply to individual weeks, not the complete horizon.</p>':'')+(interval.display_only?'<p class="tiny muted">Intervals calculated for this view. The saved run remains unchanged.</p>':'')+'</details>';
    const item=(S.view?.rows||[]).find(r=>(r.key||r.site_id+'|'+r.part_id)===S.forecastKey)||f||S.forecastItem;
    return '<div class="card-head"><div><h2>'+h(f.part_id||S.forecastKey.split('|')[1])+' <span class="muted">/ '+h(f.site_id||S.forecastKey.split('|')[0])+'</span></h2><p>'+modelMarkup(f.model||f.selected_model)+' · '+n(future.length)+' future weeks</p>'+policyBadge(item)+'</div><div class="actions"><label for="forecast-window" class="tiny muted">History</label><select id="forecast-window">'+opt('26','Last 26 weeks',S.forecastWindow)+opt('52','Last 52 weeks',S.forecastWindow)+opt('all','Full history',S.forecastWindow)+'</select>'+badge('Units','teal')+'</div></div><div class="card-body">'+legend(chartLegend)+chart(rows,lines,{height:300,label:'Recorded demand, rolling prediction, future forecast, and '+(hasBands?level+' prediction interval':'point forecast')+' for '+S.forecastKey,band:hasBands?{lower:'lower',upper:'upper'}:null})+'<div class="chart-note">'+h(chartNote)+'</div><div class="facts forecast-facts"><div class="fact"><strong>'+n(f.target_units??item.target_units)+'</strong><span>Target stock · units</span></div><div class="fact"><strong>'+n(item.latest_usable_on_hand)+'</strong><span>Latest usable on hand</span></div><div class="fact"><strong>'+n(item.latest_backlog)+'</strong><span>Latest backlog</span></div><div class="fact"><strong>'+n(item.next_forecast??future[0]?.yhat??future[0]?.predicted,2)+'</strong><span>Next week forecast</span></div><div class="fact"><strong>'+n(item.lead_mean_days,1)+'</strong><span>Mean lead time · days</span></div><div class="fact"><strong>'+date(item.latest_date)+'</strong><span>Inventory snapshot</span></div></div><p class="tiny muted">Target stock is not a purchase quantity. Open orders and the current inventory position must be reconciled before ordering.</p>'+forecastValues+'</div>';
  }
  function forecasts() {
    const head=pageHeader('Forecasts','Inspect demand history, rolling predictions, and the forward horizon.')+runStrip();
    const not=resultNotReady();if(not)return head+not;
    return head+'<section class="card">'+(S.forecastError?error(S.forecastError,'retry-forecast'):forecastPlot())+'</section><section class="card">'+filters()+(S.viewError?error(S.viewError):S.busy?loading():forecastTable())+'</section>';
  }
  function forecastTable() {
    const rows=S.view?.rows||[];
    return '<div class="table-wrap"><table><thead><tr><th>Part</th><th>Site</th><th>Family</th><th>Criticality</th><th>Model</th><th class="number">Buffer z</th><th>Validation</th></tr></thead><tbody>'+rows.map(r=>'<tr'+((r.key||r.site_id+'|'+r.part_id)===S.forecastKey?' style="background:var(--accent-soft)"':'')+'><td><button class="cell-button" data-action="select-forecast" data-key="'+h(r.key||r.site_id+'|'+r.part_id)+'">'+h(r.part_id)+'</button></td><td>'+h(r.site_id)+'</td><td>'+h(r.family)+'</td><td>'+h(r.criticality)+'</td><td>'+modelMarkup(r.model||r.selected_model)+'<span class="sub">'+policyBadge(r)+'</span></td><td class="number">'+n(r.buffer_z??r.z,2)+'</td><td>'+validationBadge(r)+'</td></tr>').join('')+'</tbody></table></div>'+(!rows.length?'<div class="empty compact">No matching series.</div>':'')+pagination(S.view);
  }
  function cohorts() {
    const head=pageHeader('Cohorts','Explore demand-weighted service and cost across inventory groups.')+runStrip();
    const not=resultNotReady();if(not)return head+not;
    const groups={site:'Site',family:'Part family',criticality:'Criticality',supplier_risk:'Supplier risk',repairable:'Repairability',training_frequency:'Training demand frequency'};
    const rows=S.view?.rows||[];
    return head+'<section class="card"><div class="toolbar"><label for="cohort-group" class="muted tiny">Group inventory by</label><select id="cohort-group">'+Object.entries(groups).map(([k,l])=>opt(k,l,S.group)).join('')+'</select><a class="button small" href="/api/export/'+S.runId+'/cohorts?group='+encodeURIComponent(S.group)+'">'+icon('download',15)+'Export cohort CSV</a></div>'+(S.viewError?error(S.viewError):S.busy?loading():'<div class="table-wrap"><table><thead><tr><th>'+h(groups[S.group])+'</th><th class="number">Series</th><th class="number">Parts</th><th class="number">Demand</th><th class="number">Baseline cost</th><th class="number">Selected cost</th><th class="number">Baseline fill</th><th class="number">Selected fill</th><th class="number">Fill change</th></tr></thead><tbody>'+rows.map(r=>{
      const b=r.baseline||{},a=r.selected||{},bf=r.baseline_fill??b.fill_rate,af=r.selected_fill??a.fill_rate,delta=num(bf)&&num(af)?af-bf:null;
      return '<tr><td><strong>'+h(r.key??r.label??r.cohort??r.name??'Unspecified')+'</strong></td><td class="number">'+n(r.series_count??r.n_series??r.series)+'</td><td class="number">'+n(r.part_count??r.n_parts??r.parts)+'</td><td class="number">'+n(r.demand??r.total_demand)+'</td><td class="number">'+n(r.baseline_cost??cost(b))+'</td><td class="number">'+n(r.selected_cost??cost(a))+'</td><td class="number">'+pct(bf)+'</td><td class="number">'+pct(af)+'</td><td class="number '+direction(delta,false)+'">'+pp(delta)+'</td></tr>';
    }).join('')+'</tbody></table></div><div class="card-footer"><span class="tiny muted">Fill is weighted by demand. Cost is summed within each cohort and averaged across paired simulations.</span></div>')+'</section>';
  }
  function runCompare() {
    if(!S.comparison)return '';
    const same = fn => S.comparison.every(x => JSON.stringify(fn(x))===JSON.stringify(fn(S.comparison[0])));
    const comparisonStatus = 'Input files: '+(same(x=>x.dataset?.file_hashes)?'Matched':'Different')+' · Evaluation windows: '+(same(x=>x.provenance?.split)?'Matched':'Different')+' · Seeds: '+(same(x=>x.provenance?.replication_seeds)?'Matched':'Different');
    return '<section class="card"><div class="card-head"><div><h2>Analysis comparison</h2><p>Each result retains its own dataset and settings.</p></div><button class="small ghost" data-action="close-compare">'+icon('close',16)+'Close</button></div><div class="compare-grid">'+S.comparison.map(x=>{
      const a=x.summary?.selected||{},r=S.runs.find(r=>r.id===x.run_id);
      return '<div class="compare-item"><h3>'+h(runName(r))+'</h3><div class="tiny muted mono">'+h(x.run_id)+'</div><dl class="detail-list"><dt>Dataset</dt><dd>'+h(x.dataset?.title||r?.dataset)+'</dd><dt>Policy selection</dt><dd>'+h(policyLabel(x.config?.policy_mode))+'</dd><dt>Carrying cost</dt><dd>'+n(cost(a))+'</dd><dt>Immediate fill</dt><dd>'+pct(a.fill_rate)+'</dd><dt>Average inventory</dt><dd>'+n(a.avg_inventory_value)+'</dd><dt>Replications</dt><dd>'+n(x.config?.replications)+'</dd><dt>Service target</dt><dd>'+pct(x.config?.target,0)+'</dd><dt>Annual carry rate</dt><dd>'+pct(x.config?.carry_rate,0)+'</dd><dt>Lead-time factor</dt><dd>'+n(x.config?.lead_factor,2)+'</dd></dl></div>';
    }).join('')+'</div><div class="card-footer tiny muted">'+h(comparisonStatus)+'</div></section>';
  }
  function runs() {
    return pageHeader('Runs','Saved evaluations with fixed configurations and reproducible exports.','<button data-action="refresh">'+icon('refresh',16)+'Refresh</button>')+runCompare()+'<section class="card"><div class="card-head"><div><h2>Analysis history</h2><p>'+n(S.runs.length)+' saved '+(S.runs.length===1?'analysis':'analyses')+'</p></div><button class="small" data-action="compare" '+(S.compare.length!==2?'disabled':'')+'>Compare selected ('+S.compare.length+'/2)</button></div>'+(S.runs.length?'<div class="table-wrap"><table><thead><tr><th><span class="sr-only">Compare</span></th><th>Analysis</th><th>Created</th><th>Status</th><th class="number">Target</th><th class="number">Carry rate</th><th class="number">Lead factor</th><th class="number">Replications</th><th>Actions</th></tr></thead><tbody>'+S.runs.map(r=>'<tr><td><input class="compare-check" type="checkbox" data-compare="'+h(r.id)+'" aria-label="Compare '+h(runName(r))+'" '+(S.compare.includes(r.id)?'checked ':'')+(!complete(r)?'disabled':'')+'></td><td><strong>'+h(runName(r))+'</strong><span class="sub mono">'+h(r.id)+(r.id===S.runId?' · Selected':'')+'</span><span class="sub">'+h(S.state.datasets.find(d=>d.id===r.dataset)?.title||r.dataset)+'</span>'+(r.error?'<span class="sub negative">'+h(r.error)+'</span>':'')+'</td><td>'+date(r.created)+'</td><td>'+statusBadge(r)+'</td><td class="number">'+pct(r.config?.target,0)+'</td><td class="number">'+pct(r.config?.carry_rate,0)+'</td><td class="number">'+n(r.config?.lead_factor,2)+'</td><td class="number">'+n(r.config?.replications)+'</td><td><div class="actions">'+(complete(r)?'<button class="small" data-action="view-run" data-id="'+r.id+'">View</button><a class="button small" href="/api/export/'+r.id+'/zip" aria-label="Export '+h(runName(r))+'">'+icon('download',15)+'</a>':'<button class="small" data-action="run-details" data-id="'+r.id+'">Details</button>')+'</div></td></tr>').join('')+'</tbody></table></div>':'<div class="empty compact"><h3>No analyses yet</h3><p>New runs will appear here with their saved settings.</p></div>')+'</section>';
  }
  function dataPage() {
    const meta=activeMeta(),ds=S.state.datasets||[];
    return pageHeader('Data','Manage local datasets, inspect source records, and review provenance.','<button data-action="import">'+icon('upload',16)+'Import data</button>')+'<div class="dataset-grid">'+ds.map(d=>'<article class="card dataset-card '+(d.id===S.state.active_dataset?'active':'')+'"><div class="actions">'+datasetBadge(d)+(d.id===S.state.active_dataset?badge('Active','teal'):'')+'</div><h3>'+h(d.title||d.id)+'</h3><p>'+date(d.start)+' — '+date(d.end)+'</p><div class="facts"><div class="fact"><strong>'+n(d.series)+'</strong><span>Series</span></div><div class="fact"><strong>'+n(d.parts)+'</strong><span>Parts</span></div><div class="fact"><strong>'+compact(d.history_rows)+'</strong><span>Observations</span></div></div><footer><span class="mono tiny muted">'+h(d.id)+'</span><button class="small" data-action="activate" data-id="'+h(d.id)+'" '+(d.id===S.state.active_dataset||S.state.active_run?'disabled':'')+'>'+(d.id===S.state.active_dataset?'Active':'Activate')+'</button></footer></article>').join('')+'</div><div class="grid-two"><section class="card"><div class="card-head"><div><h2>Dataset details</h2><p>'+h(meta.title)+'</p></div></div><div class="card-body"><dl class="detail-list"><dt>Source</dt><dd>'+h(pretty(meta.source_kind))+'</dd><dt>License</dt><dd>'+h(meta.license||'Not specified')+'</dd><dt>Author</dt><dd>'+h(meta.source_author||'Not specified')+'</dd><dt>Lead-time units</dt><dd>'+h(meta.lead_time_unit||'Days')+'</dd><dt>Cost denomination</dt><dd>Source cost units; currency unspecified</dd><dt>Purchase orders</dt><dd>'+n(meta.purchase_orders)+'</dd><dt>Quality records</dt><dd>'+n(meta.quality_incidents)+'</dd></dl><details class="source-detail"><summary>Source integrity and mapping</summary><pre>'+h(JSON.stringify({source_url:meta.source_url,file_hashes:meta.file_hashes,mapping:meta.mapping},null,2))+'</pre></details></div></section><section class="card"><div class="card-head"><div><h2>Data checks</h2><p>Import validation</p></div>'+badge((meta.warnings||[]).length?'Review':'Validated',(meta.warnings||[]).length?'amber':'teal')+'</div><div class="card-body">'+((meta.warnings||[]).length?'<div class="decision-list">'+meta.warnings.map(w=>'<div class="decision"><div class="decision-icon amber">'+icon('alert',16)+'</div><p>'+h(typeof w==='string'?w:JSON.stringify(w))+'</p></div>').join('')+'</div>':'<div class="notice">'+icon('check')+'<span>No import warnings were recorded.</span></div>')+'<p class="tiny muted">Imported files remain local. Dataset activation applies to new analyses; saved results retain their original dataset.</p></div></section></div><section class="card"><div class="card-head"><div><h2>Source records</h2><p>Browse the active dataset</p></div></div><div class="table-tabs">'+['history','parts','orders','quality'].map(t=>'<button class="'+(S.rawTable===t?'active':'')+'" data-action="raw-table" data-table="'+t+'">'+({history:'Demand history',parts:'Parts',orders:'Purchase orders',quality:'Quality'}[t])+'</button>').join('')+'</div>'+rawTable()+'</section>';
  }
  function rawTable() {
    if(!S.raw)return S.viewError?error(S.viewError):loading();
    const rows=S.raw.rows||[],keys=rows.length?Object.keys(rows[0]):[];
    return (!rows.length?'<div class="empty compact">No records in this table.</div>':'<div class="table-wrap"><table><thead><tr>'+keys.map(k=>'<th>'+h(pretty(k))+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+keys.map(k=>'<td>'+h(r[k]===null?'—':typeof r[k]==='object'?JSON.stringify(r[k]):r[k])+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>')+pagination(S.raw,true);
  }
  function pageContent() {return ({overview,inventory,forecasts,cohorts,runs,data:dataPage})[S.route]();}
  async function loadSummary() {
    S.summary=null;S.summaryError='';if(!S.runId)return;
    const id=S.runId;try {const x=await api('/api/results/'+id+'?view=summary');if(S.runId===id)S.summary=x;}
    catch(e){if(S.runId===id)S.summaryError=e.message;}
  }
  async function loadView() {
    const seq=++S.sequence;S.viewError='';S.busy=true;shell();
    try{
      let data;
      if(S.route==='data')data=await api('/api/table?table='+S.rawTable+'&page='+S.rawPage);
      else if(['inventory','forecasts','cohorts'].includes(S.route)&&S.runId){
        const q=new URLSearchParams({view:S.route,page:S.page,q:S.q,site:S.site,family:S.family,criticality:S.criticality,group:S.group});
        data=await api('/api/results/'+S.runId+'?'+q);
      }
      if(seq!==S.sequence)return;
      if(S.route==='data')S.raw=data;else S.view=data;
      S.busy=false;shell();
      if(S.route==='forecasts'&&S.view?.rows?.length&&!S.forecastKey){const r=S.view.rows[0];await loadForecast(r.key||r.site_id+'|'+r.part_id);}
    }catch(e){if(seq!==S.sequence)return;S.busy=false;S.viewError=e.message;shell();}
  }
  async function loadForecast(key) {
    S.forecastItem=(S.view?.rows||[]).find(r=>(r.key||r.site_id+'|'+r.part_id)===key)||(S.forecastKey===key?S.forecastItem:null);
    S.forecastKey=key;S.forecast=null;S.forecastError='';const id=S.runId;shell();
    try{const x=await api('/api/results/'+id+'?view=forecasts&key='+encodeURIComponent(key));if(S.runId===id&&S.forecastKey===key)S.forecast=x;}
    catch(e){if(S.runId===id&&S.forecastKey===key)S.forecastError=e.message;}
    shell();
  }
  async function selectRun(id,navigate=false) {
    S.sequence++;S.runId=id;S.forecastKey='';S.forecast=null;S.forecastItem=null;S.view=null;S.page=0;
    if(navigate&&S.route!=='overview'){S.route='overview';history.replaceState(null,'','#overview');}
    shell();await loadSummary();shell();if(['inventory','forecasts','cohorts'].includes(S.route))await loadView();
  }
  function route() {
    const next=location.hash.slice(1);
    if(next==='main'){document.getElementById('main')?.focus();return;}
    S.route=routes.includes(next)?next:'overview';S.page=0;S.view=null;S.viewError='';S.raw=null;S.sequence++;document.body.classList.remove('menu-open');shell();
    if(['inventory','forecasts','cohorts','data'].includes(S.route))loadView();
  }
  async function refresh(selectLatest=false) {
    const [state,runs,overview]=await Promise.all([api('/api/state'),api('/api/runs'),api('/api/overview')]);
    S.state=state;S.runs=Array.isArray(runs)?runs:runs.runs||[];S.overview=overview;
    const completed=S.runs.filter(r=>complete(r)&&r.dataset===state.active_dataset);
    if(selectLatest||!S.runs.some(r=>complete(r)&&r.id===S.runId))S.runId=completed[0]?.id||'';
    await loadSummary();shell();
    if(['inventory','forecasts','cohorts','data'].includes(S.route))await loadView();
    if(state.active_run)poll();
  }
  async function poll() {
    clearTimeout(pollTimer);
    try{
      const previous=S.state.active_run;S.progress=await api('/api/progress');S.state.active_run=S.progress.active;
      const region=$('#progress-region');if(region)region.outerHTML=progressPanel();
      $$('[data-action="new-run"]').forEach(b=>b.disabled=!!S.state.active_run);
      if(previous&&!S.progress.active){await refresh(false);toast('Analysis finished. View its status in Runs.');}
      if(S.progress.active)pollTimer=setTimeout(poll,1600);
    }catch(e){toast('Progress unavailable: '+e.message);pollTimer=setTimeout(poll,5000);}
  }
  function modal(title,body,footer,wide=false) {
    modalTrigger=document.activeElement;
    $('#modal-root').innerHTML='<div class="modal-backdrop"><section class="modal '+(wide?'wide':'')+'" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-header"><h2 id="modal-title">'+h(title)+'</h2><button class="ghost small" data-action="close-modal" aria-label="Close dialog">'+icon('close')+'</button></div><div class="modal-body">'+body+'<div id="modal-error" class="form-error" role="alert"></div></div><div class="modal-footer">'+footer+'</div></section></div>';
    document.body.style.overflow='hidden';setTimeout(()=>$('input,select,button',$('.modal-body'))?.focus(),0);
  }
  function closeModal() {$('#modal-root').innerHTML='';S.modal=null;document.body.style.overflow='';modalTrigger?.focus?.();}
  function modalError(message) {const el=$('#modal-error');if(el)el.textContent=message;else toast(message);}
  function runDialog() {
    const d=S.state.defaults||{};S.modal='run';
    const modes=S.state.policy_modes||[{value:'cost_service',label:'Cost and service'},{value:'research',label:'Forecast accuracy'}];
    const policySelect='<label class="field full">Policy selection<select id="run-policy">'+modes.map(m=>opt(m.value,m.label,d.policy_mode||'cost_service')).join('')+'</select></label>';
    modal('New analysis','<p class="muted">Evaluate forecast and inventory policies against the matched baseline.</p><div class="form-grid"><label class="field full">Analysis name<input id="run-name" maxlength="100" value="Inventory review '+h(new Date().toLocaleDateString())+'" required></label>'+policySelect+'<label class="field">Service target (%)<input id="run-target" type="number" value="'+((d.target??.95)*100)+'" min="1" max="100" step=".1" required></label><label class="field">Annual carrying rate (%)<input id="run-carry" type="number" value="'+((d.carry_rate??.24)*100)+'" min=".1" max="100" step=".1" required></label><label class="field">Lead-time factor<input id="run-lead" type="number" value="'+(d.lead_factor??1)+'" min=".1" max="4" step=".05" required></label><label class="field">Paired replications<input id="run-reps" type="number" value="'+(d.replications??30)+'" min="2" max="100" step="1" required></label><label class="field">Starting random seed<input id="run-seed" type="number" value="'+(d.seed_start??10001)+'" min="0" max="2147483000" step="1" required></label></div><details class="source-detail"><summary>Evaluation assumptions</summary><p class="tiny muted">Weekly review with a matched moving-average baseline. Policies are selected on validation data before paired evaluation. Receipts are modeled as complete, and cost values retain the source denomination. Settings and source files are saved with the run.</p><p class="tiny muted">Repeated analysis of the same evaluation period is exploratory. New settings do not create a fresh test period.</p></details>','<button data-action="close-modal">Cancel</button><button class="primary" data-action="start-run">'+icon('forecasts',16)+'Start analysis</button>');
  }
  async function startRun(button) {
    const inputs=$$('input',$('.modal'));if(inputs.some(el=>!el.reportValidity()))return;
    const body={name:$('#run-name').value.trim(),policy_mode:$('#run-policy').value,target:Number($('#run-target').value)/100,carry_rate:Number($('#run-carry').value)/100,lead_factor:Number($('#run-lead').value),replications:Number($('#run-reps').value),seed_start:Number($('#run-seed').value)};
    button.disabled=true;modalError('');
    try{const x=await api('/api/run',body);S.state.active_run=x.id;closeModal();location.hash='runs';await refresh(false);poll();toast('Analysis started. You can continue browsing saved results.');}
    catch(e){button.disabled=false;modalError(e.message);}
  }
  function importDialog() {
    S.modal='import';S.stage=null;
    modal('Import dataset','<p class="muted">Choose a ZIP archive or CSV files from your computer. Parts and weekly demand history are required.</p><label class="upload-zone">'+icon('upload',32)+'<strong>Select dataset files</strong><span>ZIP or CSV · Maximum request size 100 MB</span><input id="import-files" type="file" accept=".zip,.csv" multiple></label><div id="import-preview"></div>','<button data-action="close-modal">Cancel</button><button class="primary" data-action="preview-import">Preview files</button>',true);
  }
  async function fileContent(file) {
    return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(Error('Unable to read '+file.name));reader.onload=()=>resolve({name:file.name,content:String(reader.result).split(',')[1]});reader.readAsDataURL(file);});
  }
  async function previewImport(button) {
    const files=[...($('#import-files')?.files||[])];if(!files.length){modalError('Select a ZIP archive or CSV files first.');return;}
    if(files.reduce((s,f)=>s+f.size,0)>70*1024*1024){modalError('Select files totaling less than 70 MB to fit the local request limit.');return;}
    button.disabled=true;button.textContent='Reading files…';modalError('');
    try{
      const result=await api('/api/import/preview',{files:await Promise.all(files.map(fileContent))});S.stage=result;
      const names=Object.keys(result.files||{});
      $('#import-preview').innerHTML='<div class="form-grid"><label class="field full">Dataset name<input id="import-title" value="'+h(files[0].name.replace(/\.[^.]+$/,''))+'" maxlength="120"></label><label class="field">Data source<select id="import-source">'+opt('local','Local dataset','local')+opt('kaggle','Synthetic aerospace dataset','local')+'</select></label><label class="field">Lead-time units<select id="import-lead">'+opt('days','Days','days')+opt('weeks','Weeks','days')+'</select></label><label class="field">Date format<select id="import-date">'+opt('iso','ISO (YYYY-MM-DD)','iso')+opt('mdy','Month / day / year','iso')+opt('dmy','Day / month / year','iso')+'</select></label></div><p class="tiny muted">Confirm the source columns mapped to each field before importing.</p>'+Object.entries(result.contract||{}).map(([table,c])=>'<details class="mapping-section" '+(['parts','history'].includes(table)?'open':'')+'><summary>'+h(pretty(table))+' '+(['parts','history'].includes(table)?'(required)':'(optional)')+'</summary><label class="field">Source file<select data-mapping-file="'+h(table)+'">'+opt('','Not included',result.suggested_mapping?.[table]?.file)+names.map(name=>opt(name,name+' · '+n(result.files[name].rows)+' rows',result.suggested_mapping?.[table]?.file)).join('')+'</select></label><div class="mapping-grid" id="mapping-'+table+'">'+mappingFields(table,c,result.suggested_mapping?.[table]?.file,result.suggested_mapping?.[table]?.fields||{})+'</div></details>').join('');
      $('.modal-footer').innerHTML='<button data-action="close-modal">Cancel</button><button class="primary" data-action="commit-import">'+icon('check',16)+'Import dataset</button>';
    }catch(e){button.disabled=false;button.textContent='Preview files';modalError(e.message);}
  }
  function mappingFields(table,contract,file,selected={}) {
    const columns=S.stage?.files?.[file]?.columns||[];
    return Object.keys(contract.fields||{}).map(field=>'<label class="field">'+h(pretty(field))+((contract.required||[]).includes(field)?' *':'')+'<select data-map-table="'+h(table)+'" data-map-field="'+h(field)+'" '+(!file?'disabled':'')+'>'+opt('','Not mapped',selected[field])+columns.map(c=>opt(c,c,selected[field])).join('')+'</select></label>').join('');
  }
  async function commitImport(button) {
    const mapping={};for(const [table,c] of Object.entries(S.stage.contract)){
      const file=$('[data-mapping-file="'+table+'"]').value||null,fields={};
      $$('[data-map-table="'+table+'"]').forEach(s=>{if(s.value)fields[s.dataset.mapField]=s.value;});
      if(['parts','history'].includes(table)&&!file){modalError(pretty(table)+' needs a source file.');return;}
      if(file)for(const field of c.required||[]){if(!fields[field]){modalError(pretty(table)+': map '+pretty(field)+'.');return;}}
      mapping[table]={file,fields};
    }
    button.disabled=true;button.textContent='Importing…';modalError('');
    try{await api('/api/import/commit',{stage_id:S.stage.id,mapping,title:$('#import-title').value,source_kind:$('#import-source').value,lead_unit:$('#import-lead').value,date_format:$('#import-date').value});closeModal();await refresh(true);toast('Dataset imported and ready.');}
    catch(e){button.disabled=false;button.textContent='Import dataset';modalError(e.message);}
  }
  async function runDetails(id) {
    const r=S.runs.find(x=>x.id===id);if(!r)throw Error('This analysis is no longer in the run list.');
    const x=complete(r)?(S.summary?.run_id===id?S.summary:await api('/api/results/'+id+'?view=summary')):null;
    S.modal='details';
    const body='<div class="metadata">'+statusBadge(r)+'<span class="mono tiny">'+h(id)+'</span></div>'+(r.error?'<p class="negative">'+h(r.error)+'</p>':'')+'<dl class="detail-list"><dt>Dataset</dt><dd>'+h(x?.dataset?.title||r.dataset)+'</dd><dt>Created</dt><dd>'+date(r.created)+'</dd><dt>Policy selection</dt><dd>'+h(policyLabel(r.config?.policy_mode))+'</dd>'+Object.entries(r.config||{}).filter(([k])=>k!=='policy_mode').map(([k,v])=>'<dt>'+h(pretty(k))+'</dt><dd>'+h(Array.isArray(v)?v.join(', '):typeof v==='object'?JSON.stringify(v):v)+'</dd>').join('')+'</dl>'+(x?'<details class="source-detail"><summary>Saved comparison and source identifiers</summary><pre>'+h(JSON.stringify({inference:x.inference,source_sha256:x.provenance?.source?.sha256,configuration_sha256:x.provenance?.config_sha256,policy_sha256:x.provenance?.policies_sha256},null,2))+'</pre></details>':'');
    modal(runName(r),body,(complete(r)?'<a class="button small" href="/api/export/'+id+'/csv">Inventory CSV</a><a class="button small" href="/api/export/'+id+'/json">Result JSON</a>':'')+'<button data-action="close-modal">Close</button>',true);
  }
  async function action(name,el) {
    try{
      if(name==='menu'){document.body.classList.toggle('menu-open');return;}
      if(name==='close-menu'){document.body.classList.remove('menu-open');return;}
      if(name==='data'){location.hash='data';return;}
      if(name==='new-run'){runDialog();return;}
      if(name==='close-modal'){closeModal();return;}
      if(name==='start-run'){await startRun(el);return;}
      if(name==='import'){importDialog();return;}
      if(name==='preview-import'){await previewImport(el);return;}
      if(name==='commit-import'){await commitImport(el);return;}
      if(name==='cancel'){el.disabled=true;await api('/api/cancel',{});toast('Cancellation requested.');return;}
      if(name==='retry'){if(S.summaryError){await loadSummary();shell();}else await loadView();return;}
      if(name==='retry-forecast'){await loadForecast(S.forecastKey);return;}
      if(name==='refresh'){await refresh();return;}
      if(name==='clear-filters'){S.q='';S.site='';S.family='';S.criticality='';S.page=0;await loadView();return;}
      if(name==='prev'||name==='next'){S.page=Math.max(0,S.page+(name==='next'?1:-1));await loadView();return;}
      if(name==='raw-prev'||name==='raw-next'){S.rawPage=Math.max(0,S.rawPage+(name==='raw-next'?1:-1));S.raw=null;await loadView();return;}
      if(name==='raw-table'){S.rawTable=el.dataset.table;S.rawPage=0;S.raw=null;await loadView();return;}
      if(name==='view-run'){await selectRun(el.dataset.id,true);return;}
      if(name==='select-forecast'){await loadForecast(el.dataset.key);return;}
      if(name==='open-forecast'){S.forecastKey=el.dataset.key;S.forecast=null;location.hash='forecasts';await loadForecast(S.forecastKey);return;}
      if(name==='activate'){el.disabled=true;await api('/api/activate',{dataset_id:el.dataset.id});S.runId='';S.forecastKey='';await refresh(true);toast('Active dataset changed.');return;}
      if(name==='close-compare'){S.comparison=null;shell();return;}
      if(name==='compare'){el.disabled=true;S.comparison=await Promise.all(S.compare.map(id=>api('/api/results/'+id+'?view=summary')));shell();return;}
      if(name==='run-details'){await runDetails(el.dataset.id);return;}
    }catch(e){toast(e.message);el.disabled=false;}
  }
  document.addEventListener('click',e=>{
    const el=e.target.closest('[data-action]');if(el&&!el.disabled){e.preventDefault();action(el.dataset.action,el);}
    if(e.target.classList.contains('modal-backdrop'))closeModal();
  });
  document.addEventListener('input',e=>{
    if(e.target.dataset.filter==='q'){S.q=e.target.value;S.page=0;clearTimeout(searchTimer);searchTimer=setTimeout(loadView,300);}
  });
  document.addEventListener('change',async e=>{
    const el=e.target;
    try{
      if(el.id==='run-picker')await selectRun(el.value);
      else if(el.dataset.filter&&el.dataset.filter!=='q'){S[el.dataset.filter]=el.value;S.page=0;await loadView();}
      else if(el.id==='cohort-group'){S.group=el.value;await loadView();}
      else if(el.id==='forecast-window'){S.forecastWindow=el.value;shell();}
      else if(el.dataset.compare){const id=el.dataset.compare;if(el.checked){if(S.compare.length>=2){el.checked=false;toast('Select up to two completed analyses.');return;}S.compare.push(id);}else S.compare=S.compare.filter(x=>x!==id);shell();}
      else if(el.dataset.mappingFile){const table=el.dataset.mappingFile;$('#mapping-'+table).innerHTML=mappingFields(table,S.stage.contract[table],el.value,{});}
    }catch(err){toast(err.message);}
  });
  document.addEventListener('keydown',e=>{
    const m=$('.modal');if(!m)return;
    if(e.key==='Escape'){closeModal();return;}
    if(e.key==='Tab'){const focusable=$$('a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),summary,[tabindex="0"]',m).filter(x=>x.getClientRects().length);const first=focusable[0],last=focusable[focusable.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}
  });
  window.addEventListener('hashchange',route);
  async function boot(){
    try{S.route=routes.includes(location.hash.slice(1))?location.hash.slice(1):'overview';await refresh(true);if(S.state.active_run)poll();}
    catch(e){$('#app').innerHTML='<main class="boot"><div class="brand-mark">A</div><h1>Unable to open workspace</h1><p>'+h(e.message)+'</p><button data-action="boot">Try again</button></main>';const b=$('[data-action="boot"]');b.onclick=boot;}
  }
  boot();
})();

