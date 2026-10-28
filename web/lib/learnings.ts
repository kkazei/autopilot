// Learnings grouped by the post they are about, with the post itself (text, time, link, scores) from the approved
// log. Posts published before the weekly plan existed are not in the plan state, so the log is the source for them.

export type LearningRow = { run_id: string; post_id: string; metrics: Record<string, number>; insight: string };
export type ApprovedPost = { run_id?: string; post_id?: string; status?: string; text?: string; uri?: string; posted_at?: string; dry_run?: boolean; scores?: Record<string, number> };
export type PlannedPost = { id: string; topic: string; goal: string; angle: string };

export const NOT_ENOUGH = "Not enough data yet"; // harness/measure.py NOT_ENOUGH_DATA_INSIGHT starts with this

export type Measurement = { run_id: string; at: string | null; metrics: Record<string, number>; insight: string; thin: boolean };
export type PostLearnings = {
  post_id: string; text: string | null; posted_at: string | null; bluesky: string | null; topic: string | null; goal: string | null;
  scores: Record<string, number> | null; measurements: Measurement[]; lesson: Measurement | null; latest: Measurement;
};

/** run_20261026_101942_a284db -> 2026-10-26T10:19:42Z: when the measuring run started. */
export function runTime(runId: string): string | null {
  const m = /^run_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/.exec(runId);
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z` : null;
}

/** at://did:plc:abc/app.bsky.feed.post/xyz -> https://bsky.app/profile/did:plc:abc/post/xyz */
export function blueskyUrl(uri: string | undefined): string | null {
  const m = /^at:\/\/(did:[a-z]+:[A-Za-z0-9._:%-]+)\/app\.bsky\.feed\.post\/([A-Za-z0-9]+)$/.exec(uri ?? "");
  return m ? `https://bsky.app/profile/${m[1]}/post/${m[2]}` : null;
}

export function groupLearnings(learnings: LearningRow[], approved: ApprovedPost[], planned: PlannedPost[]): PostLearnings[] {
  const published = new Map<string, ApprovedPost>();
  for (const r of approved) {
    if (r.dry_run || !r.post_id || (r.status ?? "published") !== "published") continue;
    published.set(r.post_id, r);
  }
  const plan = new Map(planned.map((p) => [p.id, p]));
  const byPost = new Map<string, Measurement[]>();
  for (const l of learnings) {
    const list = byPost.get(l.post_id) ?? [];
    list.push({ run_id: l.run_id, at: runTime(l.run_id), metrics: l.metrics, insight: l.insight, thin: l.insight.startsWith(NOT_ENOUGH) });
    byPost.set(l.post_id, list);
  }
  const groups: PostLearnings[] = [...byPost].map(([post_id, measurements]) => {
    measurements.sort((a, b) => (a.at ?? "").localeCompare(b.at ?? ""));
    const post = published.get(post_id);
    const p = plan.get(post_id);
    return {
      post_id, text: post?.text ?? null, posted_at: post?.posted_at ?? null, bluesky: blueskyUrl(post?.uri),
      topic: p?.topic ?? null, goal: p?.goal ?? null, scores: post?.scores ?? null, measurements,
      lesson: measurements.findLast((m) => !m.thin) ?? null, latest: measurements.at(-1)!,
    };
  });
  return groups.sort((a, b) => (b.posted_at ?? "").localeCompare(a.posted_at ?? ""));
}
