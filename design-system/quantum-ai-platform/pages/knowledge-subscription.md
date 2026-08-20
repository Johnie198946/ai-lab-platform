# Knowledge Subscription Center Override

This page follows `ios-core.md` and replaces the earlier dense, overlapping wallet layout.

## Information hierarchy

1. Current organization entitlement: one compact summary surface.
2. Platform plan: horizontally paged comparison cards.
3. Optional knowledge packs: horizontally paged launch cards; incubating packs remain collapsed.
4. Approval: one safe-area action bar appears only after a new plan is selected.

## Component rules

- Use the label **可选知识包**, not “知识包钱包”. The latter is easily confused with the ordinary knowledge wallet.
- Never overlap knowledge-pack cards. Preserve the wallet metaphor through horizontal paging and a partially visible next card.
- Each launch card contains only title, risk label, short boundary, K5 progress, freshness and state.
- Full entitlement keys, governance explanation and selection controls belong in a native bottom sheet.
- `draft` and `incubating` packs use explicit “建设中” text and disabled semantics; color is supplementary.
- Keep one primary action on screen: the safe-area “提交审批” button.

## Motion and accessibility

- Horizontal paging and sheet presentation use native SwiftUI motion; no decorative looping animation.
- All buttons are at least 44pt, use SF Symbols and Dynamic Type roles.
- Reduced Motion uses the system transition without custom scale or offset animation.
- Maintain readable card order and VoiceOver labels independent of visual status color.
