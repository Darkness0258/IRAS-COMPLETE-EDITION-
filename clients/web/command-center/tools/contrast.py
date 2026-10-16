#!/usr/bin/env python3
"""
Measures WCAG contrast for the IRAS design tokens in all four looks
(light/dark x cobalt/neon). Text pairs need 4.5:1, UI parts need 3:1.
Glass is composited over the base background first, the way it renders.

    python contrast.py path/to/tokens.css
"""
import re, sys
from pathlib import Path

css = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent.parent / "src/css/tokens.css").read_text()

def block(selector):
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", css, re.S)
    return dict(re.findall(r"--([a-z0-9-]+):\s*([^;]+);", m.group(1))) if m else {}

light, dark = block(":root"), block('[data-theme="dark"]')
neon, neon_dark = block('[data-skin="neon"]'), block('[data-theme="dark"][data-skin="neon"]')
combos = {
    "light/cobalt": {**light},
    "dark/cobalt": {**light, **dark},
    "light/neon": {**light, **neon},
    "dark/neon": {**light, **dark, **neon, **neon_dark},
}

def rgba(s):
    s = s.strip()
    if s.startswith("#"):
        h = s[1:]
        h = h if len(h) == 6 else "".join(c * 2 for c in h)
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [1.0]
    v = [float(x) for x in re.match(r"rgba?\(([^)]+)\)", s).group(1).split(",")]
    return v[:3] + [v[3] if len(v) > 3 else 1.0]

def over(fg, bg):
    a = fg[3]
    return [fg[i] * a + bg[i] * (1 - a) for i in range(3)] + [1.0]

def lum(c):
    f = lambda v: (v / 255) / 12.92 if v / 255 <= 0.03928 else (((v / 255) + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])

def ratio(a, b):
    hi, lo = max(lum(a), lum(b)), min(lum(a), lum(b))
    return (hi + 0.05) / (lo + 0.05)

ROWS = [
    ("text on glass", "text", "glass", 4.5),
    ("muted text on glass", "muted", "glass", 4.5),
    ("accent text and links on glass", "accent", "glass", 4.5),
    ("button text on accent fill", "on-accent", "accent-fill", 4.5),
    ("amber text on its tint", "warn", "glass+warn-soft", 4.5),
    ("red text on its tint", "crit", "glass+crit-soft", 4.5),
    ("button text on amber fill", "on-warn", "warn-fill", 4.5),
    ("button text on red fill", "on-crit", "crit-fill", 4.5),
    ("focus ring and accent icons on page", "accent", "bg", 3.0),
    ("switch and input borders on page", "muted", "bg", 3.0),
]

print(f"{'pair (needs)':46}" + "".join(f"{k:>15}" for k in combos))
ok = True
for label, fg, bgk, need in ROWS:
    line = f"{label + ' (' + str(need) + ')':46}"
    for name, t in combos.items():
        page = rgba(t["bg"])
        if bgk == "glass":
            bg = over(rgba(t["glass"]), page)
        elif bgk.startswith("glass+"):
            bg = over(rgba(t[bgk.split("+")[1]]), over(rgba(t["glass"]), page))
        elif bgk == "bg":
            bg = page
        else:
            bg = rgba(t[bgk])
        f = rgba(t[fg])
        if f[3] < 1:
            f = over(f, bg)
        r = ratio(f, bg)
        bad = r < need
        ok &= not bad
        line += f"{r:>13.2f}{' !' if bad else '  '}"
    print(line)
print("\nALL PASS" if ok else "\nSOME PAIRS ARE BELOW TARGET")
sys.exit(0 if ok else 1)
