"""Weekly forecasting, validation-only policy search, and held-out inventory replay.

This is a single-echelon research simulator, not an ERP or physical procurement system.
All forecasting and optimization calculations execute locally using the standard library.
"""
from __future__ import annotations
import copy, hashlib, math, random, statistics
from collections import Counter, defaultdict
from datetime import date,timedelta
from .forecast import MODELS,forecasts,metrics,segment,future,mean
from .store import now
from . import VERSION

DEFAULTS=dict(name='Baseline vs. optimized policy',models=list(MODELS),target=.95,carry_rate=.24,
 review_weeks=1,validation_weeks=52,test_weeks=26,horizon=13,use_empirical=True,lead_factor=1.0,
 max_series=60,site='',family='',criticality='',seed=42,stock_basis='subtract_blocked')
GRID=[0.,.5,1.,1.5,2.,2.5,3.,4.,5.,6.]
class Cancelled(Exception):pass

def config_checked(raw):
    if not isinstance(raw,dict):raise ValueError('Experiment configuration must be an object.')
    c={**DEFAULTS,**{k:v for k,v in raw.items() if k in DEFAULTS}}
    if not isinstance(c['name'],str) or not c['name'].strip():raise ValueError('Give the experiment a name.')
    c['name']=c['name'].strip()[:120]
    for k,lo,hi in [('target',.5,.999),('carry_rate',.001,1.),('lead_factor',.25,4.)]:
        try:c[k]=float(c[k])
        except (TypeError,ValueError):raise ValueError(f'{k} must be numeric.')
        if not math.isfinite(c[k]) or not lo<=c[k]<=hi:raise ValueError(f'{k} must be between {lo} and {hi}.')
    for k,lo,hi in [('review_weeks',1,8),('validation_weeks',8,104),('test_weeks',4,104),('horizon',1,52),('max_series',0,3000),('seed',0,2147483647)]:
        try:
            value=float(c[k])
            if not value.is_integer():raise ValueError()
            c[k]=int(value)
        except (TypeError,ValueError,OverflowError):raise ValueError(f'{k} must be a whole number.')
        if not lo<=c[k]<=hi:raise ValueError(f'{k} must be between {lo} and {hi}.')
    if not isinstance(c['models'],list) or not c['models'] or any(m not in MODELS for m in c['models']):raise ValueError('Select at least one supported forecast model.')
    c['models']=list(dict.fromkeys(c['models']))
    if not isinstance(c['use_empirical'],bool):raise ValueError('use_empirical must be true or false.')
    if c['stock_basis'] not in ('subtract_blocked','already_usable'):raise ValueError('Invalid on-hand interpretation.')
    for k in ('site','family','criticality'):
        if not isinstance(c[k],str):raise ValueError(f'{k} must be text.')
    return c

def lead_profile(part,orders,site,cutoff,c):
    def lt(o):return (date.fromisoformat(o['receipt_date'])-date.fromisoformat(o['order_date'])).days
    eligible=[o for o in orders if o['part_id']==part['part_id'] and o.get('receipt_date') and o['receipt_date']<=cutoff and o['order_date']<=cutoff and 0<lt(o)<=730]
    same=[o for o in eligible if o.get('site_id')==site]
    usable=same if len(same)>=3 else eligible
    source='Closed POs · site–part' if len(same)>=3 else 'Closed POs · part pooled across sites'
    if not c['use_empirical'] or len(usable)<3:
        days=[part['lead_time_days']];source='Nominal part lead time';n=0
    else:days=[lt(o) for o in usable];n=len(days)
    days=[v*c['lead_factor'] for v in days]
    return dict(mean_days=mean(days),std_days=statistics.pstdev(days) if len(days)>1 else 0.,
      samples_days=days,sample_count=n,source=source,as_of=cutoff)

def target_stock(mu,sigma,lead,c,z):
    protection=math.ceil(lead['mean_days']/7)+c['review_weeks']
    uncertainty=math.sqrt(sigma*sigma*protection+mu*mu*(lead['std_days']/7)**2)
    return max(0,math.ceil(mu*protection+z*uncertainty))

