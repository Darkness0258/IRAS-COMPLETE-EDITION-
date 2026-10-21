#!/usr/bin/env python3
"""
Builds index.html: one self-contained file with no network requests.

    python build.py                  write ../index.html (the page served at /app/)
    python build.py --check          also fail on missing icons or external URLs
    python build.py --out PATH       write somewhere else

Source layout
    src/index.template.html    page shell
    src/views/*.html           one file per screen
    src/css/*.css              tokens, base, shell, components, one file per screen
    src/js/NN-*.js             modules, concatenated in filename order
    src/assets/                icon sprite, logo mark
    src/fonts/*.woff2          Sora, Instrument Sans, JetBrains Mono (latin, variable)
"""
import base64, re, sys, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

CSS_ORDER = ["tokens", "base", "shell", "components", "home", "chat", "agents", "activity", "memory", "identity", "settings"]
VIEW_ORDER = ["home", "chat", "agents", "activity", "memory", "identity", "settings"]

FONTS = [
    ("Sora", "sora-latin-wght-normal.woff2", "100 800"),
    ("Instrument Sans", "instrument-sans-latin-wght-normal.woff2", "400 700"),
    ("JetBrains Mono", "jetbrains-mono-latin-wght-normal.woff2", "100 800"),
]


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def fonts_css() -> str:
    out = []
    for family, fname, weight in FONTS:
        p = SRC / "fonts" / fname
        if not p.exists():
            print(f"  ! font missing: {fname}")
            continue
        out.append(
            f'@font-face{{font-family:"{family}";font-style:normal;font-weight:{weight};font-display:swap;'
            f'src:url(data:font/woff2;base64,{b64(p)}) format("woff2")}}'
        )
    return "\n".join(out)


def favicon() -> str:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><defs>"
        "<radialGradient id='g' cx='.35' cy='.3' r='.8'><stop offset='0' stop-color='#EAF4FF'/>"
        "<stop offset='.45' stop-color='#5E96FF'/><stop offset='1' stop-color='#1B3FB8'/></radialGradient></defs>"
        "<rect width='64' height='64' rx='16' fill='#04070F'/><circle cx='32' cy='32' r='15' fill='url(#g)'/></svg>"
    )
    return "data:image/svg+xml," + urllib.parse.quote(svg, safe="/:=' <>")


def expand_icons(html: str, known: set, missing: set) -> str:
    def repl(m):
        name, *rest = m.group(1).split()
        if name not in known:
            missing.add(name)
        cls = "i" + (" i-" + rest[0] if rest else "")
        return f'<svg class="{cls}" aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>'
    return re.sub(r"\{\{i:([a-z0-9\- ]+)\}\}", repl, html)


def render():
    """Returns (page_text, problems, stats). Writes nothing."""
    sprite = read(SRC / "assets" / "sprite-symbols.html")
    known = set(re.findall(r'id="i-([a-z0-9-]+)"', sprite))
    missing = set()

    css = "\n".join(read(SRC / "css" / f"{n}.css") for n in CSS_ORDER if (SRC / "css" / f"{n}.css").exists())
    js_files = sorted((SRC / "js").glob("*.js"))
    js = "\n".join(f"/* ---- {f.name} ---- */\n" + read(f) for f in js_files)
    views = "\n".join(read(SRC / "views" / f"{n}.html") for n in VIEW_ORDER if (SRC / "views" / f"{n}.html").exists())

    page = read(SRC / "index.template.html")
    page = page.replace("{{VIEWS}}", views)
    page = expand_icons(page, known, missing)
    page = page.replace("{{FONTS}}", fonts_css())
    page = page.replace("{{CSS}}", css)
    page = page.replace("{{SPRITE}}", sprite)
    page = page.replace("{{MARK}}", "data:image/png;base64," + b64(SRC / "assets" / "mark-144.png"))
    page = page.replace("{{FAVICON}}", favicon())
    # JS last, so a "{{" inside code is never touched by the replacements above
    page = page.replace("{{JS}}", js.replace("</script", "<\\/script"))

    # icons named in JS: icon("x"), icon: "x", ic: "x"
    js_icons = set(re.findall(r'icon\(\s*["\']([a-z0-9-]+)["\']', js)) | set(re.findall(r'\bicon:\s*"([a-z0-9-]+)"', js))
    js_icons |= set(re.findall(r'\bic:\s*"([a-z0-9-]+)"', js))
    for n in sorted(js_icons):
        if n not in known:
            missing.add(n)

    problems = []
    if missing:
        problems.append("missing icons: " + ", ".join(sorted(missing)))
    # no network requests: no remote URLs except XML namespaces
    urls = [u for u in re.findall(r"https?://[^\s\"'<>)]+", page) if "www.w3.org" not in u]
    urls = [u for u in urls if not u.startswith(("http://localhost", "http://127.0.0.1"))]
    # placeholder text in the Settings form, never fetched
    urls = [u for u in urls if u.rstrip(".,") != "https://iras-cloud.onrender.com"]
    if urls:
        problems.append("external URLs: " + ", ".join(sorted(set(urls))[:8]))
    if "cdn." in page.lower():
        problems.append('the text "cdn." appears in the page')
    return page, problems, {"js": len(js_files), "css": len(CSS_ORDER), "icons": len(known)}


def main(argv):
    out = ROOT.parent / "index.html"
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1]).resolve()
    page, problems, st = render()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"built {out}  {out.stat().st_size / 1024:,.0f} KB  ({st['js']} js, {st['css']} css, {st['icons']} icons)")
    for p in problems:
        print("  !", p)
    if "--check" in argv and problems:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
