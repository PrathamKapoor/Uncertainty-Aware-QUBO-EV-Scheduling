"""Generate the EV scheduling paper and its figures from recorded artifacts."""
import gzip, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from scheduling.revised_qubo import build_revised_qubo
from quantum.qaoa import qubo_to_ising, _build_qaoa_ansatz

OUT = Path('docs/final')
ASSETS = OUT / 'figures'
ASSETS.mkdir(parents=True, exist_ok=True)
with gzip.open('artifacts/revised_v2/public_duration_stress.json.gz', 'rt', encoding='utf-8') as f:
    data = json.load(f)
assert data['dataset']['counts']['raw'] == 72856
assert data['counts']['calibration_total'] == 50185 and data['counts']['evaluation_eligible'] == 22083
names = ['F0', 'F1', 'Buffer 80%', 'Buffer 90%', 'Buffer 95%']
methods = list(data['methods'].values())
plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10, 'figure.dpi':150})

fig, ax = plt.subplots(figsize=(7.2, 2.5)); ax.axis('off')
labels = ['Public session\nrecords', 'Validate and\nsplit by date', 'Calibrate scenarios\nand buffers', 'Construct\nQUBO', 'Exact solver\nand QAOA', 'Decode and\nevaluate']
positions=[(.16,.75),(.5,.75),(.84,.75),(.84,.25),(.5,.25),(.16,.25)]
for label, (x,y) in zip(labels, positions):
    ax.text(x, y, label, ha='center', va='center', fontsize=10, bbox=dict(boxstyle='round,pad=.35', fc='white', ec='black', lw=.9), transform=ax.transAxes)
for a,b in [((.25,.75),(.39,.75)),((.61,.75),(.72,.75)),((.84,.61),(.84,.39)),((.73,.25),(.61,.25)),((.39,.25),(.25,.25))]:
    ax.annotate('',xy=b,xytext=a,xycoords='axes fraction',arrowprops=dict(arrowstyle='->',lw=1))
fig.savefig(ASSETS/'architecture.png',bbox_inches='tight'); plt.close(fig)

fig, ax=plt.subplots(figsize=(7.2,2.0)); ax.set_xlim(-1,33); ax.set_ylim(-.5,3.3)
for y, label, end in [(2.5,'Nominal horizon',30),(1.5,'Buffered horizon',23),(0.5,'Example availability',18)]:
    ax.plot([0,end],[y,y], color='black',lw=5,solid_capstyle='butt'); ax.text(-.5,y,label,ha='right',va='center',fontsize=9)
for x in (0,15,30): ax.axvline(x,linestyle=':',color='gray',lw=.8)
ax.set_xticks([0,15,23,30]); ax.set_xlabel('Minutes since connection'); ax.set_yticks([]); ax.spines[['top','right','left']].set_visible(False)
fig.savefig(ASSETS/'timeline.png',bbox_inches='tight'); plt.close(fig)

for metric, ylabel, filename in [('feasibility_rate','Simulated service completion (%)','completion.png'),('mean_unmet_kWh','Mean simulated unmet energy (kWh)','unmet.png')]:
    vals=[m['evaluation'][metric] * (100 if metric=='feasibility_rate' else 1) for m in methods]
    fig,ax=plt.subplots(figsize=(6.7,2.8)); bars=ax.bar(names,vals,color=['#dddddd','#bbbbbb','#999999','#666666','#eeeeee'],edgecolor='black',hatch=['','','//','','xx'])
    ax.set_ylabel(ylabel); ax.set_ylim(0,max(vals)*1.22 if max(vals) else 1); ax.spines[['top','right']].set_visible(False)
    for bar,v in zip(bars,vals): ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+max(vals)*.025, f'{v:.1f}' if metric=='feasibility_rate' else f'{v:.3f}',ha='center',fontsize=8)
    fig.tight_layout(); fig.savefig(ASSETS/filename,bbox_inches='tight'); plt.close(fig)

