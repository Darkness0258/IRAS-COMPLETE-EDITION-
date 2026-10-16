---
name: IRAS Cobalt and Neon
colors:
  background: '#04070f'
  surface: '#04070f'
  surface-container: '#0b1224'
  surface-bright: '#121a30'
  on-surface: '#eaf1ff'
  on-surface-variant: '#9aa9c7'
  outline: '#272a31'
  outline-variant: '#1a1f2b'
  primary: '#4c8dff'
  on-primary: '#04070f'
  primary-container: '#1b3fb8'
  on-primary-container: '#eaf4ff'
  tertiary: '#ffb020'
  on-tertiary: '#1a1200'
  error: '#ff5c74'
  on-error: '#25030b'
typography:
  display:
    fontFamily: Sora
    fontSize: 49px
    fontWeight: '300'
    lineHeight: 52px
  headline-lg:
    fontFamily: Sora
    fontSize: 31px
    fontWeight: '600'
    lineHeight: 36px
  headline-md:
    fontFamily: Sora
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Instrument Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Instrument Sans
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
  code:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 21px
rounded:
  xs: 0.5rem
  sm: 0.75rem
  DEFAULT: 1rem
  lg: 1.25rem
  xl: 1.75rem
  full: 9999px
spacing:
  base: 4px
  gutter: 1.5rem
---

# IRAS design system: Cobalt and Neon

This file is the plan's **UI-1: lock the design system**.
The source of truth in code is `src/css/tokens.css`. This page explains it, and the
front matter above is the dark Cobalt look in Google Stitch format, so Stitch can use it.

## The idea

IRAS should feel alive. It reacts to your voice and to what its agents are doing, live.
The **orb** is the one memorable thing: it shows the state, and everything else stays quiet.

Four rules hold the system together:

1. **One accent per skin.** Cobalt is blue and black (the default). Neon is green and black. Never both.
2. **Amber and red are only for authority.** Amber means SYSTEM_ACTION, red means CRITICAL. Nothing else uses them, so the screen shows the same rule as the backend: being able to is not the same as being allowed to.
3. **Colour is never alone.** Every level has an icon and a word.
4. **The screen shows state, it never guesses.** Every change arrives as an event. See `EVENTS.md`.

## Looks

Two skins, each in dark and light. **Auto** follows the device. You can override it.

| Role | Dark | Light |
|---|---|---|
| Background | `#04070F` | `#EEF3FB` |
| Glass fill | white 7% | white 62% |
| Glass edge | white 14% | white 85%, plus 1px `#0A1226` at 8% |
| Text | `#EAF1FF` | `#0A1226` |
| Muted text | `#9AA9C7` | `#4A5877` |
| Cobalt accent (text, icons) | `#4C8DFF` | `#1D4ED8` |
| Cobalt fill (buttons) | `#4C8DFF` with `#04070F` text | `#1D4ED8` with white text |
| Neon accent (text, icons) | `#2DFF9A` | `#006B3C` (deep green) |
| Neon fill (buttons, glow) | `#2DFF9A` with `#03120A` text | `#2DFF9A` with `#03120A` text |
| SYSTEM_ACTION text, icons | `#FFB020` | `#92400E` |
| SYSTEM_ACTION fill, ring, orb | `#FFB020` with `#1A1200` text | `#D97706` with `#1A0F00` text |
| CRITICAL text, icons | `#FF5C74` | `#B3122F` |
| CRITICAL fill, ring, orb | `#FF5C74` with `#25030B` text | `#E11D48` with white text |

Neon fails on a light background (1.27 to 1). In light mode neon is only a fill or a glow
with dark text on it, and green text and icons use the deep green.

### Two light-mode values changed from the plan

The plan listed light amber `#B45309` and light red `#C81E3A` as text colours. On the tinted
badge backgrounds they sit on, they measured **3.76** and **4.24**, under the 4.5 needed.
The text colours are now `#92400E` and `#B3122F` (5.9 and 5.7). Brighter amber and red are kept
for fills, rings and the orb, with dark or white text on top. Dark mode and every other value follow the plan.

## Measured contrast

Measured with `tools/contrast.py` on the glass surface (glass over the base background).
Text needs 4.5, parts of the interface need 3.

| Pair (needs) | light/cobalt | dark/cobalt | light/neon | dark/neon |
|---|---|---|---|---|
| text on glass (4.5) | 17.89 | 15.60 | 17.89 | 15.60 |
| muted text on glass (4.5) | 6.83 | 7.47 | 6.83 | 7.47 |
| accent text and links on glass (4.5) | 6.44 | 5.53 | 6.36 | 13.38 |
| button text on accent fill (4.5) | 6.70 | 6.29 | 14.51 | 14.51 |
| amber text on its tint (4.5) | 5.88 | 7.35 | 5.88 | 7.35 |
| red text on its tint (4.5) | 5.67 | 4.95 | 5.67 | 4.95 |
| button text on amber fill (4.5) | 5.93 | 10.16 | 5.93 | 10.16 |
| button text on red fill (4.5) | 4.70 | 6.42 | 4.70 | 6.42 |
| focus ring and accent icons on page (3) | 6.02 | 6.29 | 5.95 | 15.24 |
| switch and input borders on page (3) | 6.38 | 8.51 | 6.38 | 8.51 |

