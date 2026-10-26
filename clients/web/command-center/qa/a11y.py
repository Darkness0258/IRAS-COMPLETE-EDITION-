import pathlib, json, sys
from playwright.sync_api import sync_playwright
DIST = (pathlib.Path(__file__).resolve().parent.parent / 'index.html')
_axe = [p for p in [pathlib.Path(__file__).resolve().parent / 'node_modules/axe-core/axe.min.js', pathlib.Path('/home/claude/cc/build/node_modules/axe-core/axe.min.js')] if p.exists()]
if not _axe:
    raise SystemExit('axe-core not found. Run:  npm i axe-core   (in the qa folder)')
AXE = _axe[0].read_text()
views=['home','chat','agents','activity','memory','identity','pc','settings']
total=0
with sync_playwright() as p:
    b=p.chromium.launch()
    for theme in ('dark','light'):
        for skin in ('cobalt','neon'):
            ctx=b.new_context(viewport={'width':1440,'height':900}, color_scheme=theme)
            pg=ctx.new_page()
            pg.add_init_script(f"localStorage.setItem('iras-cc-settings', JSON.stringify({{theme:'{theme}',skin:'{skin}',perf:'lite'}}))")
            for v in views:
                pg.goto(f'file://{DIST}#/{v}'); pg.wait_for_timeout(700)
                pg.evaluate("document.querySelectorAll('.is-entering').forEach(e=>e.classList.remove('is-entering'))")
                pg.add_script_tag(content=AXE)
                res=pg.evaluate("""async () => { const r = await axe.run(document, {runOnly:{type:'tag', values:['wcag2a','wcag2aa','wcag21aa','wcag22aa','best-practice']}, resultTypes:['violations']}); return r.violations.map(v=>({id:v.id, impact:v.impact, n:v.nodes.length, help:v.help, sample:v.nodes.slice(0,3).map(n=>n.target.join(' ')+' :: '+(n.failureSummary||'').split('\\n').slice(0,3).join(' | '))})); }""")
                for r in res:
                    total+=1
                    print(f'[{theme}/{skin}/{v}] {r["impact"]} {r["id"]} x{r["n"]}: {r["help"]}')
                    for s in r['sample'][:2]: print('     ', s[:230])
            ctx.close()
    b.close()
print('violation groups:', total)
