# From Broken PR to Autonomous Recovery

A Slidev keynote for the CI Control Plane workshop:
**Claude Code Hooks, Headless Agents, Skills & Validation Gates**.
16 slides, 6 chapters, ~25 min of talk + a 10–15 min live demo.

The deck is self-contained: it needs no backend, no network and no external
images (fonts are bundled through `@fontsource`).

## Run

```bash
npm install
npm run dev        # http://localhost:3030 — opens the browser
```

| Script | What it does |
|---|---|
| `npm run dev` | dev server with hot reload |
| `npm run build` | static SPA in `dist/` (serve with any static server) |
| `npm run export` | PDF fallback → `dist/keynote.pdf` (final state of every slide) |
| `npm run export:clicks` | PDF with one page per click step → `dist/keynote-steps.pdf` |
| `npm run export:png` | one PNG per slide → `dist/png/` |

The exports use Playwright. If Chromium is missing, run `npx playwright install chromium` once.

## Presenting

| Key | Action |
|---|---|
| `→` / `space` | next click or slide |
| `←` | previous click or slide |
| `↓` / `↑` | next / previous slide, skipping click steps |
| `f` | fullscreen |
| `o` | slide overview |
| `g` | go to slide |
| `d` | toggle dark mode (the deck is dark-only) |

- **Presenter mode** (notes, timer, next slide): open `http://localhost:3030/presenter`
  or use the presenter icon in the bottom-left toolbar. Speaker notes are in Ukrainian.
- Every animated diagram is driven by clicks — nothing autoplays except two ambient loops
  (title background, finale orbit). `prefers-reduced-motion` disables animation.
- **Slide 10 (architecture)**: besides click steps, any node can be clicked with the mouse
  to show its repository path and responsibility — useful for Q&A.
- **Slide 13 (demo scenario)**: clicks step A → B → C; tabs are clickable as well.
  The scenario tagged "live demo" is set with `live="C"` in `slides.md`.
- **Slide 14** is the bridge to the real dashboard (`localhost:8000`). The demo itself is
  never simulated in the deck.

Live-demo prep (in the main repository): backend running, `gh auth status` OK, `claude`
logged in, Slack webhook configured, scenario branch prepared with
`demo/scripts/scenario.py prepare C`.

## Structure

```
slides.md                 all slides + speaker notes (HTML comments)
components/               interactive Vue components (one per concept)
global-top.vue            chapter progress footer
styles/tokens.css         design tokens (colour, type, radius, motion)
styles/base.css           canvas, typography, code blocks, shared motion
styles/slides.css         per-slide compositions
setup/shiki.ts            code theme
setup/mermaid.ts          Mermaid theme
docs/storyboard.md        storyboard, component plan, verified-vs-proposed notes
```

Canvas is 1280×720 (16:9) and scales to 1920×1080 and other sizes.

## Technical accuracy

Claude Code behaviour shown in the deck was checked against code.claude.com
(hooks, skills, sub-agents, headless) and `claude --help` v2.1.308. Code on slides 6 and 8 is
excerpted from this repository's `.claude/` directory; validator findings on slide 13 are the
real output of `demo/scripts/scenario.py verify all`. The terminal output on slide 7 is
labelled as illustrative.
