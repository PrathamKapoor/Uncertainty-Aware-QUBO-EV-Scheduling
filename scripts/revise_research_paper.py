"""Edit the user-selected DOCX and retain its existing cover and styles."""
import json, gzip
from copy import deepcopy
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

source=Path('docs/final/EV_QUBO_Research_Paper.docx')
target=Path('docs/final/EV_QUBO_Research_Paper_Revised.docx')
figs=Path('docs/final/revision_figures'); figs.mkdir(exist_ok=True)
with gzip.open('artifacts/revised_v2/earliest_baseline.json.gz','rt') as f: single=json.load(f)
multi=json.loads(Path('artifacts/revised_v2/multi_ev_comparison.json').read_text())
sens=json.loads(Path('artifacts/revised_v2/duplicate_sensitivity.json').read_text())
keys=['F0','F1','F_early','buffer_80','buffer_90','buffer_95']
labels=['F0','F1','Early','Buf 80','Buf 90','Buf 95']
for metric,filename,ylabel,scale in [('feasibility_rate','completion.png','Simulated service completion (%)',100),('mean_unmet_kWh','unmet.png','Mean unmet energy (kWh)',1)]:
    vals=[single['methods'][k]['evaluation'][metric]*scale for k in keys]
    fig,ax=plt.subplots(figsize=(7,3)); bars=ax.bar(labels,vals,color=['#ddd','#bbb','#666','#999','#777','#eee'],edgecolor='black',hatch=['','','//','','','xx'])
    ax.set_ylabel(ylabel); ax.set_ylim(0,max(vals)*1.22); ax.spines[['top','right']].set_visible(False)
    for b,v in zip(bars,vals): ax.text(b.get_x()+b.get_width()/2,b.get_height()+max(vals)*.02,f'{v:.1f}' if scale==100 else f'{v:.3f}',ha='center',fontsize=8)
    fig.tight_layout(); fig.savefig(figs/filename,dpi=180,bbox_inches='tight'); plt.close(fig)
fig,ax=plt.subplots(figsize=(7,2.7)); ax.axis('off')
labels1=['Observed\nconnection data','Validate and\nsplit','Calibrate\nscenarios / buffers','F0 / F1 / buffer\nQUBO and greedy','Exact and QAOA\n(two EVs)','Physical metrics\nand statistics']
points=[(.16,.75),(.50,.75),(.84,.75),(.84,.25),(.50,.25),(.16,.25)]
for label,(x,y) in zip(labels1,points): ax.text(x,y,label,ha='center',va='center',fontsize=9,transform=ax.transAxes,bbox=dict(boxstyle='round,pad=.4',fc='white',ec='black'))
for a,b in [((.26,.75),(.39,.75)),((.61,.75),(.72,.75)),((.84,.60),(.84,.40)),((.72,.25),(.61,.25)),((.39,.25),(.26,.25))]: ax.annotate('',xy=b,xytext=a,xycoords='axes fraction',arrowprops=dict(arrowstyle='->'))
fig.savefig(figs/'architecture.png',dpi=180,bbox_inches='tight');plt.close(fig)

d=Document(source)
paragraphs=d.paragraphs
def settext(par,text):
    if par.runs:
        par.runs[0].text=text
        for run in par.runs[1:]: run.text=''
    else: par.add_run(text)
def before(anchor,text,style=None):
    p=d.add_paragraph(text,style=style); anchor._p.addprevious(p._p)
    p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
    return p
def before_table(anchor, title, headers, rows):
    cap=before(anchor,title); cap.paragraph_format.keep_with_next=True; cap.alignment=WD_ALIGN_PARAGRAPH.LEFT
    for r in cap.runs: r.bold=True
    t=d.add_table(rows=0,cols=len(headers)); anchor._p.addprevious(t._tbl)
    borders=OxmlElement('w:tblBorders')
    for name in ('top','bottom','insideH','insideV','left','right'):
        item=OxmlElement('w:'+name);item.set(qn('w:val'),'single' if name in ('top','bottom') else 'nil');item.set(qn('w:sz'),'6');borders.append(item)
    t._tbl.tblPr.append(borders)
    for i,row in enumerate([headers]+rows):
        cells=t.add_row().cells
        for c,v in zip(cells,row):
            c.text=str(v)
            for p in c.paragraphs:
                p.paragraph_format.space_after=Pt(2); p.paragraph_format.keep_with_next=(i<len(rows))
                for r in p.runs:r.font.name='Times New Roman';r.font.size=Pt(10)
        cells[0]._tc.getparent().get_or_add_trPr().append(OxmlElement('w:cantSplit'))

