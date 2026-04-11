# Augmented UI Atlas Info Panel

**Date:** 2026-04-11
**Scope:** Atlas3DPage info panel only (top-right detail panel)
**Status:** Approved

## Summary

Replace the Atlas3DPage info panel's standard CSS borders and border-radius with augmented-ui geometry, porting the exact clip/notch/round configuration from the developer's personal landing page (sssamuelll/landing-page). The panel uses a hybrid color scheme: cyan augmented borders during hover (reading state), transitioning to purple/orange gradient borders on click (persistent link established state).

## What Changes

### 1. Add augmented-ui dependency

Add the augmented-ui v2.0.0 CSS library via CDN link in `frontend/index.html`:

```html
<link rel="stylesheet" href="https://unpkg.com/augmented-ui@2.0.0/augmented-ui.min.css">
```

### 2. Augmented geometry configuration

Ported directly from the landing page's `.augs` class:

```css
.atlas-info-panel {
  /* Rectangular notches on left and right edges */
  --aug-rect-l1: initial;
  --aug-l1-width: 110px;
  --aug-l1-height: 4px;
  --aug-l-center: 57px;

  --aug-rect-r1: initial;
  --aug-r1-width: (100% - 125px - 50px);
  --aug-r1-height: 4px;
  --aug-r-center: 57px;

  /* Top-right corner clip with extend */
  --aug-clip-tr1: initial;
  --aug-tr1-alt-join-out: initial;
  --aug-tr1: 17px;
  --aug-clip-tr2: initial;
  --aug-tr2: 17px;
  --aug-tr-extend1: 50px;

  /* Rounded corners on opposite ends */
  --aug-round-tl1: initial;
  --aug-tl1: 8px;
  --aug-round-br1: initial;
  --aug-br1: 8px;

  /* Border and inlay */
  --aug-border: initial;
  --aug-border-all: 2px;
  --aug-inlay: initial;
  --aug-inlay-all: 2px;
}
```

### 3. Color states (hybrid approach)

**Hover / Reading state** (`.atlas-info-panel--reading`):
- `--aug-border-bg: #00eeff` (solid cyan)
- `--aug-inlay-bg: rgba(0, 238, 255, 0.08)`
- `--aug-inlay-opacity: 0.15`
- Subtle cyan box shadow: `0 0 20px rgba(0, 238, 255, 0.1)`

**Selected / Persistent link state** (`.atlas-info-panel--locked`):
- `--aug-border-bg: linear-gradient(to bottom left, rebeccapurple, orange)` (landing page gradient)
- `--aug-inlay-bg: rgba(102, 51, 153, 0.12)`
- `--aug-inlay-opacity: 0.25`
- Purple/orange glow: `0 0 40px rgba(102, 51, 153, 0.2), 0 0 20px rgba(255, 165, 0, 0.1)`

### 4. Files modified

| File | Change |
|------|--------|
| `frontend/index.html` | Add augmented-ui CDN link |
| `frontend/src/styles.css` | Add `.atlas-info-panel`, `--reading`, `--locked` classes |
| `frontend/src/pages/Atlas3DPage.tsx` | Replace info panel inline styles with augmented-ui classes and `data-augmented-ui` attribute |

### 5. What stays the same

- Panel position (`absolute`, top-right), width (320px), backdrop-filter blur
- Panel content layout (label, node name, cognitive debt sub-panel, release-focus hint)
- All Three.js code, hover/click logic, raycaster, OrbitControls
- All other Atlas UI elements (title overlay, loading state)
- All other pages and components across the dashboard

## Implementation Notes

- augmented-ui works via `data-augmented-ui` attribute on the element. The CSS custom properties define the geometry; the attribute triggers the clip-path generation.
- The `data-augmented-ui` attribute value is empty string (augmented-ui reads the CSS vars automatically).
- Transition between reading/locked states: swap the CSS class. augmented-ui re-clips on property change.
- The existing inline `border`, `borderRadius`, and `boxShadow` on the panel must be removed since augmented-ui handles the border via its own mechanism. `borderRadius` is replaced by `--aug-round-*` properties. Background and backdrop-filter remain as inline or class styles.
- The panel's `background` (`rgba(0,0,0,0.85)`) and `backdropFilter` (`blur(16px)`) stay as-is; augmented-ui clips the background along with the border.
