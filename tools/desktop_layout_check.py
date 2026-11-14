"""Check the actual Tk window at normal and minimum supported sizes."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.console import Console

c=Console();results=[]
def children(w):
    for x in w.winfo_children():
        yield x
        yield from children(x)
try:
    for width,height in [(1320,860),(1050,700)]:
        c.root.geometry(f'{width}x{height}');c.root.update()
        buttons=[w for w in children(c.root) if w.winfo_class()=='TButton']
        outside=[w.cget('text') for w in buttons if w.winfo_rootx()+w.winfo_width()>c.root.winfo_rootx()+c.root.winfo_width()+1]
        assert not outside,(width,outside)
        assert any(w.winfo_class()=='TScrollbar' for w in children(c.root))
        results.append({'size':[width,height],'horizontal_overflow':outside,'scrollable_status_panel':True,'buttons':len(buttons)})
    Path('reports/desktop-layout-check.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False))
finally:
    c.closing=True;c.root.destroy()
