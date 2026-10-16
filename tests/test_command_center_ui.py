"""Checks for the IRAS Command Center (clients/web/command-center).

Same style as the other UI tests: read the files and look for the things that must
stay true. The browser tests live in clients/web/command-center/qa/.
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "clients" / "web" / "command-center"


def read(*parts):
    return CC.joinpath(*parts).read_text(encoding="utf-8")


def all_js():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted((CC / "src" / "js").glob("*.js")))


def all_css():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted((CC / "src" / "css").glob("*.css")))


def test_command_center_is_one_offline_file():
    text = read("index.html")
    assert "cdn." not in text.lower()
    assert "<script src" not in text
    assert 'rel="stylesheet"' not in text
    remote = [u for u in re.findall(r"https?://[^\s\"'<>)]+", text) if "www.w3.org" not in u]
    remote = [u for u in remote if not u.startswith(("http://localhost", "http://127.0.0.1"))]
    remote = [u for u in remote if u.rstrip(".,") != "https://iras-cloud.onrender.com"]  # placeholder text only
    assert remote == []
    assert len(text) < 1_500_000


def test_built_file_matches_the_sources():
    spec = importlib.util.spec_from_file_location("cc_build", CC / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    page, problems, _ = mod.render()
    assert problems == []
    assert page == read("index.html"), "index.html is stale. Run: python build.py"


def test_design_tokens_cover_both_skins_and_both_themes():
    tokens = read("src", "css", "tokens.css")
    for marker in (
        "--bg: #EEF3FB", "--bg: #04070F",                       # light and dark background
        "--accent: #1D4ED8", "--accent: #4C8DFF",                # cobalt
        '[data-skin="neon"]', "--accent: #2DFF9A", "--accent: #006B3C",  # neon, deep green for light text
        "--warn: #FFB020", "--crit: #FF5C74",                    # authority, dark values from the plan
        "--on-accent: #03120A",                                  # dark text on neon fills
        '[data-theme="dark"]',
    ):
        assert marker in tokens, marker


def test_glass_recipe_and_blur_budget():
    css = all_css()
    for marker in ("blur(var(--blur)) saturate(var(--sat))", "--blur: 24px", "--sat: 160%", "inset 0 1px 0 var(--highlight)"):
        assert marker in css, marker
    assert "@supports not" in css                       # solid fallback without backdrop-filter
    assert 'body[data-modal] .glass:not(.modal-glass)' in css   # only the dialog blurs while one is open


def test_orb_has_six_states_and_three_quality_levels():
    orb = read("src", "js", "10-orb.js")
    for state in ("idle", "listening", "thinking", "speaking", "acting", "approval"):
        assert state in orb
    for marker in ('"full"', '"lite"', '"still"', "createConicGradient", "IRAS.approvalFrac", "S.level.mic", "S.level.tts"):
        assert marker in orb, marker
    assert "visibilitychange" in all_js()               # loops stop in a hidden window


def test_state_machine_blocks_impossible_moves():
    core = read("src", "js", "00-core.js")
    assert "blocked impossible transition" in core
    allowed = dict(re.findall(r"(\w+):\s*\[([^\]]*)\]", core[core.index("const ALLOWED"):core.index("const fsm")]))
    assert "speaking" not in allowed["listening"] and "acting" not in allowed["listening"]
    assert "listening" in allowed["speaking"]            # barge-in goes through listening, never both at once
    assert "approval" in allowed["acting"] and "acting" in allowed["approval"]


def test_approval_rules_esc_denies_and_critical_is_nine_seconds():
    approval = read("src", "js", "45-approval.js")
    assert 'dlg.addEventListener("cancel"' in approval and 'resolve("deny", "escape")' in approval
    sim = read("src", "js", "30-sim.js")
    assert re.search(r'authority: "critical"[^}]*expires_ms: 9000', sim, re.S) or "expires_ms: 9000" in sim
    html = read("src", "index.template.html")
    assert html.index('id="apDeny"') < html.index('id="apApprove"')   # focus lands on Deny first


def test_amber_and_red_are_reserved_for_authority():
    js = all_js()
    # tokens exist for both levels and the badge text always carries a word, not only colour
    assert '"System action"' in js and '"Critical"' in js
    skins = read("src", "css", "tokens.css")
    for token in ("--accent", "--accent-fill", "--glow", "--orb-mid"):
        block = re.findall(r"%s:\s*([^;]+);" % re.escape(token), skins)
        assert all(not v.strip().upper().startswith(("#FFB020", "#FF5C74", "#D97706", "#E11D48")) for v in block)


def test_motion_rules_reduced_motion_performance_mode_and_no_layout_animation():
    css = all_css()
    assert "prefers-reduced-motion" in css and '[data-motion="reduce"]' in css
    assert '[data-perf="lite"] .glass' in css and "backdrop-filter: none" in css
    assert 'html[data-hidden="1"]' in css
    for frames in re.findall(r"@keyframes\s+\w+\s*\{((?:[^{}]|\{[^{}]*\})*)\}", css):
        assert not re.search(r"\b(width|height|top|left|right|bottom|margin|padding|max-height)\s*:", frames)
    js = all_js()
    assert "IRAS.onSlow" in js and "autoLite" in js     # Auto switches to Performance mode by itself


def test_live_source_uses_the_endpoints_that_exist():
    live = read("src", "js", "35-live.js")
    for marker in ("/health", "/v1/providers/status", "/v1/chat/stream", "text/event-stream", "iras-api-token", "authorization_required"):
        assert marker in live, marker
    assert 'store.sset("iras-api-token"' in read("src", "js", "80-settings.js")   # the token is kept for this tab only
    assert 'store.set("iras-api-token"' not in all_js()                         # and is never written to localStorage


def test_accessibility_markers():
    html = read("index.html")
    for marker in ('class="skip-link"', 'aria-live="polite"', "<dialog", 'aria-labelledby="apTitle"', 'role="log"', ":focus-visible", "aria-current"):
        assert marker in html, marker
    assert "ap-voice" in html and "ap-timer" in html


def test_design_documents_exist_and_describe_the_rules():
    design = read("DESIGN.md")
    assert design.startswith("---") and "name: IRAS Cobalt and Neon" in design
    assert "Amber and red are only for authority" in design
    events = read("EVENTS.md")
    for ev in ("approval_request", "audio_level", "agent_step", "tool_start", "GET /v1/events"):
        assert ev in events, ev


def test_contrast_tool_passes_for_all_four_looks():
    run = subprocess.run([sys.executable, str(CC / "tools" / "contrast.py")], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "ALL PASS" in run.stdout
