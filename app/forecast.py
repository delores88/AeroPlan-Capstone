"""Transparent causal point forecasts; no held-out observations in model selection."""
import math, statistics
MODELS={
 'ma8':'Moving average · 8 weeks', 'naive':'Last-observation naïve',
 'seasonal52':'Seasonal naïve · 52 weeks', 'ses':'Exponential smoothing · α 0.20',
 'sba':'Croston–SBA · α 0.10', 'tsb':'TSB · α/β 0.10'
}

def mean(xs):return sum(xs)/len(xs) if xs else 0.0

def forecasts(y):
    """Return one-step predictions at every t using only y[:t], and next-step values."""
    out={m:[] for m in MODELS};level=0.;size=0.;interval=1.;since=1;initialized=False;prob=0.;tsize=0.
    for t in range(len(y)+1):
        out['ma8'].append(mean(y[max(0,t-8):t]))
        out['naive'].append(y[t-1] if t else 0.)
        out['seasonal52'].append(y[t-52] if t>=52 else mean(y[max(0,t-8):t]))
        out['ses'].append(level)
        out['sba'].append(.95*size/interval if initialized else 0.)
        out['tsb'].append(prob*tsize)
        if t==len(y):break
        v=y[t]
        level=v if t==0 else .2*v+.8*level
        if v>0:
            if not initialized:size=v;interval=t+1.;initialized=True
            else:size=.1*v+.9*size;interval=.1*since+.9*interval
            since=1
            tsize=v if tsize==0 else .1*v+.9*tsize
        else:since+=1
        prob=.1*(1. if v>0 else 0.)+.9*prob
    return out

def metrics(actual,pred):
    if not actual:return {'mae':None,'rmse':None,'wape':None,'bias':None,'n':0,'demand':0.,'absolute_error':0.,'squared_error':0.,'signed_error':0.}
    errors=[p-a for a,p in zip(actual,pred)];den=sum(actual)
    return dict(mae=mean([abs(e) for e in errors]),rmse=math.sqrt(mean([e*e for e in errors])),
      wape=sum(abs(e) for e in errors)/den if den else None,bias=sum(errors)/den if den else None,
      n=len(errors),demand=den,absolute_error=sum(abs(e) for e in errors),squared_error=sum(e*e for e in errors),signed_error=sum(errors))

def segment(y):
    nz=[v for v in y if v>0]
    if not nz:return dict(segment='No demand',adi=None,cv2=None,nonzero=0)
    adi=len(y)/len(nz);mu=mean(nz);cv2=(statistics.pvariance(nz) if len(nz)>1 else 0)/(mu*mu)
    label='Smooth' if adi<1.32 and cv2<.49 else 'Erratic' if adi<1.32 else 'Intermittent' if cv2<.49 else 'Lumpy'
    return dict(segment=label,adi=adi,cv2=cv2,nonzero=len(nz))

def future(y,model,horizon):
    # Recursive seasonal/naïve projections; SBA/TSB/SES point level held constant.
    f=forecasts(y)
    if model in ('sba','tsb','ses','ma8'):return [f[model][-1]]*horizon
    ext=list(y);out=[]
    for _ in range(horizon):
        v=(ext[-52] if len(ext)>=52 else mean(ext[-8:])) if model=='seasonal52' else ext[-1] if ext else 0.
        out.append(v);ext.append(v)
    return out