An automated axe-core scan of all seven screens in all four looks found **0 violations**.

## Glass

Glass needs something behind it, so the background is a slow nebula: three soft blobs that
only move with `transform`, over a faint grid.

```css
.glass {
  background: var(--glass);
  border: 1px solid var(--edge);
  border-radius: 20px;
  backdrop-filter: blur(24px) saturate(160%);
  box-shadow: inset 0 1px 0 var(--highlight);   /* the faint top highlight */
}
```

- Blur 24px, saturate 160%. The 1px edge is what makes it read as glass.
- **At most 3 blurred layers on screen.** On Home they are Live activity, the command bar, and (on phones) the bottom bar. When a dialog opens, only the dialog blurs.
- Never animate the blur radius.
- Without `backdrop-filter`, a solid translucent panel is used instead.

## Type

| Use | Font | Notes |
|---|---|---|
| State name, titles, numbers | **Sora** | Wide and geometric, like the IRAS wordmark. The state name is weight 300. |
| Interface text | **Instrument Sans** | Quiet and readable at 14 to 16px. |
| Code, ids, JSON | **JetBrains Mono** | Only where it really is code. |

All three are embedded in the file (Latin, variable weight, SIL Open Font License), so
there is no network request. Scale ratio 1.25: 12, 13, 14, 15, 16, 18, 20, 25, 31, 39, 49.
Body text is 16px. Sentence case everywhere. No all-caps labels.

## Shape and space

4px base. Radius follows hierarchy, so the surface is softer than what sits on it:
panels 20 to 28, rows and cards 12 to 16, chips and badges full.

## Motion

Only `transform` and `opacity` move. Nothing moves layout.

| Kind | Time |
|---|---|
| Micro (hover, press) | 140ms |
| Panels and dialogs | 280ms, `cubic-bezier(.2, 0, 0, 1)` |
| Exits | 200ms (about 30% faster) |
| Ambient loops | 4s breathing. Background drift is 58s or longer. |
| List stagger | 40ms per row |

Loops pause when the window is hidden.

### The orb

| State | What it does | Driven by |
|---|---|---|
| Idle | Slow breathing glow, 4s loop | Timer |
| Listening | Rings grow with your voice, live dot | Mic level |
| Thinking | Orbiting light. Tokens appear as they stream | LLM stream |
| Speaking | Radial waveform follows IRAS's voice | TTS level |
| Acting | Scan sweep and ticks. A picture of the screen area it controls shows a highlight box and a cursor | Computer-use events |
| Approval | Amber or red pulse with a 9 second countdown ring | Approval request |

It is drawn on a 2D canvas, so it runs on weak laptops. Three quality levels:

- **Full**: 60fps, dust, trails.
- **Performance**: 20fps, no blur, no dust, no trails, no loops. Auto switches to it if frames stay slow. You can force it.
- **Still** (reduced motion): time is frozen and it redraws only when something changes. State shows with colour and words. The countdown ring still updates, because time left is information.

## The approval gate

Between Understand and Act on Home there is a lock. It is dashed when nothing is waiting and
lights up in amber or red when IRAS needs you.

| Level | Colour | Icon | Word | How you answer |
|---|---|---|---|---|
| Safe | none | check | Safe | Nothing. IRAS logs it. |
| SYSTEM_ACTION | amber | shield | System action | Tap Approve or Deny. 30 second window. |
| CRITICAL | red | shield with alert | Critical | Say the phrase out loud, or tap. 9 second window. |

Esc always means deny. The dialog focuses Deny first, so Enter can never approve by accident.
When time runs out, nothing runs.

## Accessibility

- Visible 2px focus ring on every control. Skip link. Landmarks.
- Every icon-only button has a name. State changes are announced politely.
- Dialogs are native `<dialog>`, so focus is trapped and Esc works.
- Touch targets are 44px or more on touch screens.
- The memory map has a plain list version for keyboards and screen readers.
- Reduced motion follows the device, with an override in Settings.
- Windows high contrast mode falls back to system colours.

## Voice of the interface

Plain words. Short. Say what IRAS did or needs, not how it works.
"Needs your approval", not "Authorization required". "Done in 0.9 s", not "Execution complete".
Roman Urdu is supported in replies and in the default speech language.
