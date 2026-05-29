Build a professional job tracking web app with a modern dark-themed UI.
## CSS Design System — Professional Modern Dark Theme

Apply these exact design tokens via CSS custom properties:

```css
:root {
  --bg-base: #0f1117;
  --bg-surface: #1a1d27;
  --bg-elevated: #22263a;
  --border: #2e3250;
  --border-subtle: #1e2238;

  --text-primary: #f0f2ff;
  --text-secondary: #8b90b8;
  --text-muted: #555a7a;

  --accent: #6c8ef5;
  --accent-hover: #8aa5ff;
  --accent-glow: rgba(108, 142, 245, 0.15);

  --status-applied: #4a9eff;
  --status-interview: #f5a623;
  --status-offer: #2ecc71;
  --status-rejected: #e74c3c;
  --status-saved: #9b59b6;

  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;

  --shadow-card: 0 4px 20px rgba(0,0,0,0.4);
  --shadow-glow: 0 0 0 1px var(--accent), 0 4px 20px var(--accent-glow);

  --font-heading: 'DM Sans', sans-serif;
  --font-body: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  --transition: 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
```

## UI Details
- Header: app name left, "Add Job" CTA button right (accent color with glow on hover)
- Cards: dark elevated surface, left border colored by status, subtle hover lift
- Inputs: dark background, border that glows with accent on focus
- Buttons: filled accent for primary, ghost for secondary actions
- Status badges: pill-shaped, colored per status variable
- Smooth transitions on all interactive elements
- Empty state with a helpful illustration message
- Fully responsive (mobile-friendly)

## Typography
Import from Google Fonts:
- DM Sans (headings, labels)
- Inter (body, inputs)

## Animations
- Cards fade+slide in on load (staggered, 50ms delay each)
- Modal opens with scale(0.95) → scale(1) + fade
- Button press: scale(0.97) on active

Keep everything in one index.html file. Output only the complete file.