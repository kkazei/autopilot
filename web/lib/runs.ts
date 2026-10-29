import type { RunRow } from "./db";
import { describeRun, runKind, type RunStory, type RunSummary } from "./parse";

/** describeRun for a row from db.recentRuns, which carries only the events the description needs. */
export function rowStory(r: RunRow, topic?: (postId: string) => string | undefined, now?: number): RunStory {
  let summary: RunSummary | null = null;
  try {
    summary = r.summary ? (JSON.parse(r.summary.summary_out) as RunSummary) : null;
  } catch { /* a cut summary reads as none */ }
  return describeRun({ kind: r.first ? runKind([r.first]) : "run", summary, publish: r.publish, last: r.last, updatedAt: r.updated_at }, topic, now);
}

/** Post id to topic, for "“bake result” is on Bluesky" instead of an id. */
export const topicLookup = (posts: { id: string; topic: string }[]) => {
  const map = new Map(posts.map((p) => [p.id, p.topic]));
  return (id: string) => map.get(id);
};
