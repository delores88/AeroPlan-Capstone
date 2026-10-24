"""Offline instructor evidence: PDF, self-contained HTML, CSV, JSON and ZIP."""
import csv, hashlib, html, io, json, zipfile
from collections import defaultdict
from pathlib import Path
from .pdf import PDF
from .forecast import MODELS
from .schema import SOURCE_URL

REFERENCE_TEXT='Hyndman, R. J., & Athanasopoulos, G. (2021). Forecasting: Principles and Practice (3rd ed.). OTexts. Chapters 5.8 and 5.10. https://otexts.com/fpp3/accuracy.html ; https://otexts.com/fpp3/tscv.html'

def h(x):return html.escape(str(x))
def pct(x):return 'N/A' if x is None else f'{x*100:,.1f}%'
def number(x,digits=0):return 'N/A' if x is None else f'{x:,.{digits}f}'
def money(x):return 'CU '+number(x,2)
def source_label(r):return 'DEMONSTRATION - NOT KAGGLE DATA' if r['dataset']['source_kind']=='demo' else 'USER-IMPORTED '+('KAGGLE SYNTHETIC DATA' if r['dataset']['source_kind']=='kaggle' else 'LOCAL DATA')

def csv_bytes(rows):
    rows=list(rows)
    if not rows:return b''
    headers=list(dict.fromkeys(k for r in rows for k in r));s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=headers);w.writeheader()
    for row in rows:
        safe={}
        for k,v in row.items():
            if isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False)
            if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')):v="'"+v
            safe[k]=v
        w.writerow(safe)
    return s.getvalue().encode('utf-8-sig')

def series_rows(r):
    for s in r['series']:
        yield dict(site_id=s['site_id'],part_id=s['part_id'],family=s['family'],criticality=s['criticality'],segment=s['segment'],adi=s['adi'],cv2=s['cv2'],model=s['model'],
          test_wape=s['test_metrics'][s['model']]['wape'],test_mae=s['test_metrics'][s['model']]['mae'],
          baseline_fill_rate=s['baseline']['fill_rate'],optimized_fill_rate=s['optimized']['fill_rate'],baseline_carrying_cost=s['baseline']['carrying_cost'],optimized_carrying_cost=s['optimized']['carrying_cost'],
          baseline_avg_inventory_value=s['baseline']['avg_inventory_value'],optimized_avg_inventory_value=s['optimized']['avg_inventory_value'],
          validation_feasible=s['validation_feasible'],buffer_z=s['buffer_z'],target_stock=s['target_stock'],lead_days=s['lead']['mean_days'],lead_source=s['lead']['source'],
          usable_on_hand=s['usable_on_hand'],known_open_po_units=s['known_open_po_units'],unknown_pipeline=s['unknown_pipeline'],indicative_order_units=s['suggested_order_units'])