def simulate(y,pred,start,end,state,lead,c,z,sigma,cost,draws,score_start=None,trace=False):
    """Receipts -> old backorders -> new demand -> end-of-week review.
    An order placed at the end of week t is available at the start of t+L+1.
    The inventory position is usable on-hand + pipeline - backlog.
    """
    state=copy.deepcopy(state);stock=float(state['stock']);backlog=float(state['backlog']);pipeline=list(state['pipeline'])
    demand=served=stock_sum=hold=0.;stockout_weeks=weeks=0;rows=[];order_total=0.
    for t in range(start,end):
        receipts=sum(q for due,q in pipeline if due<=t);pipeline=[(due,q) for due,q in pipeline if due>t]
        stock+=receipts
        cleared=min(stock,backlog);stock-=cleared;backlog-=cleared
        immediate=min(stock,y[t]);stock-=immediate;backlog+=y[t]-immediate
        # Review follows this week's demand; use the newly available next-week forecast.
        order=0;S=target_stock(pred[min(t+1,len(pred)-1)],sigma,lead,c,z)
        if (t-start)%c['review_weeks']==0:
            position=stock+sum(q for _,q in pipeline)-backlog
            order=max(0,math.ceil(S-position))
            if order:pipeline.append((t+draws[t]+1,order))
        if score_start is None or t>=score_start:
            order_total+=order;demand+=y[t];served+=immediate;stock_sum+=stock;hold+=stock*cost*c['carry_rate']/52;weeks+=1;stockout_weeks+=int(y[t]-immediate>1e-9)
            if trace:rows.append(dict(index=t,demand=y[t],immediate_filled=immediate,end_on_hand=stock,end_backlog=backlog,
              receipts=receipts,ordered=order,pipeline=sum(q for _,q in pipeline),order_up_to=S,carrying_cost=stock*cost*c['carry_rate']/52))
    return dict(fill_rate=served/demand if demand else None,demand=demand,immediate_filled=served,
      avg_on_hand=stock_sum/weeks if weeks else 0.,avg_inventory_value=stock_sum/weeks*cost if weeks else 0.,
      carrying_cost=hold,end_backlog=backlog,stockout_weeks=stockout_weeks,weeks=weeks,ordered_units=order_total,
      state=dict(stock=stock,backlog=backlog,pipeline=pipeline),trace=rows)

def stripped(sim):return {k:v for k,v in sim.items() if k not in ('state','trace')}

def aggregate_model(rows):
    n=sum(x['n'] for x in rows);d=sum(x['demand'] for x in rows);a=sum(x['absolute_error'] for x in rows);sq=sum(x['squared_error'] for x in rows);sg=sum(x['signed_error'] for x in rows)
    return dict(mae=a/n if n else None,rmse=math.sqrt(sq/n) if n else None,wape=a/d if d else None,bias=sg/d if d else None,n=n,demand=d)

def bootstrap(items,seed,reps=500):
    clusters=defaultdict(list)
    for s in items:clusters[s['part_id']].append(s)
    vals=list(clusters.values())
    if len(vals)<3:return dict(available=False,reason='At least three distinct parts are required.')
    r=random.Random(seed);costs=[];fills=[]
    for _ in range(reps):
        selected=[s for _ in vals for s in vals[r.randrange(len(vals))]]
        costs.append(mean([s['optimized']['carrying_cost']-s['baseline']['carrying_cost'] for s in selected]))
        den=sum(s['optimized']['demand'] for s in selected)
        fills.append(sum(s['optimized']['immediate_filled']-s['baseline']['immediate_filled'] for s in selected)/den if den else 0.)
    costs.sort();fills.sort();lo=int(.025*(reps-1));hi=int(.975*(reps-1))
    return dict(available=True,replicates=reps,clusters=len(vals),unit='part (all sites kept together)',
      mean_series_carrying_cost_delta_95=[costs[lo],costs[hi]],portfolio_fill_delta_95=[fills[lo],fills[hi]],
      caveat='Exploratory percentile interval. Assumes parts are independent; cross-part/shared-supplier dependence is not modeled.')

