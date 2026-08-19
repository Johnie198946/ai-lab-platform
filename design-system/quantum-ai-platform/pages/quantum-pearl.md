# iOS Quantum Pearl — luminous productivity override

> Current iOS visual source of truth. References: `IMG_2903.WEBP` and `IMG_2904.WEBP`. Preserve the spatial and material language without copying sample content.

## Foundations

- Cold pearl canvas `#F8F7FC` with static cyan, blue, violet and pink ambient light.
- Solid white content cards; translucency is reserved for floating navigation and modal chrome.
- Primary ink `#191521`, secondary ink `#746E7F`, border `#EAE6F2`.
- Brand gradient `#18C8CC → #328CE4 → #8057E8` is limited to primary CTA, selected knowledge cards and the featured task.
- SF Pro / Dynamic Type, 4/8 spacing rhythm, 20pt page gutter, 22–30pt card radii.

## Page mapping

- **Login:** sparse brand header, abstract dimensional artwork, value proposition and one contained authentication card.
- **Chat:** focused reading column, white assistant surfaces, violet user bubbles, persistent composer above navigation.
- **Tasks:** greeting header, one gradient featured workflow, two-column white Bento task cards, topology as a secondary drill-down.
- **Knowledge:** subscribed sources become vertically scrollable wallet cards; selecting a card extracts it into a full-screen detail surface.
- **Settings:** account overview, truthful usage visualization, profile, agents, skills and destructive account actions ordered by risk.

## Motion and accessibility

- Press feedback: 180ms scale to 0.97 without layout shift.
- Knowledge extraction: spring response 0.42 / damping 0.82; Reduce Motion uses opacity only.
- Minimum target 44pt. Primary text contrast >= 4.5:1. State is always paired with text or a symbol.
- Lists and fixed bottom chrome reserve safe-area space; no content may sit behind the tab bar or composer.