assert paragraphs[2].text=='Quantum Computing' and 'Sreemoyee Sarkar' in paragraphs[9].text
assert 'B078' in paragraphs[6].text
settext(paragraphs[16], 'Pratham Kapoor, Ayaan Makhani, Vinayak Rastogi, Yashvardhan Wagh')
settext(paragraphs[20], 'Electric-vehicle charging schedules must supply energy despite limited connection time and site capacity. This exploratory study compares nominal and scenario-averaged QUBOs, earliest feasible charging, and calibration-derived deadline buffers. Among 22,083 later public charging transactions, observed connection durations provide counterfactual availability; the 30-minute deadline, energy target, power and tariffs are assumed. Simulated completion is 85.01% for the nominal schedule and 93.56% for both earliest charging and the 90th-percentile buffer. The 95th-percentile buffer leaves no complete slot. A synthetic two-EV example introduces a binding capacity limit: scenario, buffer and earliest policies choose the same early allocation, which is also a nominal-optimum tie. Exact enumeration and Qiskit Aer simulations compare QUBOs with six or eight logical qubits, using depths p=1 and p=2 across five seeds. The results expose the importance of baseline choice and tie-breaking; they do not establish real-world deployment benefits or quantum advantage.')
settext(paragraphs[32], 'Figure 1. Data, calibration, model construction and evaluation pipeline. The two-EV scenarios are modeled, not reconstructed fleet sessions.')
settext(paragraphs[30], paragraphs[30].text.replace('Thirteen duplicate full rows remain; their effect has not been separately assessed.', 'Thirteen duplicate full rows remain; a removal sensitivity check is reported below.'))
settext(paragraphs[40], paragraphs[40].text + ' The additional F_early policy fills physically available slots chronologically; ties between EVs follow their declared order.')
paragraphs[38].paragraph_format.keep_with_next=True
paragraphs[39].paragraph_format.keep_with_next=True
before(paragraphs[41], 'For F1, the objective is min(x, s₁,…,sK) Σₛ pₛ fₛ(x, sₛ), where K is the number of calibrated groups, pₛ is its empirical frequency, x is the shared schedule, and each sₛ is scenario-specific capacity slack. Each scenario changes availability, delivered energy, cost and the capacity residual. The model is risk-neutral scenario averaging, not a worst-case guarantee.')
settext(paragraphs[56], paragraphs[56].text.replace('The five methods', 'The six methods'))
settext(paragraphs[57], 'The paired 90% buffer versus F0 comparison uses a 2,000-replicate calendar-day block bootstrap across 92 evaluation days. User- and charger-cluster sensitivity analyses are reported separately. These analyses do not remove all cross-cluster dependence. The analysis is exploratory and the buffer levels are not a confirmatory multiple-comparison study. The original one-EV QAOA uses p=1 and one seed; a separate synthetic two-EV case tests p=1 and p=2 with five seeds and 128 shots each for F0, F1 and the buffer.')
settext(paragraphs[62], 'As Table 2 and Figure 3 show, F0 and F1 select the same later slot in this particular instance. The 90% buffer moves charging to the first slot and achieves 93.56% modeled completion, 8.55 percentage points above F0; the day-block interval is 8.20 to 8.91 points. F_early chooses the identical first slot and has identical completion, unmet energy and cost. Thus the improvement is over the cost-oriented F0 baseline, not over earliest feasible charging. The interval describes this counterfactual model, not a real-world improvement.')
settext(paragraphs[68], 'The earlier 90% and F_early schedules use a higher assumed tariff: mean realized expenditure is 0.2339 arbitrary currency units versus 0.1063 for F0. These means use modeled energy actually delivered, not a fixed equal-energy purchase: F0 often delivers less, which lowers its expenditure. The full-target nominal costs are 0.25 for the early schedule and 0.125 for the later schedule. No observed customer bills or economic benefits are inferred.')
settext(paragraphs[76], 'The public-data comparison models a single EV; requests, power, capacity, tariffs and nominal deadlines are assumed, not observed driver inputs. The two-EV experiment is also synthetic, uses two equally weighted scenarios and does not reconstruct a historical fleet. Its F0 tie-breaking materially changes the reported comparison. Day-, charger- and user-cluster intervals are separate sensitivity checks and do not fully account for overlapping dependence. QAOA is simulated on Aer with limited seeds, shots and optimization budgets. No hardware execution, noise resilience, industrial scalability or quantum advantage is demonstrated.')
settext(paragraphs[78], 'In the single-EV counterfactual, the 90% buffer improves modeled completion over the cost-oriented nominal schedule but exactly matches earliest feasible charging; the 95% buffer removes all usable full slots. In the synthetic two-EV case, capacity creates a meaningful scheduling conflict, yet an equally optimal nominal tie can match the scenario, buffer and greedy allocation. The findings demonstrate baseline and tie-breaking sensitivity rather than a unique benefit of calibration. Future work should validate on decision-time requests, independent multi-EV site data and broader quantum experiments.')
paragraphs[78].paragraph_format.keep_together=True