def pdf_report(run,notes=None):
    r=run['result'];s=r['summary'];c=r['config'];notes=notes or {};p=PDF(source_label(r));b=s['baseline'];o=s['optimized']
    p.heading('Forecasting & inventory policy study')
    p.paragraph(c['name'],12);p.paragraph(f"Author: {notes.get('author') or 'Not specified'} | Run: {run['id']} | Created: {r['created']}")
    p.paragraph(source_label(r),11);p.paragraph('This document is a computed evidence summary, not the Module 1 research proposal or a claim of real-company savings.')
    p.heading('Held-out results',2)
    p.table(['Measure','Fixed-buffer baseline','Validation-selected policy'],[
      ('Immediate unit fill rate',pct(b['fill_rate']),pct(o['fill_rate'])),
      (f"Carrying cost / {c['test_weeks']} test weeks",money(b['carrying_cost']),money(o['carrying_cost'])),
      ('Average on-hand inventory value',money(b['avg_inventory_value']),money(o['avg_inventory_value'])),
      ('Final outstanding backlog',number(b['end_backlog']),number(o['end_backlog'])),
      ('Series meeting test fill target',number(b['series_meeting_test_target']),number(o['series_meeting_test_target']))
    ],[224,140,160])
    p.paragraph(f"Evaluated {s['series']} site-part series; skipped {s['skipped']}. {s['validation_feasible']} of {s['series']} found a feasible buffer in validation. Requested fill target: {pct(c['target'])}.")
    p.paragraph(f"Optimized minus baseline carrying cost: {money(s['carrying_cost_delta'])}. Fill-rate change: {'N/A' if s['fill_rate_delta'] is None else str(round(s['fill_rate_delta']*100,2))+' percentage points'}. A validation target does not guarantee test-period service.")
    p.paragraph('CU means currency units from the imported unit-cost field; no currency conversion or dollar denomination is assumed.')
    p.heading('Forecast accuracy on test weeks',2)
    p.table(['Model','MAE','RMSE','WAPE','Bias'],[(('Selected / per series' if m=='champion' else MODELS[m]),number(v['mae'],2),number(v['rmse'],2),pct(v['wape']),pct(v['bias'])) for m,v in r['model_summary'].items()],[228,70,70,78,78])
    p.new_page();p.heading('Research design & reproducibility')
    p.paragraph(notes.get('question') or 'How do demand-model selection and service-constrained inventory policies change simulated inventory investment and part availability relative to a fixed-buffer baseline?')
    p.heading('Chronological split',2)
    for k,v in r['split'].items():p.paragraph(f'{k.replace("_"," ").capitalize()}: {v}')
    p.paragraph(f"Scope: site={c['site'] or 'all'}, family={c['family'] or 'all'}, criticality={c['criticality'] or 'all'}. Limit={c['max_series'] or 'all'} sorted site-part keys. Seed={c['seed']}. Annual carrying rate={pct(c['carry_rate'])}; review every {c['review_weeks']} week(s); lead-time multiplier={c['lead_factor']}.")
    p.heading('Procedure',2)
    for text in r['limitations'][2:8]:p.paragraph(text)
    p.heading('Uncertainty',2)
    boot=r['bootstrap']
    if boot['available']:
        p.paragraph(f"Part-clustered bootstrap: {boot['replicates']} replicates, {boot['clusters']} part clusters. Exploratory 95% interval for mean per-series holding-cost difference (optimized minus baseline): {money(boot['mean_series_carrying_cost_delta_95'][0])} to {money(boot['mean_series_carrying_cost_delta_95'][1])}. {boot['caveat']}")
    else:p.paragraph(boot['reason'])
    if notes.get('notes'):p.heading('Author interpretation',2);p.paragraph(notes['notes'])
    p.new_page();p.heading('Series-level decisions')
    p.paragraph('First 24 series by site-part key. The accompanying CSV contains every evaluated series. A buffer is selected in validation, never by test performance.')
    p.table(['Site / Part','Model','Baseline fill','Selected fill','Target units'],[(x['site_id']+' / '+x['part_id'],x['model'],pct(x['baseline']['fill_rate']),pct(x['optimized']['fill_rate']),number(x['target_stock'])) for x in r['series'][:24]],[174,76,90,90,94])
    p.new_page();p.heading('Data provenance & limitations')
    d=r['dataset'];p.paragraph(f"Dataset: {d['title']} | Source: {source_label(r)}\nAuthor: {d['source_author']}\nLicense: {d['license']}\nImported: {d['imported_at']}\nRows: {d['history_rows']:,}; parts: {d['parts']:,}; series: {d['series']:,}; purchase orders: {d['purchase_orders']:,}.")
    for text in r['limitations'][:2]+r['limitations'][8:]:p.paragraph(text)
    p.heading('CSV SHA-256 provenance',2)
    for name,value in d['file_hashes'].items():p.paragraph(f'{name}\n{value}',8)
    p.heading('Source references',2)
    p.paragraph(REFERENCE_TEXT,9)
    p.paragraph('TIENTCHEU, R. C. (n.d.). Aerospace Supply Chain Performance & Forecasting [Synthetic dataset]. Kaggle. MIT license listed on data card. '+SOURCE_URL,9)
    p.paragraph('These references document the proposed public dataset and evaluation approach. The independent bundled demonstration must not be attributed to the dataset publisher. Add your course textbook and assignment-specific references to the separate proposal.',9)
    return p.bytes()

