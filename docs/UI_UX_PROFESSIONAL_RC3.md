# IRAS RC3 Professional UI/UX & Motion System

This pass introduces one consistent product language across the IRAS Web/PWA, Windows desktop shell, and Android companion without changing the existing cloud/device security model.

## Design principles

- **Functional motion first.** Motion communicates hierarchy, loading, focus, and state changes rather than decorating every surface.
- **Short, natural transitions.** Small controls react quickly; larger containers use slightly longer easing. Continuous ambient motion is intentionally subtle.
- **Adaptive navigation.** Desktop uses a persistent navigation rail/sidebar, while compact layouts collapse to horizontal navigation and a simplified composer.
- **Strong hierarchy.** Primary actions, system state, chat, and secondary administrative tools are visually separated.
- **Accessible by default.** Web honors `prefers-reduced-motion`; Android uses standard tap targets and content descriptions; desktop retains keyboard focus and direct shortcuts.
- **Immediate feedback.** Chat messages animate in, status changes are color-coded, controls acknowledge press/hover states, and loading/working states remain visible.

## Visual language

IRAS uses an Obsidian-style dark workspace with cool indigo/cyan accents, restrained glass surfaces, low-noise borders, semantic success/warning/error colors, and typography optimized for dense technical work.

### Web/PWA

- Persistent desktop navigation rail with responsive compact navigation.
- Command Center header and system-health presence indicator.
- Welcome state with fast-start prompt chips.
- Refined message hierarchy, timestamps, streaming cursor, glass composer, and animated dialogs/cards.
- Responsive layout for desktop, tablet, and phone.
- Reduced-motion fallback for all nonessential motion.

### Windows desktop

- New command-center layout with navigation rail, health state, structured chat bubbles, modern composer, and custom approval dialog.
- Fade-in, status pulse, hover/press feedback, and consistent message hierarchy.
- Keyboard focus shortcut (`Ctrl+L`) preserved.

### Android

- Dark tonal surface hierarchy inspired by modern Material 3 patterns.
- Responsive system-bar inset handling for modern Android edge-to-edge behavior.
- Structured IRAS/user message groups with animated entry.
- Polished composer, cloud-state card, accessible content descriptions, and press micro-interactions.

## Motion/accessibility references reviewed

- Microsoft Fluent 2 Motion: https://fluent2.microsoft.design/motion
- Android Material 3 design system: https://developer.android.com/develop/ui/compose/designsystems/material3
- Android layout/navigation patterns: https://developer.android.com/design/ui/mobile/guides/layout-and-content/layout-and-nav-patterns
- Android window insets: https://developer.android.com/develop/ui/compose/system/insets
- Apple Human Interface Guidelines / loading and responsive interaction guidance: https://developer.apple.com/design/
- WCAG 2.1 animation-from-interactions guidance: https://www.w3.org/WAI/standards-guidelines/wcag/new-in-21/

## Non-goals

This release does not add a new backend capability, change Remote protocol `1`, modify protected authorization boundaries, or introduce external UI frameworks/CDNs. The UI remains self-contained and deployable with the existing RC3 build.
