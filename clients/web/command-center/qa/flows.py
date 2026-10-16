import pathlib, json, time, sys
from playwright.sync_api import sync_playwright

DIST = (pathlib.Path(__file__).resolve().parent.parent / 'index.html')
(pathlib.Path(__file__).resolve().parent / 'shots').mkdir(exist_ok=True)
RESULTS = []
def check(name, cond, extra=''):
    RESULTS.append((name, bool(cond), extra))
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{extra}]' if extra and not cond else ''))

def wait_idle(pg, timeout=40000):
    pg.wait_for_function("() => IRAS.S.ui === 'idle' && !IRAS.sim.running", timeout=timeout)

def seq(pg):
    return pg.evaluate("() => window.__ui.slice()")

with sync_playwright() as p:
    b = p.chromium.launch(args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--autoplay-policy=no-user-gesture-required'])
    ctx = b.new_context(viewport={'width':1440,'height':900}, permissions=['microphone','camera'])
    pg = ctx.new_page()
    errs=[]; reqs=[]
    pg.on('console', lambda m: errs.append(f'{m.type}: {m.text}') if m.type in ('error',) else None)
    pg.on('pageerror', lambda e: errs.append('PAGEERROR: '+str(e)))
    pg.on('request', lambda r: reqs.append(r.url) if not r.url.startswith(('file:','data:','blob:')) else None)
    pg.add_init_script("localStorage.setItem('iras-cc-settings', JSON.stringify({theme:'dark',skin:'cobalt',perf:'full',realMic:false}))")
    pg.goto(f'file://{DIST}#/home'); pg.wait_for_timeout(800)
    pg.evaluate("""() => { window.__ui = []; window.__inv = []; IRAS.bus.on('ui', e => window.__ui.push(e.to)); IRAS.bus.on('invalid_transition', e => window.__inv.push(e.from+'>'+e.to)); }""")

    # ---- 1. spotify via prompt chip (screen control)
    pg.click('.prompt:has-text("Spotify")')
    pg.wait_for_function("() => IRAS.S.ui === 'acting'", timeout=8000)
    check('peek card visible while acting', pg.is_visible('#screenPeek'))
    check('pipeline Act active', pg.evaluate("() => document.querySelector('.step[data-step=act]').classList.contains('is-active')"))
    pg.screenshot(path=str(pathlib.Path(__file__).resolve().parent / 'shots') + '/flow-acting.png')
    wait_idle(pg)
    s = seq(pg)
    check('spotify: thinking -> acting -> idle', s[:3] == ['thinking','acting','thinking'] and s[-1]=='idle', str(s))
    check('chat got a reply', 'Calm Piano' in pg.evaluate("() => document.querySelector('#thread').innerText"))

    # ---- 2. emails typed
    pg.evaluate("window.__ui.length=0")
    pg.fill('[data-composer=home] .msg', 'Summarize my unread emails')
    pg.keyboard.press('Enter')
    wait_idle(pg)
    s = seq(pg)
    check('emails typed: thinking -> idle (no speaking)', s == ['thinking','idle'], str(s))
    check('emails reply has list', pg.evaluate("() => document.querySelectorAll('#thread .msg.assistant ol li').length") >= 3)

    # ---- 3. install: system approval, approve
    pg.evaluate("window.__ui.length=0")
    pg.click('.prompt:has-text("Install VS Code")')
    pg.wait_for_selector('#approvalDlg[open]', timeout=8000)
    check('install: dialog level system', pg.get_attribute('#approvalDlg','data-level') == 'system')
    check('body authority = system', pg.evaluate("() => document.body.dataset.authority") == 'system')
    check('only dialog blurs (modal)', pg.evaluate("() => document.body.dataset.modal") == '1')
    check('focus starts on Deny', pg.evaluate("() => document.activeElement.id") == 'apDeny')
    pg.click('#apApprove')
    wait_idle(pg)
    s = seq(pg)
    check('install approve path', 'approval' in s and 'acting' in s and s[-1]=='idle', str(s))
    check('modal flag cleared', pg.evaluate("() => document.body.dataset.modal") is None)

    # ---- 4. delete: critical, Escape = deny
    pg.evaluate("window.__ui.length=0")
    pg.click('.prompt:has-text("Delete old build")')
    pg.wait_for_selector('#approvalDlg[open]', timeout=8000)
    check('delete: dialog level critical', pg.get_attribute('#approvalDlg','data-level') == 'critical')
    check('voice phrase shown', pg.is_visible('#apPhrase') and 'Approve delete' in pg.inner_text('#apPhrase'))
    pg.screenshot(path=str(pathlib.Path(__file__).resolve().parent / 'shots') + '/flow-critical.png')
    pg.keyboard.press('Escape')
    pg.wait_for_function("() => !document.querySelector('#approvalDlg').open", timeout=3000)
    wait_idle(pg)
    s = seq(pg)
    check('critical deny ends idle without acting', 'acting' not in s and s[-1]=='idle', str(s))
    audit_state = pg.evaluate("() => IRAS.audit.items.find(i=>i.kind==='approval' && i.id.startsWith('ap_ap')) && IRAS.audit.items.find(i=>i.kind==='approval' && i.id.startsWith('ap_ap')).status")
    check('audit shows denied', audit_state == 'denied', str(audit_state))

    # ---- 5. delete: let it expire (9s)
    pg.evaluate("window.__ui.length=0")
    pg.click('.prompt:has-text("Delete old build")')
    pg.wait_for_selector('#approvalDlg[open]', timeout=8000)
    t0 = time.time()
    pg.wait_for_function("() => !document.querySelector('#approvalDlg').open", timeout=14000)
    dt = time.time()-t0
    check('critical expires after about 9s', 8 <= dt <= 11, f'{dt:.1f}s')
    wait_idle(pg)
    check('expired reply mentions time ran out', 'Time ran out' in pg.evaluate("() => document.querySelector('#thread').innerText"))

    # ---- 6. delete: approve
    pg.evaluate("window.__ui.length=0")
    pg.click('.prompt:has-text("Delete old build")')
    pg.wait_for_selector('#approvalDlg[open]', timeout=8000)
    pg.click('#apApprove')
    pg.wait_for_function("() => IRAS.S.ui === 'acting'", timeout=6000)
    peek = pg.inner_text('#peekApp')
    check('files layout peek app', 'File Explorer' in peek, peek)
    wait_idle(pg)
    check('critical approve completes', 'Deleted 3 folders' in pg.evaluate("() => document.querySelector('#actList') ? IRAS.audit.items.map(i=>i.title).join('|') : ''"))

    # ---- 7. stop (Escape) mid-run
    pg.evaluate("window.__ui.length=0")
    pg.click('.prompt:has-text("Spotify")')
    pg.wait_for_function("() => IRAS.S.ui === 'acting'", timeout=8000)
    pg.keyboard.press('Escape')
    pg.wait_for_function("() => IRAS.S.ui === 'idle'", timeout=3000)
    pg.wait_for_timeout(1500)
    check('stop ends idle and stays idle', pg.evaluate("() => IRAS.S.ui") == 'idle' and not pg.evaluate("() => IRAS.sim.running"))
    check('stop button hidden when idle', not pg.is_visible('#stopBtn'))

    # ---- 8. code agent -> Agents view
    pg.fill('[data-composer=home] .msg', '/code fix the failing test')
    pg.keyboard.press('Enter')
    pg.wait_for_function("() => IRAS.S.ui === 'acting'", timeout=6000)
    pg.wait_for_timeout(4200)
    pg.evaluate("IRAS.go('agents')"); pg.wait_for_timeout(300)
    running = pg.evaluate("() => document.querySelectorAll('#runList .stp[data-status=running]').length")
    check('agents view shows a running step mid-run', running >= 1, str(running))
    pg.evaluate("IRAS.go('home')")
    wait_idle(pg)
    pg.evaluate("IRAS.go('agents')"); pg.wait_for_timeout(300)
    done_steps = pg.evaluate("() => document.querySelectorAll('#runList .run:first-child .stp[data-status=done], #runList .run:first-child .stp[data-status=failed]').length")
    check('code agent finished all 6 steps', done_steps == 6, str(done_steps))

    # ---- 9. voice via Space (sim levels, realMic off)
    pg.evaluate("IRAS.go('home')"); pg.wait_for_timeout(200)
    pg.evaluate("window.__ui.length=0")
    pg.mouse.click(700, 300)   # click empty area so focus is on body
    pg.keyboard.press('Space')
    pg.wait_for_function("() => IRAS.S.ui === 'listening'", timeout=2000)
    pg.wait_for_timeout(1200)
    check('listening shows heard card text', len(pg.inner_text('#heardText')) > 3)
    wait_idle(pg)
    s = seq(pg)
    check('voice flow speaks', 'listening' in s and 'thinking' in s and 'speaking' in s and s[-1]=='idle', str(s))

    # ---- 10. palette + settings
    pg.keyboard.press('Control+k')
    pg.wait_for_selector('#paletteDlg[open]')
    pg.fill('#palInput', 'light theme')
    pg.keyboard.press('Enter')
    pg.wait_for_timeout(400)
    check('palette switches to light', pg.evaluate("() => document.documentElement.dataset.theme") == 'light')
    pg.evaluate("IRAS.setSetting('skin','neon')"); pg.wait_for_timeout(200)
    check('skin neon', pg.evaluate("() => document.documentElement.dataset.skin") == 'neon')
    pg.evaluate("IRAS.setSetting('perf','lite')"); pg.wait_for_timeout(200)
    blur = pg.evaluate("() => getComputedStyle(document.querySelector('#livePanel')).backdropFilter")
    check('performance mode removes blur', blur in ('none',''), blur)
    pg.evaluate("IRAS.setSetting('perf','full'); IRAS.setSetting('theme','dark'); IRAS.setSetting('skin','cobalt')")

    # ---- 11. blur layer budget on Home
    n = pg.evaluate("""() => [...document.querySelectorAll('body *')].filter(e => { const s = getComputedStyle(e); const d = s.display !== 'none' && e.getBoundingClientRect().width>0; return d && ((s.backdropFilter && s.backdropFilter !== 'none') || (s.webkitBackdropFilter && s.webkitBackdropFilter !== 'none')); }).length""")
    check('3 or fewer blurred layers on Home', n <= 3, str(n))

    check('no invalid state transitions', pg.evaluate("() => window.__inv.length") == 0, str(pg.evaluate("() => window.__inv")))
    check('no network requests', len(reqs) == 0, str(reqs[:5]))
    check('no console errors', len(errs) == 0, str(errs[:5]))
    b.close()

fails = [r for r in RESULTS if not r[1]]
print(f'\n{len(RESULTS)-len(fails)}/{len(RESULTS)} passed')
sys.exit(1 if fails else 0)
