# Storyboard & component plan

Talk: **From Broken PR to Autonomous Recovery** — 35–45 min incl. a 10–15 min live demo.
Canvas 1280×720 (scales to 1920×1080). Visible content in English, speaker notes in Ukrainian.

| # | Chapter | Slide | Composition | Component | Clicks |
|---|---|---|---|---|---|
| 1 | 1 · Problem | Title | Hero type over an ambient node field | `HeroFlow` | 0 |
| 2 | 1 · Problem | The Traditional Workflow | Horizontal pipeline, human-effort bracket | `AnimatedWorkflow` | 7 |
| 3 | 1 · Problem | The Opportunity | Two lanes (CI-only vs agent + gate), 3-part thesis | `OpportunityLanes` | 3 |
| 4 | 2 · Hooks | What Are Hooks? | Definition + facts left, Mermaid sequence right, hook-vs-webhook strip | Mermaid | 1 |
| 5 | 2 · Hooks | Not Just PostToolUse | Hook-event catalog along the session lifecycle; blocking power + ideas per event | `HookEvents` | 2 |
| 6 | 2 · Hooks | Hook Lifecycle | 6-stage flow with travelling packet + payload card per stage | `HookLifecycle` | 6 |
| 7 | 2 · Hooks | Hook Implementation | `settings.json` + real hook excerpt with line-highlight steps, synced legend | Shiki + `StepLegend` | 5 |
| 8 | 3 · Headless | What Is Headless Mode? | Interactive vs headless contrast + terminal | `TerminalDemo` | 3 |
| 9 | 3 · Headless | Skills vs Subagents | Main context ↔ skill (knowledge) / subagent (isolated worker) | `SkillSubagent` | 2 |
| 10 | 3 · Headless | Agent Reasoning Pipeline | 5-stage pipeline + structured diagnosis card | `AgentPipeline` | 5 |
| 11 | 4 · Architecture | Full System Architecture | Snake architecture map, zone highlighting, clickable nodes | `ArchitectureExplorer` | 6 |
| 12 | 4 · Architecture | The State Machine | SVG state graph laid over the 4 Kanban columns | `StateMachine` | 3 |
| 13 | 4 · Architecture | Trust Boundaries | AI band over a deterministic band, gates along a timeline | `TrustLayers` | 3 |
| 14 | 5 · Demo | Demo Scenario | values.yaml diff + validation-gate ladder, scenarios A/B/C | `DemoScenario` → `CodeDiff`, `ValidationGate` | 2 |
| 15 | 5 · Demo | Let's Break a Deployment. | Dramatic type + live checklist (no simulation) | — | 0 |
| 16 | 6 · Build | Automation Maturity Model | Ascending staircase of 3 levels | `MaturityModel` | 3 |
| 17 | 6 · Build | Your Turn | Orbit of applications around "one event", closing line | `YourTurn` | 2 |

Shared: `global-top.vue` (chapter progress + page), `StepLegend`, design tokens in `styles/tokens.css`, per-slide compositions in `styles/slides.css`.

## Verified vs proposed

Claims about Claude Code were checked against code.claude.com docs (hooks, skills, sub-agents,
headless) and `claude --help` (v2.1.308) on 2026-10-22. Code shown on slides 7, 9 is excerpted
from the repository (`.claude/settings.json`, `.claude/hooks/register_pr.py`,
`.claude/skills/k8s-failure-analysis/SKILL.md`, `.claude/agents/k8s-remediator.md`).
The hook-event
list on slide 5 was checked against code.claude.com/docs/en/hooks; only PostToolUse is
implemented in this repo, and the per-event ideas are marked "could". Terminal output on slide 8
is marked as illustrative. The React dashboard was not yet implemented when the deck was written; the deck never depends on it.