row=d.tables[1].add_row()
for c,v in zip(row.cells,['F_early','—','93.56','0.0161']):
    c.text=v
    for p in c.paragraphs:
        for r in p.runs:r.font.name='Times New Roman';r.font.size=Pt(10)
d.tables[1].rows[3]._tr.addprevious(row._tr)
for shape_index,file in [(1,'architecture.png'),(3,'completion.png'),(4,'unmet.png')]:
    rid=d.inline_shapes[shape_index]._inline.graphic.graphicData.pic.blipFill.blip.embed
    d.part.related_parts[rid]._blob=(figs/file).read_bytes()

anchor=paragraphs[75]
before(anchor,'Multi-EV capacity and sensitivity',style='Heading 2')
before(anchor,'A separate synthetic instance has two EVs, two 15-minute slots, 1 kW charging power per EV, a 1 kW shared site limit, and a 0.25 kWh target for each. Both EVs have the same nominal arrival and departure windows. Two equally weighted modeled cases either retain both windows or end EV A’s window one slot early; these are illustrative assumptions, not historical fleet schedules. Simultaneous charging exceeds capacity, so the site constraint genuinely binds.')
before_table(anchor,'Table 4. Synthetic two-EV comparison (two equally weighted scenarios)', ['Method','A slots','B slots','Joint completion','Unmet kWh','Mean cost'], [
    ['F0','01','10','50%','0.125','0.3125'],['F1','10','01','100%','0','0.3750'],['F_early','10','01','100%','0','0.3750'],['Buffer','10','01','100%','0','0.3750']])
before(anchor,'Table 4 reports physical outcomes under identical scenarios. F0’s displayed solution is selected by lexicographic tie-breaking; an equally optimal nominal solution assigns EV A the earlier slot and matches the other methods. Hence the 50% versus 100% difference cannot be credited uniquely to the buffer or to scenario optimization. All successful nominal schedules purchase 0.5 kWh for 0.375 arbitrary units. F0’s lower average realized cost reflects its failure to deliver 0.125 kWh in one case.')
before(anchor,'Deleting the 13 identical full rows did not change the calibrated 7-minute buffer or the 22,083-record evaluation result. The day-block interval uses 92 days. A charger-cluster interval is 7.78–9.45 percentage points over 1,661 charger IDs; an identifiable-user interval is 9.88–12.67 points over 1,254 nonzero user IDs and 13,684 records. These resampling units overlap and the user subset differs, so the intervals are sensitivity analyses rather than interchangeable independent evidence.')
rows=[]
for name in ['F0','F1','F_buffer']:
    q=multi['quantum'][name]
    for pdepth in [1,2]:
        runs=[r for r in q['runs'] if r['p']==pdepth]
        rows.append([name,str(pdepth),f"{q['qubits']} ({q['slack_qubits']})",f"{100*np.mean([r['p_optimal'] for r in runs]):.2f} ± {100*np.std([r['p_optimal'] for r in runs],ddof=1):.2f}", f"{100*np.mean([r['p_nominal_physical_feasible'] for r in runs]):.2f}", f"{runs[0]['transpiled_depth']} / {runs[0]['cx']}"])
before_table(anchor,'Table 5. Two-EV QAOA: five seeds, 128 shots per run',['Model','p','Qubits (slack)','Optimal % mean ± SD','Nominal feasible %','Depth / CX'],rows)
before(anchor,'Table 5 uses sample standard deviation across five optimizer seeds; individual shots are not independent optimization trials. Each QUBO has four charging-decision qubits. F1 adds four scenario-specific slack qubits, while F0 and the buffer add two. All small QUBO and Ising basis energies were checked exhaustively. The exact minimum of each tested objective is 0.375 in its own formulation; values from different objectives are not used as physical-quality comparisons. The limited runs do not show quantum advantage.')
d.core_properties.author='Pratham Kapoor; Ayaan Makhani; Vinayak Rastogi; Yashvardhan Wagh'
d.save(target)
print(target)
