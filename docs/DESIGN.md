# Autopilot web app: design

Figma: https://www.figma.com/design/jeXBDZ9i6pQpTsIEPAB4Uc (pages: Foundations, Components, Screens).
Direction: **mission control**. Dense, precise, data first. Graphite surfaces, hairline borders, tight radii, monospace for
ids, times and numbers, and status lights. Color carries meaning only; amber is reserved for "needs you".

## Tokens

Two themes, same names. The app follows the system setting (`prefers-color-scheme`). In Figma the Starter plan allows one
mode per collection, so the themes are two collections (`Color · Dark`, `Color · Light`) with identical variable names.

| Token | Dark | Light |
|---|---|---|
| `bg/canvas` | `#0A0C0F` | `#F4F5F7` |
| `bg/surface` | `#111418` | `#FFFFFF` |
| `bg/raised` | `#181C22` | `#F0F2F4` |
| `bg/inset` | `#07080A` | `#EAEDF0` |
| `border/default` | `#232830` | `#DCE0E5` |
| `border/strong` | `#343A46` | `#C3C9D1` |
| `text/primary` | `#E7E9EC` | `#0E1116` |
| `text/secondary` | `#9AA3AF` | `#4F5865` |
| `text/tertiary` | `#646D7A` | `#7F8894` |
| `action/primary-bg` | `#E7E9EC` | `#0E1116` |
| `action/primary-fg` | `#0A0C0F` | `#FFFFFF` |
| `status/ok` | `#3FB950` | `#1A7F37` |
| `status/warn` | `#F2A93B` | `#9A5800` |
| `status/error` | `#F85149` | `#CF222E` |
| `status/info` | `#58A6FF` | `#0969DA` |
| `status/*-bg` | the status color at 14% | the status color at 10% (warn uses `#BF7400`) |

Space: 4, 8, 12, 16, 20, 24, 32, 40 (`space/1` to `space/10`). Radius: `sm` 4, `md` 6, `lg` 8, `pill` 999.

## Type

Geist and Geist Mono (`next/font` ships both).

| Style | Font | Size / line | Notes |
|---|---|---|---|
| display | Geist SemiBold | 28 / 34 | -1.5% tracking; page titles |
| title-lg | Geist SemiBold | 20 / 28 | mobile page titles |
| title | Geist SemiBold | 16 / 24 | card titles |
| body-lg | Geist Regular | 16 / 26 | draft text (the thing being approved) |
| body | Geist Regular | 14 / 22 | default |
| body-strong | Geist Medium | 14 / 22 | buttons, list titles |
| small | Geist Regular | 12 / 18 | secondary lines |
| label | Geist Mono Medium | 11 / 16 | uppercase, +6% tracking; section and field labels |
| mono | Geist Mono Regular | 13 / 20 | values |
| mono-sm | Geist Mono Regular | 12 / 18 | ids, times, models, trace cells |
| metric | Geist Mono Medium | 28 / 32 | stat tiles, scores |

## Components (Figma page "Components")

- **Button**: primary, secondary (raised and strong border), danger (error tint), ghost. 14px horizontal and 8px vertical padding, radius md.
- **Badge**: ok, warn ("needs you"), error, info, neutral. Pill, 6px dot, mono label.
- **ScoreTile**: pass and fail (warn tint). Label, score out of 5 in `metric`, one-line reason.
- **GuardChip**: pass (check, ok) and fail (x, error).
- **NavItem**: default and active (raised background), with a swappable icon.
- **TraceRow**: ok, error (summary in red), selected (raised background with a 2px info left edge). Columns: time 64,
  status dot, agent 64, kind 80, summary (fills the rest, one line, truncated), model 168, latency 56 (right-aligned).
- **QueueRow**: day, topic and angle, goal, status badge in a 112px right-aligned slot.
- Icons are Lucide paths at 16px with a 2px stroke.

## Screens (Figma page "Screens")

