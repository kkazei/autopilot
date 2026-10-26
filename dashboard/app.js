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

// A badge made of a glyph gets a spoken label; the others already read as words.
const badge = (text, kind, spoken) => h("span", { class: "badge" + (kind ? " " + kind : ""), role: spoken ? "img" : null, "aria-label": spoken || null }, text);
// An issue is any step that went wrong, including ones the harness recovered from (a repair, a retry). It is not
// the run's outcome: a published run can have issues, and a declined draft is the system working as intended, so a
// decline is not counted as one.
const isFailure = (e) => !e.ok && !/human reviewer did not approve/.test(e.summary_out || "");
// Every stored time is UTC and is shown in the viewer's own time zone. The string is cut to whole seconds before it
// is parsed, because trace timestamps carry microseconds, which Date does not parse the same in every browser.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const toDate = (iso) => {
  const d = new Date(String(iso || "").slice(0, 19) + "Z");
  return Number.isNaN(d.getTime()) ? null : d;
};
const pad = (n) => String(n).padStart(2, "0");
const hm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
function zoneName(d) {
  try {
    const part = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(d).find((p) => p.type === "timeZoneName");
    return part ? part.value : "";
  } catch (_) { return ""; }
}
const when = (iso) => { const d = toDate(iso); return d ? `${ymd(d)} ${hm(d)}:${pad(d.getSeconds())} ${zoneName(d)}`.trim() : ""; };
const clock = (iso) => { const d = toDate(iso); return d ? `${hm(d)}:${pad(d.getSeconds())}` : ""; };
const day = (iso) => { const d = toDate(iso); return d ? `${ymd(d)} ${hm(d)} ${zoneName(d)}`.trim() : "unknown time"; };
const shortDay = (iso) => { const d = toDate(iso); return d ? `${MONTHS[d.getMonth()]} ${d.getDate()} · ${hm(d)}` : ""; };
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
  const tile = (num, label, href) => h(href ? "a" : "div", { class: "tile" + (href ? " link" : ""), href }, h("div", { class: "num" }, num), h("div", { class: "lbl" }, label));
  return h("section", { class: "tiles", "aria-label": "Totals" },
    tile(o.live_posts, "Live posts on Bluesky"),
    tile(o.runs, "Runs traced"),
    tile(o.llm_calls, "Model calls (failed attempts included)"),
    tile(`${o.learnings_with_signal}/${o.learnings}`, "Learnings backed by engagement", "#learnings-sec"));
}

