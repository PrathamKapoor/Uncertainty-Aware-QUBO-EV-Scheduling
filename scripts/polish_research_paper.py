"""Polish the revised paper without changing its research limitations."""
from pathlib import Path
from docx import Document

source=Path('docs/final/EV_QUBO_Research_Paper_Revised.docx')
target=Path('docs/final/EV_QUBO_Research_Paper_Polished.docx')
d=Document(source)
def find(prefix):
    return next(p for p in d.paragraphs if p.text.startswith(prefix))
def settext(p, value):
    p.runs[0].text=value
    for r in p.runs[1:]: r.text=''

p=find('The contribution is a comparative, exploratory')
settext(p,'The contribution is an exploratory comparison of calibration, baseline selection, tie-breaking and quantum sampling under a shared scheduling formulation. A method can appear better than a nominal optimizer when a simple alternative baseline has been omitted or when multiple nominal optima are resolved differently. The underlying charging transactions are real, while the requests, tariffs and scheduling actions evaluated here are simulated. The public-data experiment uses one EV; it cannot establish the performance of a fleet controller.')

p=find('Site loading Lₜ')
first, second=p.text.split('For this experiment,',1)
settext(p,first.strip())
p.paragraph_format.keep_together=True
new=d.add_paragraph('For this experiment,'+second,style=p.style)
p._p.addnext(new._p)
new.paragraph_format.keep_together=True
new.alignment=p.alignment

explain=find('Figure 4 shows unconditional mean unmet energy.')
explain.paragraph_format.keep_with_next=True
table_explanation=find('Table 4 reports physical outcomes')
settext(table_explanation,'In the two-slot representation, 10 indicates charging in the first slot, whereas 01 indicates charging in the second slot. These are charging-decision bits, not complete QUBO bitstrings, which also include capacity slack. '+table_explanation.text)

references=find('References')
references.paragraph_format.page_break_before=True
d.save(target)
print(target)
