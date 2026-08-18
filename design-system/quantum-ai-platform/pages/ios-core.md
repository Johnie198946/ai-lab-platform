# Quantum iOS Core Override

This native override takes precedence over the generated web-oriented Master file.

## Product direction

- Product: enterprise AI agent productivity workspace.
- Tone: calm, premium, trustworthy, content-first; Swiss/AI-native minimalism.
- Primary platform: SwiftUI on iOS 17+.
- Preserve the official Quantum cyan → blue → violet brand spectrum. Pink is not used as a structural CTA color.
- The supplied transparent Quantum mark is the visual focal point. Never place it inside a second decorative circle or add glow behind it.
- Use the full gradient only for the brand mark and rare moments of emphasis. Primary controls use a stable single blue.
- Support light and dark appearance equally; dark mode uses graphite surfaces, never pure black.

## Native tokens

| Role | Light | Dark |
|---|---|---|
| Background | `#F6F7FB` | `#0D0F14` |
| Card | `#FFFFFF` | `#151821` |
| Elevated surface | `#FFFFFF` | `#1C202A` |
| Primary text | `#172033` | `#F4F6FC` |
| Secondary text | `#526079` | `#B4BECE` |
| Border | `#DDE3EE` | `#303541` |
| Brand blue | `#5B7CEE` | `#5B7CEE` |

## Interaction rules

- Use native `NavigationStack`, `TabView`, `Menu`, sheets and alerts.
- Every interactive target is at least 44×44pt and has an accessibility label when icon-only.
- Prefer Dynamic Type roles over fixed point sizes for core navigation, forms and message composition.
- Keep one clear primary action per region. Secondary actions use neutral surfaces.
- Prefer whitespace, typography and hairline dividers over nested cards, glow and decorative capsules.
- Use 180–240ms ease-out transitions and short damped springs. Respect Reduce Motion.
- Never hide task progress: operations over 300ms show explicit status, and messages submitted during generation are labeled as queued.

## Layout rules

- 16pt phone gutters, 8pt spacing rhythm, 720pt maximum readable message width.
- Composer and tab bar respect bottom safe areas; scroll content must remain visible above them.
- Quick commands belong to the conversation empty state as a short vertical list; the composer remains a single quiet surface.
- Final Drill-me confirmation renders the requirement table and decision controls in the same message surface.
