"use strict";
// Read-only dashboard. Every value from data.json is shown with textContent (never innerHTML), because it
// includes model output and trace text. The one href built from data is checked against bsky.app first.

const VIEWS = ["overview", "posts", "learnings", "trace"];
const app = document.getElementById("app");
let data = null;

function h(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

const badge = (text, kind) => h("span", { class: "badge" + (kind ? " " + kind : "") }, text);
const when = (iso) => (iso ? iso.slice(0, 19).replace("T", " ") + " UTC" : "");
const clock = (iso) => (iso ? iso.slice(11, 19) : "");
const day = (iso) => (iso ? iso.slice(0, 16).replace("T", " ") + " UTC" : "unknown time");
const empty = (text) => h("p", { class: "empty" }, text);

function overview() {
  const o = data.overview;
  const tile = (num, label) => h("div", { class: "tile" }, h("div", { class: "num" }, num), h("div", { class: "lbl" }, label));
  return [
    h("div", { class: "tiles" },
      tile(o.live_posts, "live posts on Bluesky"),
      tile(o.runs, "runs traced"),
      tile(o.llm_calls, "model calls recorded (failed attempts included)"),
      tile(`${o.learnings_with_signal} of ${o.learnings}`, "learnings with real engagement signal")),
    h("div", { class: "card partial" },
      h("strong", null, "What is partial or unproven"),
      h("ul", null, o.partial.map((p) => h("li", null, p)))),
    o.unreadable_traces.length ? h("p", { class: "muted" }, `${o.unreadable_traces.length} trace file(s) could not be read and are not shown.`) : null,
    h("h2", null, "How it works, in short"),
    h("p", null, "A planner picks the week's posts, a writer drafts them, a critic scores each draft, and the harness (not the models) decides whether a post may go out. Publishing needs a human yes, and every model and tool call is written to a trace."),
    h("p", { class: "muted" }, "Use the tabs above: Posts shows what went live and why it passed, Learnings what the agent took from the results, Trace every step of every run."),
  ];
}

function engagementFor(postId) {
  const l = data.learnings.find((x) => x.post_id === postId);
  if (!l) return null;
  const m = l.metrics || {};
  return `${m.likes ?? 0} likes · ${m.reposts ?? 0} reposts · ${m.replies ?? 0} replies`;
}

function posts() {
  if (!data.posts.length) return [empty("No posts recorded yet.")];
  return data.posts.map((p) => {
    const kind = p.status === "published" ? "ok" : p.status === "failed" ? "bad" : "warn";
    const link = p.link && p.link.startsWith("https://bsky.app/profile/") ? p.link : null;
    const reasons = p.reasons ? Object.entries(p.reasons) : [];
    return h("article", { class: "card" },
      h("div", { class: "meta" },
        badge(p.status, kind), p.dry_run ? badge("dry run", "warn") : null,
        h("span", { class: "muted small" }, day(p.when))),
      h("p", { class: "post-text" }, p.text),
      p.scores ? h("div", { class: "scores", role: "list", "aria-label": "Critic scores out of 5" },
        Object.entries(p.scores).map(([k, v]) => h("span", { class: "badge " + (v >= 4 ? "ok" : "bad"), role: "listitem" }, `${k.replace("_", " ")} ${v}/5`))) : null,
      p.reason ? h("p", { class: "muted" }, "Reason: " + p.reason) : null,
      engagementFor(p.post_id) ? h("p", { class: "muted small" }, "Engagement when last measured: " + engagementFor(p.post_id)) : null,
      reasons.length ? h("details", null, h("summary", null, "Critic's reasons"),
        h("dl", { class: "reasons" }, reasons.map(([k, v]) => [h("dt", null, k.replace("_", " ")), h("dd", null, v)]))) : null,
      link ? h("p", { class: "small" }, h("a", { href: link, rel: "noopener noreferrer", target: "_blank" }, "View on Bluesky ↗")) : null,
      h("p", { class: "muted small" }, `post ${p.post_id} · ${p.run_id}`));
  });
}

function learnings() {
  if (!data.learnings.length) return [empty("No learnings saved yet.")];
  return [
    h("p", { class: "muted" }, "After a post has been live a while, the analyst reads its engagement and saves one sentence for the next plan. With too little engagement it says so rather than inventing a lesson."),
    ...data.learnings.map((l) => {
      const m = l.metrics || {};
      return h("article", { class: "card" },
        h("div", { class: "meta" },
          badge(l.has_signal ? "has signal" : "not enough data", l.has_signal ? "ok" : "warn"),
          h("span", { class: "muted small" }, day(l.saved_at))),
        h("p", null, l.insight),
        h("p", { class: "muted small" }, `${m.likes ?? 0} likes · ${m.reposts ?? 0} reposts · ${m.replies ?? 0} replies · post ${l.post_id}`));
    }),
  ];
}

function traceView() {
  if (!data.runs.length) return [empty("No runs recorded yet.")];
  const wanted = (location.hash.split("/")[1] || "");
  const run = data.runs.find((r) => r.run_id === wanted) || data.runs[0];
  const problemsOnly = sessionFlag("problems");
  const select = h("select", {
    id: "runpick", "aria-label": "Choose a run",
    onchange: (e) => { location.hash = "#trace/" + e.target.value; },
  }, data.runs.map((r) => h("option", Object.assign({ value: r.run_id }, r.run_id === run.run_id ? { selected: true } : {}),
    `${day(r.started)} · ${r.label.slice(0, 28)} · ${r.ok ? "ok" : "had failures"}`)));
  const box = h("input", { type: "checkbox", id: "problems", onchange: (e) => { setSessionFlag("problems", e.target.checked); render(); } });
  box.checked = problemsOnly;
  const shown = run.events.filter((e) => !problemsOnly || !e.ok);
  return [
    h("div", { class: "controls" },
      h("label", { for: "runpick" }, "Run: "), select,
      h("label", null, box, " only failed steps")),
    h("div", { class: "card runsummary" },
      h("div", { class: "meta" }, badge(run.ok ? "no failed steps" : "has failed steps", run.ok ? "ok" : "warn"), h("span", { class: "muted small" }, run.run_id)),
      h("dl", null,
        h("dt", null, "Started"), h("dd", null, when(run.started)),
        h("dt", null, "Began"), h("dd", null, run.start),
        h("dt", null, "Ended"), h("dd", null, run.final || "(no final decision)"),
        h("dt", null, "Model calls"), h("dd", null, `${run.llm_calls} of ${run.events.length} steps`))),
    shown.length ? h("ol", { class: "events" }, shown.map(eventRow)) : empty("No failed steps in this run."),
  ];
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

// A remembered checkbox is a convenience only; storage may be blocked, so every access is guarded.
function sessionFlag(k) { try { return sessionStorage.getItem("autopilot." + k) === "1"; } catch (_) { return false; } }
function setSessionFlag(k, v) { try { sessionStorage.setItem("autopilot." + k, v ? "1" : "0"); } catch (_) { /* ignore */ } }

function render() {
  const view = VIEWS.includes(location.hash.slice(1).split("/")[0]) ? location.hash.slice(1).split("/")[0] : "overview";
  document.querySelectorAll(".tabs a").forEach((a) => {
    if (a.dataset.view === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  const body = { overview, posts, learnings, trace: traceView }[view]();
  app.replaceChildren(h("h2", { style: "margin-top:16px" }, { overview: "Overview", posts: "Posts", learnings: "Learnings", trace: "Trace" }[view]), ...body.filter(Boolean));
  document.title = "Autopilot · " + view;
}

async function start() {
  try {
    data = window.DASHBOARD_DATA || (await (await fetch("data.json")).json());
  } catch (_) {
    app.replaceChildren(h("p", { class: "empty" }, "No data found. Run: python -m scripts.export_dashboard_data"));
    return;
  }
  document.getElementById("foot").textContent = `Data exported ${when(data.exported_at)} (schema ${data.schema_version}). Read-only: nothing here can post.`;
  window.addEventListener("hashchange", render);
  render();
}
start();
