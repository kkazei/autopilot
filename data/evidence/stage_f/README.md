# Stage F evidence: a real plan cites a real learning (Oct 25)

**Question:** does the planner, on a real free model, use a learning that has engagement signal, and does the
harness's own plan check accept the citation?

**The learning.** `post_fa922d48` (live since 09:27 UTC) was measured live at 11:29 UTC by `run_outer --measure-only`
(`data/runs/run_20261025_112952_3635b0.json`): 4 likes, 0 reposts, 0 replies, so the analyst model wrote an insight
(it suggests a clearer call to action). **The likes came from people the builder knows, not an organic audience**, so
this shows the measure, learn and cite loop working on real data, not a real audience signal. The analyst's insight
also reads more into 4 likes on one post than they support.

**How it was run.** Planner only, to save free quota for a live post: the real `agents.planner.plan_week` with the
real OpenRouter client, the learnings fetched through the harness (`fetch_learnings`, which includes the one above),
and the harness's `check_plan`, which rejects a plan that does not cite a learning with signal. A scratch copy of
`data/` was used, so nothing was written to `data/` and nothing was published. The write, critique and publish half
of `run_outer` was not repeated here; it ran on real models in stage B and in the live posts.

Criteria, fixed before the run: the plan check passes with `[learning:post_fa922d48]` in the rationale; the plan
visibly uses the learning; nothing is published.

| Run | Budget | Result |
|---|---|---|
| `run_20261025_114552_876bb2.json` | 4 | **Failed cleanly, no plan.** poolside 429, then a 120 s timeout, then a local DNS failure (`getaddrinfo failed`), then flint truncated at 4,096 tokens; the budget stopped the run (`LLMBudgetExceeded`). |
| `run_20261025_115028_61726b.json` | 5 | **Passed.** After poolside and flint failed, nemotron-3-ultra answered (4 requests). `check plan (attempt 1) \| ok`; the rationale cites `[learning:post_fa922d48]` and says post p2 "leads with the concrete 'folding the dough' action" because of it. |

**Limits.** The use of the learning is shallow (one post's framing). Some planned topics go beyond the brief ("The role
of steam in baking", "feeding schedule"); angles follow the focus-only rule from PR #15, but topics are still trusted
as fact by the writer and critic. These 8 requests ran from a scratch folder, so `quota.run_cap` does not count them.
`mcp_calls.jsonl` is the tool call log for both runs (`get_learnings` by the harness, `get_brand_brief` by the planner).