def run_experiment(dataset,c,progress=lambda *_:None,cancel=None):
    meta,parts,groups,orders,quality=dataset;c=config_checked(c)
    last=date.fromisoformat(meta['end']);test_start=last-timedelta(weeks=c['test_weeks']-1)
    val_start=test_start-timedelta(weeks=c['validation_weeks']);train_end=val_start-timedelta(weeks=1)
    scope=[(k,rows) for k,rows in sorted(groups.items()) if (not c['site'] or k[0]==c['site']) and (not c['family'] or parts[k[1]]['family']==c['family']) and (not c['criticality'] or parts[k[1]]['criticality']==c['criticality'])]
    total_scope=len(scope)
    if c['max_series']:scope=scope[:c['max_series']]
    if not scope:raise ValueError('No series match these filters.')
    result=[];skipped=[];all_models={m:[] for m in list(dict.fromkeys(c['models']+['ma8']))};champ_metrics=[];grids=[]
    order_index=defaultdict(list)
    for o in orders:order_index[o['part_id']].append(o)
    for ix,((site,pid),rows) in enumerate(scope):
        if cancel and cancel.is_set():raise Cancelled('Experiment cancelled. No partial results promoted.')
        progress(ix,len(scope),f'Evaluating {site} / {pid}')
        dates=[date.fromisoformat(x['week']) for x in rows];reason=None
        if any((b-a).days!=7 for a,b in zip(dates,dates[1:])):reason='Missing or irregular weekly observations; no zero imputation applied.'
        elif dates[-1]!=last:reason='Series does not reach the common final test week.'
        elif val_start not in dates or test_start not in dates:reason='Series does not cover the common validation and test windows.'
        if reason:skipped.append(dict(site_id=site,part_id=pid,reason=reason));continue
        vs=dates.index(val_start);ts=dates.index(test_start)
        if vs<16:skipped.append(dict(site_id=site,part_id=pid,reason='Fewer than 16 training weeks.'));continue
        y=[x['demand'] for x in rows];p=parts[pid];lead=lead_profile(p,order_index[pid],site,train_end.isoformat(),c)
        warmup=max(4,math.ceil(lead['mean_days']/7)+c['review_weeks']+1)
        if c['validation_weeks']<warmup+4:
            skipped.append(dict(site_id=site,part_id=pid,reason=f'Validation needs at least {warmup+4} weeks for this lead time.'));continue
        f=forecasts(y);vm={m:metrics(y[vs:ts],f[m][vs:ts]) for m in c['models']}
        champion=min(c['models'],key=lambda m:(vm[m]['mae'],c['models'].index(m)))
        def errsigma(m):
            errs=[y[t]-f[m][t] for t in range(max(1,vs-52),vs)]
            return statistics.pstdev(errs) if len(errs)>1 else 0.
        sigma=errsigma(champion);bsigma=errsigma('ma8')
        observed=rows[vs-1]['on_hand'];blocked=rows[vs-1].get('blocked_stock') or 0.
        initial=max(0.,observed-(blocked if c['stock_basis']=='subtract_blocked' else 0.)) if observed is not None else mean(y[:vs])*(math.ceil(lead['mean_days']/7)+c['review_weeks'])
        state=dict(stock=initial,backlog=rows[vs-1].get('backorders') or 0.,pipeline=[])
        seed=int(hashlib.sha256(f'{c["seed"]}|{site}|{pid}'.encode()).hexdigest()[:16],16);rng=random.Random(seed)
        draws=[max(1,math.ceil(rng.choice(lead['samples_days'])/7)) for _ in y]
        candidates=[]
        for z in GRID:
            sim=simulate(y,f[champion],vs,ts,state,lead,c,z,sigma,p['unit_cost'],draws,vs+warmup)
            feasible=sim['fill_rate'] is None or sim['fill_rate']>=c['target']
            candidates.append((z,sim,feasible));grids.append(dict(site_id=site,part_id=pid,model=champion,buffer_z=z,feasible=feasible,**stripped(sim)))
        feasible=[x for x in candidates if x[2]]
        selected=min(feasible,key=lambda x:(x[1]['carrying_cost'],x[1]['end_backlog'],x[0])) if feasible else min(candidates,key=lambda x:(-(x[1]['fill_rate'] or 0),x[1]['carrying_cost'],x[0]))
        z,validation,ok=selected
        baseval=simulate(y,f['ma8'],vs,ts,state,lead,c,1.645,bsigma,p['unit_cost'],draws,vs+warmup)
        # Preserve review cadence across validation/test boundaries.
        # simulate uses start for cadence, so require an offset when continuing.
        optimized=simulate(y,f[champion],vs,len(y),state,lead,c,z,sigma,p['unit_cost'],draws,ts,True)
        baseline=simulate(y,f['ma8'],vs,len(y),state,lead,c,1.645,bsigma,p['unit_cost'],draws,ts,True)
        tm={m:metrics(y[ts:],f[m][ts:len(y)]) for m in all_models}
        for m in all_models:all_models[m].append(tm[m])
        champ_metrics.append(tm[champion])
        future_values=future(y,champion,c['horizon']);seg=segment(y[:vs])
        current=rows[-1];usable=None if current['on_hand'] is None else max(0,current['on_hand']-((current['blocked_stock'] or 0) if c['stock_basis']=='subtract_blocked' else 0))
        S=target_stock(future_values[0],sigma,lead,c,z)
        open_orders=[o for o in order_index[pid] if o.get('site_id')==site and o['order_date']<=meta['end'] and (not o['receipt_date'] or o['receipt_date']>meta['end'])]
        known_pipeline=sum(max(0.,(o['quantity'] or 0.)) for o in open_orders)
        unknown_pipeline=any(o['quantity'] is None for o in open_orders) or not any(o.get('site_id')==site and o.get('quantity') is not None for o in order_index[pid])
        suggested=None if usable is None or unknown_pipeline else max(0,math.ceil(S-usable-known_pipeline+(current['backorders'] or 0.)))
        traces=[]
        for label,sim in [('baseline',baseline),('optimized',optimized)]:
            for row in sim['trace']:traces.append({**row,'week':rows[row['index']]['week'],'policy':label})
        series_forecast=[dict(week=rows[t]['week'],actual=y[t],split='training' if t<vs else 'validation' if t<ts else 'test',predictions={m:f[m][t] for m in all_models}) for t in range(max(0,len(y)-104),len(y))]
        frows=[dict(week=(last+timedelta(weeks=i+1)).isoformat(),forecast=v) for i,v in enumerate(future_values)]
        result.append(dict(site_id=site,part_id=pid,description=p['description'],family=p['family'],criticality=p['criticality'],unit_cost=p['unit_cost'],
          **seg,model=champion,validation_metrics=vm,test_metrics=tm,forecast=series_forecast,future=frows,
          baseline=stripped(baseline),optimized=stripped(optimized),buffer_z=z,validation_feasible=ok,
          validation_policy=stripped(validation),lead={k:v for k,v in lead.items() if k!='samples_days'},sigma=sigma,
          initial_on_hand=initial,initial_stock_source='Observed end-of-training snapshot' if observed is not None else 'Training-only mean protection demand',
          initial_pipeline_assumption='Empty for all policies; supplier order snapshots are not a complete inventory ledger',
          warmup_weeks=warmup,training_weeks=vs,validation_scored_weeks=c['validation_weeks']-warmup,
          target_stock=S,usable_on_hand=usable,known_open_po_units=known_pipeline,unknown_pipeline=unknown_pipeline,suggested_order_units=suggested,
          recommendation_note='Indicative only. No MOQ, packs, supplier capacity, network transfers, repair loop, or expiry optimization. Assumes mapped on-hand/backlog snapshots are end-of-week; partial PO receipts cannot be reconstructed.',
          inventory_trace=traces))
    if not result:raise ValueError('No eligible series. '+ '; '.join(x['reason'] for x in skipped[:4]))
    summary={}
    for label in ('baseline','optimized'):
        demand=sum(s[label]['demand'] for s in result);filled=sum(s[label]['immediate_filled'] for s in result)
        summary[label]=dict(fill_rate=filled/demand if demand else None,carrying_cost=sum(s[label]['carrying_cost'] for s in result),
          avg_inventory_value=sum(s[label]['avg_inventory_value'] for s in result),end_backlog=sum(s[label]['end_backlog'] for s in result),demand=demand,immediate_filled=filled,
          series_meeting_test_target=sum(s[label]['fill_rate'] is not None and s[label]['fill_rate']>=c['target'] for s in result))
    b=summary['baseline'];o=summary['optimized'];delta=o['carrying_cost']-b['carrying_cost']
    summary.update(series=len(result),skipped=len(skipped),scoped_series=total_scope,attempted_series=len(scope),
      carrying_cost_delta=delta,carrying_cost_reduction=(b['carrying_cost']-o['carrying_cost'])/b['carrying_cost'] if b['carrying_cost'] else None,
      fill_rate_delta=o['fill_rate']-b['fill_rate'] if o['fill_rate'] is not None and b['fill_rate'] is not None else None,
      validation_feasible=sum(s['validation_feasible'] for s in result),segments=dict(Counter(s['segment'] for s in result)),champions=dict(Counter(s['model'] for s in result)))
    model_summary={m:aggregate_model(vals) for m,vals in all_models.items()};model_summary['champion']=aggregate_model(champ_metrics)
    progress(len(scope),len(scope),'Computing paired part-clustered bootstrap intervals')
    return dict(version=VERSION,created=now(),config=c,dataset=meta,summary=summary,model_summary=model_summary,series=result,skipped=skipped,policy_grid=grids,
      bootstrap=bootstrap(result,c['seed']),split=dict(training_end=train_end.isoformat(),validation_start=val_start.isoformat(),validation_end=(test_start-timedelta(weeks=1)).isoformat(),test_start=test_start.isoformat(),test_end=last.isoformat()),
      limitations=[
       'This dataset is synthetic (or user-declared). Results are controlled experiments, not measured savings at an actual company.',
       'The bundled demonstration is independent of the Kaggle publisher dataset; imported provenance remains user-declared.',
       'Model choice uses validation MAE. Inventory buffers are selected on validation carrying cost subject to observed validation fill rate; test weeks are never used for selection.',
       'This is a finite-grid local policy search, not a globally optimal mixed-integer or multi-echelon optimizer. An infeasible validation target is explicitly reported.',
       'Consumption is used as demand. Unobserved/stockout-censored demand is not recovered. Source baseline/adjusted forecasts are excluded from model fitting.',
       'Weekly review, backordering, training-only lead distributions, empty starting pipeline, common random numbers, and explicit warm-up are modeling assumptions.',
       'A receipt for an order at end of week t with L full weeks transit arrives at start of t+L+1. On-time fill excludes late fulfillment of prior backorders.',
       'No MOQ, pack sizes, capacity, procurement transaction cost, shortages penalty, scrap dynamics, repair cycles, expiry, hub/spoke design, or transfers are optimized.',
       'Projected order suggestions use the latest imported snapshots and mapped open POs; incomplete/partial receipts may require manual reconciliation.',
       'Seasonal-naive uses an 8-week mean before 52 observations. Short and irregular series are excluded; optional missing fields are disclosed.',
       'Re-running on the same holdout after tuning settings makes it exploratory rather than a new confirmatory test. Preserve an additional untouched final period for the final paper.'
      ])