function pipeline() {
  const steps = ["Planner", "Writer", "Critic", "Harness checks", "Human yes", "Bluesky", "Analyst"];
  return h("section", { class: "flow card", "aria-label": "How it works" },
    h("ol", { class: "steps" }, steps.map((s, i) => h("li", null, h("span", { class: i === 3 || i === 4 ? "gate" : null }, s)))),
    h("p", { class: "muted small" }, "The harness, not the models, decides whether a post may go out. Publishing needs a human yes, asked last, so nobody is shown a draft that fails a code check. Every model and tool call is traced, and the analyst's learnings feed the next plan."));
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

function learningCard(l) {
  const post = data.posts.find((p) => p.post_id === l.post_id) || null;
  const m = l.metrics || {};
  return h("li", { class: "card learning" },
    h("div", { class: "meta" },
      badge(l.has_signal ? "Some engagement" : "Too early to tell", l.has_signal ? "ok" : "warn"),
      h("span", { class: "muted small push" }, shortDay(l.saved_at))),
    // The saved line for a post with too little engagement is a fixed system sentence; the card says it in plain words.
    h("p", { class: "learning-text" }, l.has_signal ? l.insight : "Too little engagement so far to learn anything from this post."),
    h("div", { class: "metrics", "aria-label": "Engagement when measured" },
      [["likes", m.likes], ["reposts", m.reposts], ["replies", m.replies]].map(([k, v]) => h("span", { class: "metric" }, `${v ?? 0} ${k}`))),
    post ? h("button", { type: "button", class: "from-post", onclick: () => openPost(post) },
      h("span", { class: "muted small" }, "From the post"), h("span", { class: "clamp-2" }, post.text)) : null);
}

function learningsSection() {
  return h("section", { id: "learnings-sec", class: "panel" },
    h("div", { class: "panel-head" }, h("h2", null, "What the system learned"), h("span", { class: "muted small" }, `${data.learnings.length} saved`)),
    h("p", { class: "muted section-intro" }, "Once a post has been live for a while, the analyst reads its likes, reposts and replies and writes one sentence for the next plan. If there is too little engagement it says so instead of guessing."),
    data.learnings.length ? h("ul", { class: "learn-grid" }, data.learnings.map(learningCard)) : empty("No learnings saved yet."));
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

// The harness asks a person last, so the require_approval row is the record of what the person did. Nothing is
// guessed: a run with no such row and no failed code check has no approval story, and a run whose approval was
// switched off says so instead of claiming a human said yes.
const secondsBetween = (a, b) => {
  const s = (Date.parse(String(b).slice(0, 19) + "Z") - Date.parse(String(a).slice(0, 19) + "Z")) / 1000;
  return Number.isFinite(s) && s >= 0 ? Math.round(s) : null;
};

function approvalOf(r) {
  const evs = r.events;
  const i = evs.findIndex((e) => e.kind === "guardrail" && /^require_approval\b/.test(e.summary_in || ""));
  if (i < 0) {
    const codeStopped = /^blocked/.test(r.final || "") && evs.some((e) => e.kind === "guardrail" && !e.ok);
    return codeStopped ? { state: "code" } : null;
  }
  const e = evs[i];
  const out = e.summary_out || "";
  if (/^skipped/.test(out)) return { state: "code" };
  if (/approval disabled/.test(out)) return { state: "off" };
  if (e.ok) return { state: "approved", seconds: i > 0 ? secondsBetween(evs[i - 1].ts, e.ts) : null };
  if (!/did not approve/.test(out)) return { state: "noanswer" };
  const draft = (e.summary_in || "").replace(/^require_approval \| /, "");
  const row = evs.slice(0, i).reverse().find((x) => /^inner loop \S+ attempt \d+ \| /.test(x.summary_in || ""));
  const scores = {};
  for (const m of (row ? row.summary_in.split(" | ")[1] : "").matchAll(/(\w+)=(\d)/g)) scores[m[1]] = Number(m[2]);
  return { state: "declined", draft, scores: Object.keys(scores).length ? scores : null };
}

function runBadges(r) {
  const out = runOutcome(r);
  const ap = approvalOf(r);
  if (!ap) return [out];
  if (ap.state === "declined") return [["declined by human", "warn"]];
  if (ap.state === "code") return [["blocked by code", "warn"]];
  if (ap.state === "noanswer") return [["no human answer", "warn"]];
  if (ap.state === "off") return [out, ["approval off", "warn"]];
  // Approved, then the publish itself failed: one badge, so a green "human ✓" never sits beside a red "failed".
  if (out[0] === "failed") return [["approved · publish failed", "bad"]];
  return [out, ["human ✓", "ok", "approved by a human"]];
}

const APPROVAL_TEXT = {
  approved: (ap) => `Approved by a person${ap.seconds != null ? ` after ${ap.seconds}s` : ""}. The code checks passed first, then a person said yes.`,
  declined: () => "Declined by a person. The code checks passed, the person said no, and nothing was published.",
  code: () => "Blocked by code before anyone was asked. A draft that fails a check is never shown for approval.",
  off: () => "Approval was switched off for this run, so no person was asked.",
  noanswer: () => "No person answered (the terminal had no input), so nothing was published.",
};

function approvalBlock(ap) {
  if (!ap) return null;
  return h("div", { class: "approval card" },
    h("h3", null, "Human approval"),
    h("p", null, APPROVAL_TEXT[ap.state](ap)),
    ap.state === "declined" && ap.draft ? [h("p", { class: "muted small" }, "The draft that was declined:"), h("blockquote", { class: "post-text" }, ap.draft)] : null,
    ap.state === "declined" && ap.scores ? [h("p", { class: "muted small" }, "The critic's scores for it:"), scoreBars(ap.scores, true)] : null);
}

function runRow(r) {
  const t = runTitle(r);
  const failed = r.events.filter(isFailure).length;
  return h("li", null, h("button", { type: "button", class: "run-row", onclick: () => openRun(r) },
    h("span", { class: "run-when muted small" }, shortDay(r.started)),
    h("span", { class: "run-main" }, h("span", { class: "run-kind" }, t.kind), h("span", { class: "run-title" }, t.title)),
    h("span", { class: "run-stats muted small" }, `${r.llm_calls} model calls · ${failed} issue${failed === 1 ? "" : "s"}`),
    h("span", { class: "run-out" }, runBadges(r).map(([label, kind, spoken]) => badge(label, kind, spoken)))));
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
    postsSection(),
    learningsSection(),
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
  const badges = runBadges(r);
  const approval = approvalBlock(approvalOf(r));
  const list = h("div", null);
  // Only the step list is redrawn, so the checkbox keeps focus when toggled.
  const fill = (problemsOnly) => {
    const shown = r.events.filter((e) => !problemsOnly || isFailure(e));
    list.replaceChildren(...(shown.length
      ? stepGroups(shown).flatMap((g) => [h("h3", null, g.phase), h("ol", { class: "events" }, g.events.map(eventRow))])
      : [empty("No issues in this run.")]));
  };
  const box = h("input", { type: "checkbox", id: "problems", onchange: (e) => { setSessionFlag("problems", e.target.checked); fill(e.target.checked); } });
  box.checked = sessionFlag("problems");
  fill(box.checked);
  setHash("#run/" + r.run_id);
  show(drawer, [
    dialogHead("drawer-title", t.title, `${t.kind} · ${day(r.started)}`, drawer),
    h("div", { class: "dlg-body" },
      h("div", { class: "meta" }, badges.map(([label, kind, spoken]) => badge(label, kind, spoken)), badge(r.events.some(isFailure) ? "issues logged" : "no issues", r.events.some(isFailure) ? "warn" : "ok")),
      approval,
      h("dl", { class: "runsummary" },
        h("dt", null, "Started"), h("dd", null, when(r.started)),
        h("dt", null, "Settings"), h("dd", null, startText(r.start)),
        h("dt", null, "Ended"), h("dd", null, r.final || "(no final decision)"),
        h("dt", null, "Model calls"), h("dd", null, `${r.llm_calls} of ${r.events.length} steps`),
        h("dt", null, "Run id"), h("dd", { class: "mono" }, r.run_id)),
      h("label", { class: "toggle" }, box, " Only issues"),
      h("p", { class: "muted small" }, "Newest step first, in your time zone. Open a step for its raw input and output."),
      list),
  ]);
}

// ---------- plain-words steps ----------
// Each trace step is turned into one sentence by matching the harness's own wording. It is a convenience, not a
// source of truth: a step this does not recognise falls back to its raw text, and the raw input and output stay one
// click away. If the harness rewords a trace line, that step quietly falls back instead of showing something wrong.

const WHO = { writer: "Writer", critic: "Critic", planner: "Planner", analyst: "Analyst", harness: "The harness" };
const who = (e) => WHO[e.agent] || e.agent || "Step";
const shortModel = (m) => String(m || "").replace(/:free$/, "");
const CHECKS = { check_length: "Length check", check_banned: "Banned-phrase check", check_rate_cap: "Posting-limit check", check_duplicate: "Duplicate check" };
const TOOLS = { get_brand_brief: "the brand brief", get_learnings: "the saved learnings" };
const trim = (s, n) => (s.length > n ? s.slice(0, n) + "…" : s);

function startText(s) {
  const f = {};
  for (const m of String(s || "").matchAll(/(\w+)=(\w+)/g)) f[m[1]] = m[2];
  if (!("dry_run" in f)) return s || "";
  const bits = [f.dry_run === "True" ? "dry run (nothing is posted)" : "live run", f.approval === "True" ? "a person approves each post" : "approval off"];
  if (f.measure_only === "True") bits.push("measure only");
  if (f.min_score) bits.push(`critic bar ${f.min_score}/5`);
  return bits.join(" · ");
}

function reasonText(s) {
  if (/HTTP 429/.test(s)) return "the model was busy (rate limited)";
  if (/HTTP 404/.test(s)) return "the model is no longer available";
  if (/empty message/.test(s)) return "the model sent an empty reply";
  if (/time(d)? ?out/i.test(s)) return "the model took too long";
  return "the model call failed";
}

function criticScores(text) {
  const names = [["voice", "voice"], ["clarity", "clarity"], ["cta", "CTA"], ["policy_risk", "policy risk"]];
  const found = names.map(([k, label]) => [label, new RegExp(`"${k}"\\s*:\\s*(\\d)`).exec(text)]).filter(([, m]) => m);
  return found.length === names.length ? found.map(([label, m]) => `${label} ${m[1]}`).join(", ") : null;
}

// Returns { text, tone, meta }. tone is "ok", "error" or "declined": a decline is the system working, not an error.
function describe(e) {
  const i = e.summary_in || "";
  const o = e.summary_out || "";
  const base = { tone: e.ok ? "ok" : "error", meta: shortModel(e.model) };
  let m;

  if (e.kind === "llm_call") {
    if ((m = /^attempt (\d+)\/(\d+) failed: ([\s\S]*)$/.exec(o))) {
      return { ...base, text: `${who(e)} got no answer (try ${m[1]} of ${m[2]}): ${reasonText(m[3])}` };
    }
    if ((m = /^tokens in=(\d+) out=(\d+) finish=(\w+)/.exec(o))) {
      const meta = [shortModel(e.model), `${m[2]} tokens`].filter(Boolean).join(" · ");
      if (m[3] === "tool_calls") {
        const tool = /"name":\s*"([a-z_]+)"/.exec(o);
        return { ...base, meta, text: `${who(e)} asked for ${(tool && (TOOLS[tool[1]] || tool[1])) || "a tool"}` };
      }
      if (m[3] === "length") return { ...base, meta, text: `${who(e)}'s reply was cut off (the model ran out of room)` };
      if (e.agent === "writer") return { ...base, meta, text: "Writer drafted a post" };
      if (e.agent === "critic") {
        const s = criticScores(o);
        return { ...base, meta, text: s ? `Critic scored the draft: ${s}` : "Critic reviewed the draft" };
      }
      if (e.agent === "planner") return { ...base, meta, text: "Planner proposed the week's posts" };
      if (e.agent === "analyst") return { ...base, meta, text: "Analyst wrote a learning" };
    }
  }

  if (e.kind === "tool_call") {
    if (/^save_learning/.test(i)) return { ...base, text: "Saved a learning for the next plan" };
    if (/^get_brand_brief/.test(i)) return { ...base, text: `${who(e)} read the brand brief` };
    if (/^get_learnings/.test(i)) return { ...base, text: `${who(e)} read the saved learnings` };
    // The export swaps a real at:// address for "[post link]", so that form counts as a success too.
    if (/^publish_post/.test(i) && /^(at:\/\/|dryrun:\/\/|\[post link\])/.test(o)) {
      return { ...base, text: /dry_run=True/.test(i) ? "Post prepared (dry run: nothing was sent to Bluesky)" : "Post sent to Bluesky" };
    }
    if (/^publish_post/.test(i) && /^outcome unknown/.test(o)) {
      return { ...base, text: "Sending to Bluesky failed and the outcome is unknown, so it was not retried" };
    }
    if (/^get_metrics/.test(i)) {
      try {
        const c = JSON.parse(o);
        return { ...base, text: `Read the post's engagement: ${c.likes} likes, ${c.reposts} reposts, ${c.replies} replies` };
      } catch (_) { /* falls through to the raw text */ }
    }
  }

  if (e.kind === "guardrail") {
    const g = /^(publish re-check )?(\w+) \| /.exec(i);
    if (g) {
      const recheck = g[1] ? " (final re-check)" : "";
      if (g[2] === "require_approval" && !g[1]) {
        if (e.ok && /approval disabled/.test(o)) return { ...base, text: "Approval was switched off, so no one was asked" };
        if (e.ok) return { ...base, text: "A person approved this draft" };
        if (/did not approve/.test(o)) return { ...base, tone: "declined", text: "A person declined this draft" };
        if (/stdin closed/.test(o)) return { ...base, text: "No one answered (the terminal had no input)" };
        if (/^skipped/.test(o)) return { ...base, text: "Not asked: a code check had already failed" };
      }
      if (CHECKS[g[2]]) return { ...base, text: e.ok ? `${CHECKS[g[2]]}${recheck}: passed` : `${CHECKS[g[2]]}${recheck} failed: ${o}` };
    }
  }

  if (e.kind === "decision") {
    if ((m = /^backoff ([\d.]+)s, then retry (\d+)\/(\d+)/.exec(o))) {
      return { ...base, text: `${who(e)}: ${reasonText(i)}; waiting ${m[1]}s, then try ${m[2]} of ${m[3]}` };
    }
    if ((m = /^fallback to (.+)$/.exec(o))) return { ...base, text: `${who(e)}: ${shortModel(i.replace(/ gave up$/, ""))} gave up, switching to ${shortModel(m[1])}` };
    if (/^invalid Critique/.test(i) && (m = /^repair attempt: ([\s\S]*)$/.exec(o))) {
      return { ...base, text: `The critic's answer was not valid (${trim(m[1], 60)}); asking it to fix that` };
    }
    if (i === "repair of Critique") {
      if (/^repair succeeded/.test(o)) return { ...base, text: "The critic's answer was repaired" };
      if (/^repair failed/.test(o)) return { ...base, text: `The critic's answer could not be repaired: ${trim(o.replace(/^repair failed: /, ""), 80)}` };
    }
    if (/^invalid Draft/.test(i) && (m = /^repair attempt: ([\s\S]*)$/.exec(o))) {
      const len = /is (\d+) characters; the limit is (\d+)/.exec(m[1]);
      return { ...base, text: len ? `Draft was ${len[1]} characters (limit ${len[2]}); asking the writer to shorten it` : `Draft broke a rule (${trim(m[1], 80)}); asking the writer to fix it` };
    }
    if (i === "repair of Draft") {
      if (/^repair succeeded/.test(o)) return { ...base, text: "The repair worked" };
      if ((m = /^repair failed: ([\s\S]*)$/.exec(o))) {
        const len = /is (\d+) characters; the limit is (\d+)/.exec(m[1]);
        return { ...base, text: len ? `The repair failed: the draft was still ${len[1]} characters (limit ${len[2]})` : `The repair failed: ${trim(m[1], 80)}` };
      }
    }
    if ((m = /^inner loop \S+ attempt (\d+)(?: \| (.*))?$/.exec(i))) {
      const scores = m[2] ? m[2].replace(/policy_risk/, "policy risk").replace(/cta=/, "CTA=").replace(/=/g, " ") : "";
      if (/^passed/.test(o)) return { ...base, meta: scores, text: `Draft passed on attempt ${m[1]}` };
      if (/^below threshold/.test(o)) return { ...base, meta: scores, text: `Draft scored below the bar on attempt ${m[1]}; writing a revision` };
      if (/^failed: /.test(o)) return { ...base, text: `Gave up on the draft: ${trim(o.replace(/^failed: /, ""), 120)}` };
    }
    if (/^publish post_/.test(i)) {
      if (/^failed, outcome unknown/.test(o)) return { ...base, text: "Publishing failed and the outcome is unknown: the account should be checked before any retry" };
      if (/^published: /.test(o)) return { ...base, text: /dryrun:\/\//.test(o) ? "Dry run finished: nothing was sent to Bluesky" : "The post is live on Bluesky" };
      if (/^blocked: /.test(o)) return { ...base, tone: /did not approve/.test(o) ? "declined" : base.tone, text: `Publishing stopped: ${trim(o.replace(/^blocked: /, ""), 120)}` };
    }
    if (/^run_(post|outer)/.test(i) && /^start: /.test(o)) return { ...base, text: `Run started: ${startText(o)}` };
    if (/^daily guard/.test(i)) return { ...base, text: `Checked today's request allowance: ${o}` };
    if (/^measure candidates/.test(i)) return { ...base, text: `Checked which posts to measure: ${o}` };
    if (/^measure$/.test(i)) return { ...base, text: `Measuring: ${trim(o, 100)}` };
    if (/^check plan/.test(i)) return { ...base, text: `Plan check${/\(attempt (\d+)\)/.test(i) ? ` (attempt ${/\(attempt (\d+)\)/.exec(i)[1]})` : ""}: ${trim(o, 120)}` };
    if (i === "plan") return { ...base, text: `Plan saved: ${trim(o, 100)}` };
    if (i === "select post") return { ...base, text: `Picked the next post: ${trim(o, 100)}` };
    if (/^run_summary/.test(i)) return { ...base, text: "Run summary recorded" };
    if (/attempt budget/.test(i)) return { ...base, text: "Stopped: this call used up its request budget" };
  }

  return { ...base, text: trim(o || i, 140) };
}

function phaseOf(e) {
  const i = e.summary_in || "";
  if (e.kind === "guardrail") return /^require_approval\b/.test(i) ? "Human approval" : "Code checks";
  if (/^publish_post|^publish post_/.test(i)) return "Publishing";
  if (e.agent === "planner" || /^check plan/.test(i)) return "Planning";
  if (e.agent === "analyst" || /^get_metrics|^measure/.test(i)) return "Measuring";
  if (e.agent === "writer") return "Writing";
  if (e.agent === "critic" || /^inner loop/.test(i)) return "Critique";
  return "Run";
}

// Newest step first. Consecutive steps of one phase share a heading, so a revised draft shows as a fresh Writing group.
function stepGroups(events) {
  const groups = [];
  for (const e of [...events].reverse()) {
    const phase = phaseOf(e);
    if (!groups.length || groups[groups.length - 1].phase !== phase) groups.push({ phase, events: [] });
    groups[groups.length - 1].events.push(e);
  }
  return groups;
}

const TONE_CLASS = { ok: "pass", error: "fail", declined: "declined" };

function eventRow(e) {
  const d = describe(e);
  const out = e.summary_out || "";
  return h("li", null, h("details", { class: "event " + TONE_CLASS[d.tone] },
    h("summary", null,
      h("div", { class: "line1" },
        h("span", { class: "time" }, clock(e.ts)),
        h("span", { class: "what" }, d.text),
        d.tone === "error" ? badge("error", "bad") : null,
        d.tone === "declined" ? badge("declined", "warn") : null),
      d.meta ? h("div", { class: "out" }, d.meta) : null),
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