1. **Control, desktop** (dark and light). 240px sidebar (wordmark, nav, system lights for backend, database and cron, user).
   Main area: header with Dry run, Plan next week and Run next post. Four stat tiles (requests used out of 45 with a bar, next
   post, rate cap, last run). Left column: the approval card (amber border, draft in an inset block, character count, four
   score tiles, guardrail chips, then Approve & publish, Not now and Reject) and This week (QueueRows). Right column (352px):
   live run steps, recent runs and the latest learning.
2. **Trace viewer, desktop**. Breadcrumb, title with result badges, five stat tiles, event list (filter chips, an "N failed"
   toggle, column header, TraceRows), and a 352px detail panel: fields, fallback chain, input and output code blocks, and the
   note that the harness recomputes "passed".
3. **Control, phone** (390). Top bar with a live light, quota bar, approval card with a 2×2 score grid, full-width Approve,
   then Not now and Reject side by side, a compact week list and a bottom tab bar (Control, Plan, Runs, Learnings).

## Behaviour notes for the build

- The approval card exists only while the backend reports a pending approval. Its timer counts toward the backend's 15-minute
  timeout; at zero the post is carried forward, and the card says so.
- Approve calls the backend; the button shows a busy state until the next status poll confirms.
- When the backend is asleep (Render free tier), the system light is grey with "waking…" and the run buttons are disabled
  until `/health` answers.
- Red appears only for failures and Reject; amber only for things waiting on the owner.

## Motion (added with the KokonutUI pass)

Purposeful only: what changes state animates; nothing loops for decoration. Everything follows the system's
reduce-motion setting (`MotionConfig reducedMotion="user"`). Ease-out `cubic-bezier(0.23, 1, 0.32, 1)`, 200–350 ms.

- **Entry**: cards rise 8px and unblur in a 50–70 ms stagger, once per page load.
- **Numbers** count from their previous value (quota, rate cap, exit code).
- **Approval card** slides in with a blur, its amber ring breathes slowly while it waits, scores and guardrails stagger in.
  Live posts use a **hold-to-publish** button (1.5 s); dry runs stay a single click.
- **Live steps** stream in from the left; the run badge crossfades between running, waiting and the result.
- **Run island** (KokonutUI Status Island): a pill at the bottom of every page while a run is live, with a Trace or Review
  action; it reports the result for 5 s after the run ends.
- **Run timeline** (adapted from KokonutUI AI Agent Lanes): one lane per agent on a shared clock. A finished run replays
  in about 3.5 s; a live run follows the newest event. Bars: blue model call, red failure, green guardrail, amber the wait
  for the owner, solid tool call, hatched decision. Clicking a bar opens that event.

KokonutUI components live in `web/components/kokonutui/` (MIT, attribution kept in each file).

## Navigation glass (added 2026-10-29)

The navigation floats over content as liquid glass: a translucent fill with a 22px backdrop blur, a light top edge and a
darker bottom edge (`glass` utility, tokens `--glass-*`). Glass is only for navigation that sits above scrolling content;
cards stay solid. With "reduce transparency" on, glass falls back to `bg/surface`.

- **Desktop sidebar**: a floating glass panel, 236px, collapsible to 68px icons with the panel button or Ctrl/⌘ B; the
  width is kept in a `nav` cookie so it renders right on load. Collapsed items show glass tooltips.
- **Active item**: a brighter glass lens that springs to the page you open (one shared element). This is the nav's one
  motion; icons only compress on press.
- **Live badges**: an amber pulse on Control while a draft needs you, a steady blue light on Traces while a run is going.
- **Phone header**: transparent at the top; once content scrolls under it, it turns to glass and the wordmark swaps for the
  page title.
- **Phone tab bar**: a floating glass bar with the same lens. Scrolling down shrinks it to icons (44px targets); scrolling
  up restores the labels.
- On phones the Control actions stack: Run next post full width, Plan next week and Dry run beneath.

## Time

Every instant is shown in the viewer's timezone (24-hour), read from the browser and remembered in a `tz` cookie so
server-rendered pages match. Plan days are calendar dates and never shift. The zone offset (GMT+8) is shown where a time
stands alone, such as the trace detail and the cron slot.