model=build_revised_qubo([1],[1],[3],1,[1.,.5],.25,5,5,penalize_unavailable=False)
ising=qubo_to_ising(model.Q,model.c,{(0,i):i for i in range(model.n)})
circ,_=_build_qaoa_ansatz(ising.to_qiskit_op(),1)
fig=circ.draw(output='mpl',fold=-1,scale=.9,style='bw'); fig.savefig(ASSETS/'qaoa.png',dpi=200,bbox_inches='tight'); plt.close(fig)

d=Document(); sec=d.sections[0]; sec.page_width=Inches(8.27); sec.page_height=Inches(11.69)
sec.top_margin=sec.bottom_margin=sec.left_margin=sec.right_margin=Inches(1)
normal=d.styles['Normal']; normal.font.name='Times New Roman'; normal.font.size=Pt(12)
normal.paragraph_format.space_after=Pt(6); normal.paragraph_format.line_spacing=1.08
for nm in ('Title','Heading 1','Heading 2'):
    style=d.styles[nm]; style.font.name='Times New Roman'; style.font.color.rgb=None
    fonts=style.element.get_or_add_rPr().get_or_add_rFonts()
    for key in ('asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme'):
        fonts.attrib.pop(qn('w:'+key),None)
    fonts.set(qn('w:ascii'),'Times New Roman'); fonts.set(qn('w:hAnsi'),'Times New Roman')
    style.font.bold=True; style.font.size=Pt(14 if nm!='Heading 2' else 12)
    style.paragraph_format.space_before=Pt(8); style.paragraph_format.space_after=Pt(4)
sec.different_first_page_header_footer=True
footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
field=OxmlElement('w:fldSimple'); field.set(qn('w:instr'),'PAGE'); footer._p.append(field)
pg=sec._sectPr.find(qn('w:pgNumType'))
if pg is None: pg=OxmlElement('w:pgNumType'); sec._sectPr.append(pg)
pg.set(qn('w:start'),'0')

def p(text='',center=False,bold=False,size=None,space=6):
    para=d.add_paragraph(); para.alignment=WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.JUSTIFY
    para.paragraph_format.space_after=Pt(space); r=para.add_run(text); r.bold=bold
    if size:r.font.size=Pt(size)
    return para
def heading(text): d.add_heading(text,level=1)
def sub(text): d.add_heading(text,level=2)
def eq(text):
    q=p(text,center=True,space=7); q.paragraph_format.keep_together=True
def figure(filename, caption, width=6):
    q=d.add_paragraph(); q.alignment=WD_ALIGN_PARAGRAPH.CENTER; q.paragraph_format.keep_with_next=True
    q.add_run().add_picture(str(ASSETS/filename),width=Inches(width))
    q=p(caption,space=7); q.paragraph_format.keep_together=True; q.runs[0].italic=True; q.runs[0].font.size=Pt(10)
def table(title,headers,rows):
    for line in title.split('\n'):
        q=p(line,bold=True,space=2); q.alignment=WD_ALIGN_PARAGRAPH.LEFT; q.paragraph_format.keep_with_next=True
    t=d.add_table(rows=0, cols=len(headers)); t.alignment=WD_TABLE_ALIGNMENT.CENTER
    props=t._tbl.tblPr; borders=OxmlElement('w:tblBorders')
    for name in ('top','bottom','insideH','insideV','left','right'):
        e=OxmlElement('w:'+name); e.set(qn('w:val'),'single' if name in ('top','bottom') else 'nil'); e.set(qn('w:sz'),'6'); borders.append(e)
    props.append(borders)
    for row_index, row in enumerate([headers]+rows):
        cells=t.add_row().cells
        for c,txt in zip(cells,row):
            c.text=str(txt); c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for par in c.paragraphs:
                par.paragraph_format.space_after=Pt(2)
                par.paragraph_format.keep_with_next = row_index < len(rows)
                for r in par.runs:r.font.name='Times New Roman';r.font.size=Pt(10)
        trPr=cells[0]._tc.getparent().get_or_add_trPr(); trPr.append(OxmlElement('w:cantSplit'))
    d.add_paragraph().paragraph_format.space_after=Pt(1)