def svg_lines(series,width=900,height=240):
    ys=[v for _,vals,_ in series for v in vals if v is not None];mx=max(ys+[1])*1.08;n=max([len(vals) for _,vals,_ in series]+[1]);left=52;top=12;bottom=height-30;right=width-12
    out=[f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Actual and forecast consumption"><rect width="100%" height="100%" fill="white"/>']
    for i in range(5):
        y=bottom-(bottom-top)*i/4;out.append(f'<line x1="{left}" y1="{y}" x2="{right}" y2="{y}" stroke="#e5eaf1"/><text x="4" y="{y+4}" font-size="11" fill="#64748b">{mx*i/4:.0f}</text>')
    for name,vals,col in series:
        points=' '.join(f'{left+i*(right-left)/max(n-1,1):.2f},{bottom-v/mx*(bottom-top):.2f}' for i,v in enumerate(vals) if v is not None)
        out.append(f'<polyline fill="none" stroke="{col}" stroke-width="2.1" points="{points}"/>')
    out.append('</svg>');return ''.join(out)

def html_report(run,notes=None):
    r=run['result'];s=r['summary'];c=r['config'];d=r['dataset'];notes=notes or {};b=s['baseline'];o=s['optimized']
    modelrows=''.join(f'<tr><td>{h("Selected per series" if m=="champion" else MODELS[m])}</td><td>{number(v["mae"],2)}</td><td>{number(v["rmse"],2)}</td><td>{pct(v["wape"])}</td><td>{pct(v["bias"])}</td></tr>' for m,v in r['model_summary'].items())
    rows=''.join(f'<tr><td>{h(x["site_id"])}</td><td>{h(x["part_id"])}</td><td>{h(x["segment"])}</td><td>{h(x["model"])}</td><td>{pct(x["baseline"]["fill_rate"])}</td><td>{pct(x["optimized"]["fill_rate"])}</td><td>{money(x["optimized"]["carrying_cost"])}</td><td>{number(x["target_stock"])}</td><td>{"Yes" if x["validation_feasible"] else "No"}</td></tr>' for x in r['series'])
    agg=defaultdict(lambda:[0.,0.])
    for x in r['series']:
        for f in x['forecast']:
            if f['split']=='test':agg[f['week']][0]+=f['actual'];agg[f['week']][1]+=f['predictions'][x['model']]
    chart=svg_lines([('Actual',[v[0] for _,v in sorted(agg.items())],'#1c334e'),('Selected',[v[1] for _,v in sorted(agg.items())],'#087f8c')])
    limits=''.join(f'<li>{h(x)}</li>' for x in r['limitations'])
    split=''.join(f'<div><span>{h(k.replace("_"," "))}</span><strong>{h(v)}</strong></div>' for k,v in r['split'].items())
    facts=''.join(f'<tr><td>{h(n)}</td><td class="hash">{h(v)}</td></tr>' for n,v in d['file_hashes'].items())
    warnings=''.join(f'<p>{h(x)}</p>' for x in d['warnings'])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AeroPlan | Instructor evidence</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa;color:#20324b;font:15px/1.65 system-ui,Segoe UI,sans-serif}}main{{max-width:1120px;margin:auto;padding:42px 24px}}header{{background:#11253c;color:white;padding:40px;border-radius:20px}}.eyebrow{{font-size:11px;letter-spacing:2px;font-weight:750}}h1{{font-size:34px;line-height:1.2;margin:14px 0}}h2{{font-size:22px}}.tag{{background:#fff2d6;color:#744710;padding:10px 16px;border-radius:8px;font-weight:700}}section{{background:white;padding:28px;margin-top:22px;border:1px solid #e1e7ef;border-radius:16px}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:22px}}.metric{{padding:22px;background:white;border-radius:12px;border:1px solid #e1e7ef}}.metric strong{{display:block;font-size:27px;color:#152d48}}.metric span,small{{color:#65758a}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:11px;text-align:left;border-bottom:1px solid #e5eaf0}}th{{background:#f5f8fb}}.scroll{{overflow:auto}}.split{{display:flex;gap:20px;flex-wrap:wrap}}.split strong,.split span{{display:block}}.split span{{font-size:12px;color:#66778a;text-transform:capitalize}}.hash{{font:11px monospace;word-break:break-all}}button,input{{padding:10px 14px;font:inherit;border:1px solid #cdd7e2;border-radius:7px;background:white}}button{{cursor:pointer}}.print{{float:right}}svg{{width:100%;height:auto}}li{{margin:10px 0}}.notice{{background:#fff7e7;border:1px solid #f0dfb5;padding:14px;border-radius:10px}}@media(max-width:760px){{.metrics{{grid-template-columns:1fr 1fr}}header{{padding:25px}}}}@media print{{body{{background:white}}main{{padding:0}}.print,input{{display:none}}section,.metric{{break-inside:avoid}}header{{color:#11253c;background:white;padding:10px 0}}}}
    </style></head><body><main><header><button class="print" onclick="window.print()">Print / save PDF</button><div class="eyebrow">AEROPLAN LOCAL / INSTRUCTOR EVIDENCE</div><h1>{h(c['name'])}</h1><p>Forecasting and inventory policy evaluation for industrial parts.</p><p>Author: {h(notes.get('author') or 'Not specified')} · Run {h(run['id'])} · v{h(r['version'])}</p><div class="tag">{h(source_label(r))}</div></header>
    <div class="metrics"><div class="metric"><span>Selected policy · test fill rate</span><strong>{pct(o['fill_rate'])}</strong><small>Baseline {pct(b['fill_rate'])}</small></div><div class="metric"><span>Selected policy · holding cost</span><strong>{money(o['carrying_cost'])}</strong><small>{c['test_weeks']} test weeks</small></div><div class="metric"><span>Average inventory value</span><strong>{money(o['avg_inventory_value'])}</strong><small>Baseline {money(b['avg_inventory_value'])}</small></div><div class="metric"><span>Evaluated site–part series</span><strong>{s['series']}</strong><small>{s['skipped']} excluded; {s['validation_feasible']} validation-feasible</small></div></div>
    <section><h2>Research question</h2><p>{h(notes.get('question') or 'How do demand-model selection and service-constrained inventory policies change simulated inventory investment and part availability relative to a fixed-buffer baseline?')}</p><div class="notice">This is a computed evidence package, not the written Module 1 proposal. A synthetic experiment does not establish real-company savings. CU denotes currency units, not an assumed currency.</div></section>
    <section><h2>Held-out consumption and selected-model forecast</h2><p>Dark: recorded consumption. Teal: causal, one-week-ahead forecast. Test period {h(r['split']['test_start'])} through {h(r['split']['test_end'])}.</p>{chart}</section>
    <section><h2>Chronological evaluation</h2><div class="split">{split}</div><p>Models are selected by validation MAE per series. Inventory buffers are selected on validation holding cost subject to achieved validation fill. The fixed baseline uses an 8-week moving average and a 1.645-sigma buffer. Both use the same lead-time draws and opening conditions.</p><p>Review: {c['review_weeks']} week(s) · Annual carrying rate: {pct(c['carry_rate'])} · Fill target: {pct(c['target'])} · Lead multiplier: {c['lead_factor']} · Seed: {c['seed']}.</p></section>
    <section><h2>Forecast model comparison</h2><div class="scroll"><table><thead><tr><th>Model</th><th>MAE</th><th>RMSE</th><th>WAPE</th><th>Bias</th></tr></thead><tbody>{modelrows}</tbody></table></div><p>WAPE and bias are undefined for zero aggregate demand, rather than silently reported as zero. Bias is forecast minus actual, divided by actual demand.</p></section>
    <section><h2>Series-level decisions</h2><input id="filter" type="search" placeholder="Filter site, part, segment or model" aria-label="Filter decisions"><div class="scroll"><table id="decisions"><thead><tr><th>Site</th><th>Part</th><th>Segment</th><th>Model</th><th>Baseline fill</th><th>Selected fill</th><th>Holding cost</th><th>Target units</th><th>Validation feasible</th></tr></thead><tbody>{rows}</tbody></table></div></section>
    <section><h2>Data and provenance</h2><p><strong>{h(d['title'])}</strong><br>{h(d['source_author'])} · {h(d['license'])}<br>{d['history_rows']:,} source history rows · {d['parts']:,} parts · {d['sites']:,} sites · {d['purchase_orders']:,} purchase orders.<br>Imported {h(d['imported_at'])}. Dataset version {h(d['id'])}.</p>{warnings}<h3>Imported CSV SHA-256 hashes</h3><table>{facts}</table></section>
    <section><h2>Limitations and interpretation</h2><ol>{limits}</ol><h3>Author notes</h3><p>{h(notes.get('notes') or 'No interpretation added. Review these results and write your own conclusions before submitting.')}</p><h3>Exploratory uncertainty calculation</h3><pre style="white-space:pre-wrap;font-size:12px">{h(json.dumps(r['bootstrap'],indent=2))}</pre></section>
    <section><h2>References and reproduction</h2><p>{h(REFERENCE_TEXT)}</p><p>TIENTCHEU, R. C. (n.d.). Aerospace Supply Chain Performance &amp; Forecasting [Synthetic dataset]. Kaggle. {h(SOURCE_URL)}</p><p>The publisher dataset is not included unless explicitly imported by the user. No claims in this report are from that dataset when the report is labeled demonstration.</p><p>See assumptions.json, provenance.json, results/, inputs/ and run.json in the ZIP for the recorded inputs and full calculated outputs. Reproduce using the separate AeroPlan application and the included REPRODUCE.txt. Add the required course textbook and assignment-specific references to the written proposal.</p></section>
    </main><script>document.getElementById('filter').addEventListener('input',function(){{const q=this.value.toLowerCase();document.querySelectorAll('#decisions tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q))}});</script></body></html>'''.encode('utf-8')

def export_zip(run,dataset,notes=None,methodology=''):
    r=run['result'];meta,parts,groups,orders,quality=dataset
    selected={(s['site_id'],s['part_id']) for s in r['series']};pids={x[1] for x in selected}
    payloads={'START_HERE.html':html_report(run,notes),'Instructor_Report.pdf':pdf_report(run,notes),
      'run.json':json.dumps(run,indent=2,allow_nan=False).encode(),'assumptions.json':json.dumps({'config':r['config'],'split':r['split'],'limitations':r['limitations']},indent=2).encode(),
      'provenance.json':json.dumps(meta,indent=2).encode(),'author_notes.json':json.dumps(notes or {},indent=2).encode(),'METHODOLOGY.md':methodology.encode(),
      'results/series_decisions.csv':csv_bytes(series_rows(r)), 'results/policy_grid_validation.csv':csv_bytes(r['policy_grid']),
      'results/excluded_series.csv':csv_bytes(r['skipped']),
      'results/model_metrics.csv':csv_bytes([{'model':m,**v} for m,v in r['model_summary'].items()]),
      'results/weekly_forecasts.csv':csv_bytes([{'site_id':s['site_id'],'part_id':s['part_id'],'week':f['week'],'actual':f['actual'],'split':f['split'],'model':m,'forecast':v} for s in r['series'] for f in s['forecast'] for m,v in f['predictions'].items()]),
      'results/future_forecasts.csv':csv_bytes([{'site_id':s['site_id'],'part_id':s['part_id'],'model':s['model'],**f} for s in r['series'] for f in s['future']]),
      'results/inventory_replay.csv':csv_bytes([{'site_id':s['site_id'],'part_id':s['part_id'],**x} for s in r['series'] for x in s['inventory_trace']]),
      'inputs/parts_master.csv':csv_bytes([parts[p] for p in sorted(pids)]),
      'inputs/supply_chain_history.csv':csv_bytes([x for k in sorted(selected) for x in groups[k]]),
      'inputs/purchase_orders.csv':csv_bytes([o for o in orders if o['part_id'] in pids]),
      'inputs/quality_incidents.csv':csv_bytes(quality),
      'REPRODUCE.txt':b'1. Extract the separate AeroPlan Local application.\n2. Start it with START_APP.cmd (Windows) or python3 launch.py.\n3. Import the CSV files in inputs/ as local data. They use canonical field names; review the mapping. Lead times are in days.\n4. Open assumptions.json and use its experiment settings. These inputs contain only the evaluated scope, not excluded/unselected series.\n5. The bundled run.json is the authoritative original result, including its source status, mappings, hashes, scope, exclusions and timestamps.\n6. Dataset IDs, timestamps and source provenance will differ on re-import; calculated metrics for the same evaluated series and assumptions should match.\n7. No cloud connection, API key, network optimizer or procurement execution is involved.\n',
      'CANVAS_README.txt':b'Instructor: extract this ZIP and open START_HERE.html in a browser, or open Instructor_Report.pdf. No software installation or internet is required to read the report. CSVs/JSON contain the audit trail. This is not an executable app inside Canvas. Submit the PDF separately for convenient grading; attach this ZIP only if the assignment permits ZIP uploads. This evidence package does not replace the 700-word research proposal/title page/textbook references required in Module 1.\n'}
    for optional in ('inputs/purchase_orders.csv','inputs/quality_incidents.csv'):
        if not payloads[optional]:del payloads[optional]
    if meta['source_kind']=='demo':payloads['DEMONSTRATION_NOTICE.txt']=b'Independent test data generated by AeroPlan. NOT the Kaggle publisher dataset. Not suitable for claiming empirical Kaggle findings.'
    payloads['SHA256SUMS.txt']=''.join(f'{hashlib.sha256(v).hexdigest()}  {k}\n' for k,v in sorted(payloads.items())).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,blob in payloads.items():z.writestr(name,blob)
    return out.getvalue()
