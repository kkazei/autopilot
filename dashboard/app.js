"use strict";
// Read-only dashboard. Every value from data.json is shown with textContent (never innerHTML), because it
// includes model output and trace text. The one href built from data is checked against bsky.app first.

const app = document.getElementById("app");
const modal = document.getElementById("modal");
const drawer = document.getElementById("drawer");
const RUNS_SHOWN = 8;
let data = null;
let allRuns = false;

function h(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

const badge = (text, kind) => h("span", { class: "badge" + (kind ? " " + kind : "") }, text);
const when = (iso) => (iso ? iso.slice(0, 19).replace("T", " ") + " UTC" : "");
const clock = (iso) => (iso ? iso.slice(11, 19) : "");
const day = (iso) => (iso ? iso.slice(0, 16).replace("T", " ") + " UTC" : "unknown time");
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// Sliced, not parsed: trace timestamps carry microseconds, which Date parsing does not handle the same in every browser.
const shortDay = (iso) => (iso ? `${MONTHS[Number(iso.slice(5, 7)) - 1] || "?"} ${Number(iso.slice(8, 10))} · ${iso.slice(11, 16)}` : "");
const empty = (text) => h("p", { class: "empty" }, text);
const bskyLink = (p) => (p.link && p.link.startsWith("https://bsky.app/profile/") ? p.link : null);

function metricsText(m) {
  m = m || {};
  return `${m.likes ?? 0} likes · ${m.reposts ?? 0} reposts · ${m.replies ?? 0} replies`;
}

function learningFor(postId) {
  return data.learnings.find((x) => x.post_id === postId) || null;
}

function postKind(p) {
  return p.status === "published" ? "ok" : p.status === "failed" ? "bad" : "warn";
}

const SCORE_NAMES = { voice: "Voice", clarity: "Clarity", cta: "CTA", policy_risk: "Policy risk" };
const scoreName = (k) => SCORE_NAMES[k] || k.replace("_", " ");

function scoreBars(scores, compact) {
  return h("div", { class: "scores" + (compact ? " compact" : ""), role: "list", "aria-label": "Critic scores out of 5" },
    Object.entries(scores).map(([k, v]) => h("div", { class: "score " + (v >= 4 ? "ok" : "bad"), role: "listitem", "aria-label": `${scoreName(k)} ${v} of 5` },
      h("span", { class: "score-name" }, scoreName(k)),
      h("span", { class: "bar", "aria-hidden": "true" }, h("span", { style: `width:${Math.max(0, Math.min(5, v)) * 20}%` })),
      h("span", { class: "score-num" }, `${v}/5`))));
}

// ---------- page sections ----------

function stats() {
  const o = data.overview;
  const tile = (num, label) => h("div", { class: "tile" }, h("div", { class: "num" }, num), h("div", { class: "lbl" }, label));
  return h("section", { class: "tiles", "aria-label": "Totals" },
    tile(o.live_posts, "Live posts on Bluesky"),
    tile(o.runs, "Runs traced"),
    tile(o.llm_calls, "Model calls (failed attempts included)"),
    tile(`${o.learnings_with_signal}/${o.learnings}`, "Learnings with real engagement signal"));
}

function pipeline() {
  const steps = ["Planner", "Writer", "Critic", "Harness checks", "Human yes", "Bluesky", "Analyst"];
  return h("section", { class: "flow card", "aria-label": "How it works" },
    h("ol", { class: "steps" }, steps.map((s, i) => h("li", null, h("span", { class: i === 3 || i === 4 ? "gate" : null }, s)))),
    h("p", { class: "muted small" }, "The harness, not the models, decides whether a post may go out. Publishing needs a human yes, every model and tool call is traced, and the analyst's learnings feed the next plan."));
}

function postCard(p) {
  const learning = learningFor(p.post_id);
  return h("li", null, h("button", { type: "button", class: "card post-card", onclick: () => openPost(p), "aria-label": `Open post from ${day(p.when)}, ${p.status}` },
    h("div", { class: "meta" },
      badge(p.status, postKind(p)), p.dry_run ? badge("dry run", "warn") : null,
      h("span", { class: "muted small push" }, shortDay(p.when))),
    h("p", { class: "post-text clamp" }, p.text),
    p.scores ? scoreBars(p.scores, true) : null,
    learning ? h("p", { class: "muted small" }, metricsText(learning.metrics)) : null));
}

function postsSection() {
  return h("section", { id: "posts-sec", class: "panel" },
    h("div", { class: "panel-head" }, h("h2", null, "Posts"), h("span", { class: "muted small" }, `${data.posts.length} recorded`)),
    data.posts.length ? h("ul", { class: "post-grid" }, data.posts.map(postCard)) : empty("No posts recorded yet."));
}

function learningsSection() {
  return h("section", { id: "learnings-sec", class: "panel" },
    h("div", { class: "panel-head" }, h("h2", null, "Learnings"), h("span", { class: "muted small" }, `${data.learnings.length} saved`)),
    h("p", { class: "muted small" }, "After a post has been live a while, the analyst reads its engagement and saves one sentence for the next plan. With too little engagement it says so rather than inventing a lesson."),
    data.learnings.length ? h("ul", { class: "learnings" }, data.learnings.map((l) => h("li", { class: "card learning" },
      h("div", { class: "meta" },
        badge(l.has_signal ? "has signal" : "not enough data", l.has_signal ? "ok" : "warn"),
        h("span", { class: "muted small push" }, shortDay(l.saved_at))),
      h("p", null, l.insight),
      h("p", { class: "muted small" }, metricsText(l.metrics))))) : empty("No learnings saved yet."));
}

// Labels are the first trace line, so they are turned into a short title here rather than shown raw.
function runTitle(r) {
  const m = /^run_post \| topic='(.*?)'/.exec(r.label || "");
  if (m) return { kind: "Single post", title: m[1] };
  if ((r.label || "").startsWith("run_outer")) return { kind: "Weekly loop", title: "Plan, write, measure" };
  return { kind: "Other run", title: (r.label || "untitled").slice(0, 80) };
}

function runOutcome(r) {
  const f = r.final || "";
  if (/^published/.test(f)) return /dryrun:\/\//.test(f) || /dry_run=True/.test(r.start || "") ? ["dry run", "warn"] : ["published", "ok"];
  if (/^blocked/.test(f)) return ["blocked", "warn"];
  if (/^failed/.test(f)) return ["failed", "bad"];
  if (/to measure/.test(f)) return ["measured", "ok"];
  if (/^stop|retry|backoff/.test(f)) return ["stopped", "bad"];
  return [f ? "ended" : "no decision", null];
}

function runRow(r) {
  const t = runTitle(r);
  const [label, kind] = runOutcome(r);
  const failed = r.events.filter((e) => !e.ok).length;
  return h("li", null, h("button", { type: "button", class: "run-row", onclick: () => openRun(r) },
    h("span", { class: "run-when muted small" }, shortDay(r.started)),
    h("span", { class: "run-main" }, h("span", { class: "run-kind" }, t.kind), h("span", { class: "run-title" }, t.title)),
    h("span", { class: "run-stats muted small" }, `${r.llm_calls} model · ${failed} failed step${failed === 1 ? "" : "s"}`),
    h("span", { class: "run-out" }, badge(label, kind))));
}

function runsSection() {
  const shown = allRuns ? data.runs : data.runs.slice(0, RUNS_SHOWN);
  return h("section", { id: "runs-sec", class: "panel" },
    h("div", { class: "panel-head" }, h("h2", null, "Runs"), h("span", { class: "muted small" }, `${data.runs.length} traced · open one for every step`)),
    data.runs.length ? h("ul", { class: "runs card" }, shown.map(runRow)) : empty("No runs recorded yet."),
    data.runs.length > RUNS_SHOWN ? h("button", { type: "button", class: "ghost", onclick: () => { allRuns = !allRuns; render(); } },
      allRuns ? "Show fewer" : `Show all ${data.runs.length} runs`) : null);
}

function render() {
  app.replaceChildren(
    stats(),
    pipeline(),
    h("div", { class: "columns" }, postsSection(), learningsSection()),
    runsSection());
}

// ---------- dialogs ----------

// The hash makes a post or run linkable; replaceState keeps opening and closing out of the back-button history.
function setHash(hash) {
  try { history.replaceState(null, "", hash || location.pathname + location.search); } catch (_) { /* file:// may refuse */ }
}

function dialogHead(id, title, sub, dlg) {
  return h("div", { class: "dlg-head" },
    h("div", null, h("h2", { id, class: "dlg-title" }, title), sub ? h("p", { class: "muted small" }, sub) : null),
    h("button", { type: "button", class: "icon-btn", "aria-label": "Close", onclick: () => dlg.close() }, "×"));
}

function show(dlg, children) {
  dlg.replaceChildren(...children.filter(Boolean));
  if (!dlg.open) dlg.showModal();
  dlg.scrollTop = 0;
}

function openPost(p) {
  const learning = learningFor(p.post_id);
  const link = bskyLink(p);
  const reasons = p.reasons ? Object.entries(p.reasons) : [];
  setHash("#post/" + p.post_id);
  show(modal, [
    dialogHead("modal-title", "Post", day(p.when), modal),
    h("div", { class: "dlg-body" },
      h("div", { class: "meta" }, badge(p.status, postKind(p)), p.dry_run ? badge("dry run", "warn") : null,
        p.attempt ? badge(`attempt ${p.attempt}`) : null),
      h("blockquote", { class: "post-text" }, p.text),
      p.scores ? [h("h3", null, "Critic scores"), scoreBars(p.scores, false)] : null,
      reasons.length ? h("dl", { class: "reasons" }, reasons.map(([k, v]) => [h("dt", null, scoreName(k)), h("dd", null, v)])) : null,
      p.reason ? [h("h3", null, "Reason"), h("p", null, p.reason)] : null,
      learning ? [h("h3", null, "Engagement when last measured"), h("p", null, metricsText(learning.metrics))] : null,
      link ? h("p", null, h("a", { class: "btn", href: link, rel: "noopener noreferrer", target: "_blank" }, "View on Bluesky ↗")) : null,
      h("p", { class: "muted small mono" }, `${p.post_id} · ${p.run_id}`)),
  ]);
}

function openRun(r) {
  const t = runTitle(r);
  const [label, kind] = runOutcome(r);
  const list = h("div", null);
  // Only the step list is redrawn, so the checkbox keeps focus when toggled.
  const fill = (problemsOnly) => {
    const shown = r.events.filter((e) => !problemsOnly || !e.ok);
    list.replaceChildren(shown.length ? h("ol", { class: "events" }, shown.map(eventRow)) : empty("No failed steps in this run."));
  };
  const box = h("input", { type: "checkbox", id: "problems", onchange: (e) => { setSessionFlag("problems", e.target.checked); fill(e.target.checked); } });
  box.checked = sessionFlag("problems");
  fill(box.checked);
  setHash("#run/" + r.run_id);
  show(drawer, [
    dialogHead("drawer-title", t.title, `${t.kind} · ${day(r.started)}`, drawer),
    h("div", { class: "dlg-body" },
      h("div", { class: "meta" }, badge(label, kind), badge(r.ok ? "no failed steps" : "has failed steps", r.ok ? "ok" : "warn")),
      h("dl", { class: "runsummary" },
        h("dt", null, "Started"), h("dd", null, when(r.started)),
        h("dt", null, "Began"), h("dd", null, r.start),
        h("dt", null, "Ended"), h("dd", null, r.final || "(no final decision)"),
        h("dt", null, "Model calls"), h("dd", null, `${r.llm_calls} of ${r.events.length} steps`),
        h("dt", null, "Run id"), h("dd", { class: "mono" }, r.run_id)),
      h("label", { class: "toggle" }, box, " Only failed steps"),
      list),
  ]);
}

function eventRow(e) {
  const out = e.summary_out || "";
  return h("li", null, h("details", { class: "event " + (e.ok ? "pass" : "fail") },
    h("summary", null,
      h("div", { class: "line1" },
        h("span", { class: "time" }, clock(e.ts)),
        badge(e.agent), badge(e.kind.replace("_", " ")), badge(e.ok ? "✓ ok" : "✗ failed", e.ok ? "ok" : "bad"),
        e.model ? h("span", { class: "muted small" }, e.model) : null),
      h("div", { class: "out" }, out.length > 140 ? out.slice(0, 140) + "…" : out)),
    h("div", { class: "body" },
      h("strong", { class: "small" }, "Input"), h("pre", null, e.summary_in || ""),
      h("strong", { class: "small" }, "Output"), h("pre", null, out),
      e.latency_ms != null ? h("p", { class: "muted small" }, `${e.latency_ms} ms`) : null)));
}

function openLimits() {
  const o = data.overview;
  setHash("#limits");
  show(modal, [
    dialogHead("modal-title", "What is partial or unproven", "Stated plainly, so the numbers on this page are not over-read.", modal),
    h("div", { class: "dlg-body" },
      h("ul", { class: "limits" }, o.partial.map((p) => h("li", null, p))),
      o.unreadable_traces.length ? h("p", { class: "muted" }, `${o.unreadable_traces.length} trace file(s) could not be read and are not shown.`) : null),
  ]);
}

function openFromHash() {
  const [kind, id] = location.hash.slice(1).split("/");
  if (kind === "limits") openLimits();
  if (kind === "post") { const p = data.posts.find((x) => x.post_id === id); if (p) openPost(p); }
  if (kind === "run" || kind === "trace") { const r = data.runs.find((x) => x.run_id === id); if (r) openRun(r); }
}

// Clicking the backdrop lands on the dialog element itself; clicks inside land on its children.
for (const dlg of [modal, drawer]) {
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("close", () => { if (/^#(post\/|run\/|trace\/|limits$)/.test(location.hash)) setHash(""); });
}

// A remembered checkbox is a convenience only; storage may be blocked, so every access is guarded.
function sessionFlag(k) { try { return sessionStorage.getItem("autopilot." + k) === "1"; } catch (_) { return false; } }
function setSessionFlag(k, v) { try { sessionStorage.setItem("autopilot." + k, v ? "1" : "0"); } catch (_) { /* ignore */ } }

async function start() {
  try {
    data = window.DASHBOARD_DATA || (await (await fetch("data.json")).json());
  } catch (_) {
    app.replaceChildren(h("p", { class: "empty" }, "No data found. Run: python -m scripts.export_dashboard_data"));
    return;
  }
  document.getElementById("foot").textContent = `Data exported ${when(data.exported_at)} (schema ${data.schema_version}). Read-only: nothing here can post.`;
  const limits = data.overview.partial.length + (data.overview.unreadable_traces.length ? 1 : 0);
  if (limits) {
    const btn = document.getElementById("limits-btn");
    document.getElementById("limits-count").textContent = String(limits);
    btn.hidden = false;
    btn.addEventListener("click", openLimits);
  }
  render();
  openFromHash();
  window.addEventListener("hashchange", openFromHash);
}
start();