title='A Comparative Study of Reliability-Calibrated QUBO Scheduling for Electric Vehicle Charging'
p(title,True,True,16,28).paragraph_format.space_before=Pt(36)
p('Project Report submitted in the partial fulfillment of',True,False,12,6)
p('Research Methodology',True,True,13,20);p('by',True,False,12,10)
for author in ['Pratham Kapoor — A028','Yashvardhan Wagh — B135','Ayaan Makhani — B056','Vinayak Rastogi — B78']:p(author,True,True,12,3)
p('Under the Guidance of',True,False,12,5).paragraph_format.space_before=Pt(16)
p('[Faculty guide name to be confirmed]',True,True,12,26)
p("SVKM's NMIMS University",True,True,14,3);p('(Deemed-to-be University)',True,False,12,20)
logo=d.add_paragraph(); logo.alignment=WD_ALIGN_PARAGRAPH.CENTER
logo.paragraph_format.space_after=Pt(22)
logo.add_run().add_picture(str(ASSETS/'nmims_reference_logo.png'),width=Inches(2.1875))
p('Vile Parle (W), Mumbai – 56',True,False,12,0)
d.add_page_break()
p(title,True,True,14,8);p('Pratham Kapoor, Yashvardhan Wagh, Ayaan Makhani, Vinayak Rastogi',True,False,12,3)
p('Mukesh Patel School of Technology Management & Engineering',True,False,12,2);p("SVKM's NMIMS University, Mumbai, India",True,False,12,8)
heading('Abstract')
p('Electric-vehicle charging schedules must supply energy while respecting limited time and electrical capacity. A vehicle can disconnect before a delayed charging slot. This study compares a nominal schedule, a scenario-averaged schedule and calibration-derived deadline buffers using a quadratic unconstrained binary optimization (QUBO) model. From 72,856 public charging transactions, 72,268 records remain after timestamp and split-boundary exclusions; 22,083 later sessions are used for evaluation. Since declared departures and requested energy are unavailable, the deadline and target are simulated and observed connection durations provide counterfactual availability. Simulated completion is 85.01% for the nominal schedule and 93.56% for a 90th-percentile buffer; a 95th-percentile buffer leaves no complete charging slot. A four-qubit QAOA simulation samples an optimum of the nominal model in 23.83% of 256 shots. The results illustrate a model-specific reliability and cost trade-off, not a demonstrated real-world improvement or quantum advantage.')
p('Keywords: electric vehicles; charging scheduling; uncertainty; QUBO; QAOA; reliability',bold=True)
heading('Introduction')
p('A charging operator must decide when a connected electric vehicle (EV) receives energy. Later charging may be cheaper, but it risks leaving a request unfinished when a connection ends early. Coordinating multiple vehicles also requires respect for electrical limits. This paper asks whether a simple calibration-derived early-completion buffer changes service completion and cost in a small modeled scheduling problem, and how a corresponding binary optimization problem behaves on a quantum simulator.')
p('The contribution is a comparative, exploratory evaluation rather than a claim to have invented deadline buffers or a quantum algorithm. The underlying charging transactions are real, while the requests, tariffs and scheduling actions evaluated here are simulated. The empirical experiment uses one EV; it cannot establish the performance of a fleet controller.')
heading('Related Work')
p('Scenario-based EV charging under uncertain availability and demand has been studied using stochastic programming (Wang et al., 2020). Robust deadline and demand scheduling also has prior work (Sone et al., 2024). Dalyac et al. (2021) examined quantum approaches for industrial smart charging, and Farhi et al. (2014) introduced the quantum approximate optimization algorithm (QAOA). QUBO penalties and slack encodings are established modeling tools (Glover et al., 2019). Our comparison differs in its explicit calibration-to-evaluation split, its examination of an excessively conservative full-slot deadline, and its transparent separation of simulated service from quantum sampling. Those differences do not establish a new algorithm.')
heading('Methodology')
sub('Data preparation and decision-time assumptions')
p('Baek et al. (2024) released charging-session records with connection and disconnection timestamps and delivered energy. The study uses observed connection durations as counterfactual availability. The file does not supply the driver-declared departure time or a decision-time requested-energy field required by the original ACN formulation. Consequently, the nominal deadline and energy request in this experiment are assumed; delivered energy is not treated as true demand.')
p('Records with unparseable timestamps or nonpositive durations are removed. For calibration, sessions beginning before July 1, 2022 but ending on or after that boundary are also excluded, because their full durations would not yet be known. Later sessions form the evaluation set. Timestamp timezone is not established and timestamps are treated as naive local values. Thirteen duplicate full rows remain; their effect has not been separately assessed. Figure 1 shows the actual sequence of analysis.')
figure('architecture.png','Figure 1. Data and optimization pipeline. The QAOA comparison uses the nominal and 90% buffer formulations.')
table('Table 1\nDataset accounting',['Record group','Count'],[['Downloaded','72,856'],['Invalid duration','547'],['Calibration crossing split','41'],['Calibration','50,185'],['Evaluation','22,083']])
p('Table 1 reconciles the downloaded total with the two exclusions and retained records. The dataset is an observational source of durations, not an observed deployment of the schedules constructed here.')
sub('Calibration and scheduling methods')
p('The nominal horizon D is 30 minutes. For a calibration connection duration T, the modeled early-availability difference is D − T. The buffer b at quantile τ is the empirical quantile of the nonnegative early differences:')
eq('bτ = Qτ(max(0, D − T))                                      (1)')
p('Here Qτ is the linear-interpolated sample quantile and τ is a selected level. A conservative schedule uses only complete 15-minute slots ending by D − bτ. F0 uses the nominal window; F1 minimizes the expected penalized objective over eight equal-count calibration groups with empirical weights. Buffer variants use τ = 0.80, 0.90 and 0.95. A session ending later than the nominal horizon does not create extra decision slots.')
figure('timeline.png','Figure 2. Illustrative timing: a 7-minute buffer moves the deadline to 23 minutes, leaving only the first complete slot. The example availability is 18 minutes.')
p('Figure 2 illustrates the rounding convention. A slot contributes energy only if it ends by the realized connection end. If the buffer removes every complete slot, the method has no legal charging opportunity; the service target remains unmet rather than being silently relaxed.')
heading('System Architecture and Quantum Formulation')
sub('Physical model and QUBO')
p('Let xᵢₜ be one when EV i is scheduled to charge in slot t, and zero otherwise. Let Pᵢ be its charging power in kW, Δt the slot length in hours, Eᵢ the assumed energy request in kWh, cₜ the tariff per kWh, and Pmax the site limit in kW. With availability aᵢₜ equal to one for a fully available slot, delivered energy and cost are')
eq('Edelivered,i = Σₜ aᵢₜ Pᵢ Δt xᵢₜ;   C = Σᵢ,ₜ cₜ aᵢₜ Pᵢ Δt xᵢₜ.     (2)')
p('Site loading Lₜ = Σᵢ aᵢₜ Pᵢxᵢₜ should satisfy Lₜ ≤ Pmax. The implemented integer-power model represents unused capacity using nonnegative binary slack sₜ, and adds a squared penalty λc(Lₜ + sₜ − Pmax)². A separate squared penalty λe(Rᵢ − Σₜ aᵢₜxᵢₜ)² uses required slot count Rᵢ. For this experiment, one 1 kW EV needs R=1 slot, Δt=0.25 hours, Pmax=1 kW, and both penalty coefficients are 5. Prices are 1.0 and 0.5 arbitrary currency units per kWh. Thus the energy target is 0.25 kWh.')
p('After expansion, the model takes the quadratic unconstrained binary form f(x) = xᵀQx + c. The vector includes both charging and auxiliary slack bits. Scenario models use separate slack registers, because realized availability can change unused capacity. Penalties are not intrinsically hard constraints: the repository includes a counterexample in which a weak penalty admits an infeasible optimum. Exact enumeration checks the selected tiny instances; it does not prove a universal penalty bound.')
sub('Ising mapping and QAOA')
p('For each binary variable, set xᵢ = (1 − Zᵢ)/2, where Zᵢ has computational-basis eigenvalues +1 and −1. The symmetric QUBO becomes Hc = ΣᵢhᵢZᵢ + Σᵢ<ⱼJᵢⱼZᵢZⱼ + c′. With the repository’s symmetric-matrix convention, hᵢ = −½ΣⱼQᵢⱼ, Jᵢⱼ = Qᵢⱼ/2 and c′ = c + [ΣᵢⱼQᵢⱼ + tr(Q)]/4. Off-diagonal QUBO entries occur twice in xᵀQx. Exhaustive tests verify equality of QUBO and Ising basis energies including c′.')
p('Starting from an equal superposition, QAOA alternates a cost evolution and an X mixer. For p layers, the state is')
eq('|ψ(γ, β)⟩ = ∏ℓ=1…p exp(−iβℓ ΣᵢXᵢ) exp(−iγℓ Hc) |+⟩⊗n.       (3)')
p('The rightmost operation acts first within each layer. Hadamard gates prepare the initial superposition; the cost unitary imprints energy-dependent phases; the mixer changes amplitudes. A classical COBYLA optimizer adjusts γ and β using sampled circuit energies. Measurements yield bitstrings; Qiskit displays qubit zero on the right, so decoding reverses the displayed order. Figure 5 is drawn from the actual nominal circuit. Its first two qubits encode charging decisions, and the last two encode capacity slack.')
heading('Experimental Setup')
p('The 72,268 eligible sessions are split into 50,185 calibration and 22,083 evaluation records. Calibration determines scenario centers and buffers; the later records are not used to fit them. Each observed duration is applied to the same synthetic one-EV problem, so observations do not constitute reconstructed multi-EV site instances. The five methods are evaluated with the same physical decoder. Service completion means that the modeled request is delivered within the realized availability while respecting the modeled capacity. Unmet energy includes zero values in its mean.')
p('The paired 90% buffer versus F0 comparison uses a 2,000-replicate calendar-day block bootstrap across 92 evaluation days. It preserves within-day pairing but cannot account fully for users or chargers recurring on different days. The analysis is exploratory: previous results and the data have been inspected, and the three buffer levels are not a confirmatory multiple-comparison study. Exact enumeration is the reference for small QUBOs. QAOA is run only on F0 and the 90% buffer, with p=1, one seed, 20 COBYLA evaluations and 256 final shots per formulation.')
heading('Results and Discussion')
table('Table 2\nSimulated service outcomes',['Method','Buffer (min)','Completion (%)','Mean unmet (kWh)'],[['F0 nominal','—','85.01','0.0375'],['F1 scenario','—','85.01','0.0375'],['Buffer 80%','0','85.01','0.0375'],['Buffer 90%','7','93.56','0.0161'],['Buffer 95%','18','0.00','0.2500']])
p('As Table 2 and Figure 3 show, F0 and F1 select the same later slot in this particular instance, so they have identical evaluation results. This does not imply that the methods are equivalent for other instances. The 80% buffer is zero and also leaves the nominal schedule unchanged. The 90% buffer moves charging to the first slot and achieves 93.56% modeled completion, 8.55 percentage points above F0; the day-block interval is 8.20 to 8.91 points. The interval describes this counterfactual model under its sampling assumptions, not a real-world improvement.')
figure('completion.png','Figure 3. Simulated completion rates on 22,083 evaluation records; these are not observed outcomes of deployed schedules.')
p('Figure 4 shows unconditional mean unmet energy. At the 95% level, the 18-minute buffer moves the deadline to minute 12: neither 15-minute slot can finish in time. The resulting zero schedule leaves the entire assumed 0.25 kWh request unmet. This is a genuine consequence of the coarse modeled horizon and strict complete-slot rule, and demonstrates why a larger buffer need not improve service.')
figure('unmet.png','Figure 4. Mean simulated unmet energy, including sessions with zero shortfall.')
p('The earlier 90% schedule also incurs a higher assumed tariff. Mean realized simulated energy cost is 0.1063 arbitrary currency units for F0 and 0.2339 for the 90% buffer. These means reflect energy actually modeled as delivered and do not represent real customer bills. They illustrate the availability and cost trade-off within the chosen assumptions.')
table('Table 3\nQuantum simulation on the selected QUBOs',['Measure','F0','90% buffer'],[['Logical qubits (slack)','4 (2)','4 (2)'],['Exact objective minimum','0.125','0.250'],['Optimal-state probability','23.83%','36.72%'],['Best sampled gap','0.000','0.000'],['Shots; depth p','256; 1','256; 1']])
p('Table 3 separates quantum sampling from session-level service completion. For F0, 86.72% of shots decode to a physically feasible nominal schedule; 23.83% are optimal QUBO states. For the buffer, 92.97% obey its conservative window and 56.64% both obey the window and meet the modeled service target. Different slack assignments and feasible but more expensive schedules explain why the probabilities differ. The nominal transpiled circuit has depth 16 and six CX gates. Uniform random sampling would yield 6.25% optimal and 75% physically feasible nominal states. The quantum comparison uses one seed and a limited evaluation budget, so no general superiority can be inferred.')
figure('qaoa.png','Figure 5. Actual parameterized p = 1 QAOA circuit for the nominal four-variable QUBO. Qubits q0 and q1 encode charging; q2 and q3 encode capacity slack.',6.0)
heading('Limitations')
p('This is a single-EV synthetic decision problem calibrated using real session durations. Its assumed request, charging power, capacity, tariff and nominal deadline are not observed driver inputs. The dataset does not establish what users would have done under another schedule. Site competition, heterogeneous charging rates and realistic grid constraints are absent. The fitted quantile is not a guaranteed service level, and repeated users or chargers may induce dependence across days. The data split is chronological but the analysis remains exploratory. QAOA was simulated on Aer, uses one seed per evaluated formulation and does not include F1. Neither hardware execution, noise resilience, industrial scalability nor quantum advantage is demonstrated.')
heading('Conclusion')
p('In this modeled one-EV problem, a moderate calibration-derived buffer increased simulated completion relative to the nominal schedule while raising simulated energy cost. A more aggressive buffer eliminated all usable full slots. These findings support careful investigation of the interaction between uncertainty margins, slot length and feasibility; they do not establish a deployment effect. Future work should use decision-time declared departures and requests, construct defensible multi-EV site instances, test scenario and buffer QAOA across seeds and depths, and validate on independent data.')
heading('References')
refs=[
'Baek, K., Lee, E., & Kim, J. (2024). A dataset for multi-faceted analysis of electric vehicle charging transactions. Scientific Data, 11, Article 262. https://doi.org/10.1038/s41597-024-02942-9',
'Dalyac, C., Henriet, L., Jeandel, E., Lechner, W., Perdrix, S., Porcheron, M., & Veshchezerova, M. (2021). Qualifying quantum approaches for hard industrial optimization problems: A case study in the field of smart-charging of electric vehicles. EPJ Quantum Technology, 8, Article 12. https://doi.org/10.1140/epjqt/s40507-021-00100-3',
'Farhi, E., Goldstone, J., & Gutmann, S. (2014). A quantum approximate optimization algorithm. arXiv. https://arxiv.org/abs/1411.4028',
'Glover, F., Kochenberger, G., & Du, Y. (2019). A tutorial on formulating and using QUBO models. arXiv. https://doi.org/10.48550/arXiv.1811.11538',
'Sone, S. P., Lehtomäki, J. J., Khan, Z., Umebayashi, K., & Kim, K. S. (2024). Robust EV scheduling in charging stations under uncertain demands and deadlines. IEEE Transactions on Intelligent Transportation Systems, 25(12), 21484–21499. https://doi.org/10.1109/TITS.2024.3466514',
'Wang, Z., Jochem, P., & Fichtner, W. (2020). A scenario-based stochastic optimization model for charging scheduling of electric vehicles under uncertainties of vehicle availability and charging demand. Journal of Cleaner Production, 254, Article 119886. https://doi.org/10.1016/j.jclepro.2019.119886']
for reference in refs:
    q=p(reference,space=6); q.paragraph_format.left_indent=Inches(.25); q.paragraph_format.first_line_indent=Inches(-.25)
d.core_properties.author='Pratham Kapoor; Yashvardhan Wagh; Ayaan Makhani; Vinayak Rastogi'
d.save(OUT/'EV_QUBO_Research_Paper.docx')
print('Created',OUT/'EV_QUBO_Research_Paper.docx')
