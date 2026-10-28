import assert from "node:assert/strict";
import { test } from "node:test";

import { blueskyUrl, groupLearnings, runTime } from "./learnings.ts";

const thin = "Not enough data yet: under 2 likes, reposts and replies in total, so this post is not engagement evidence.";

test("groups learnings under their post, with the post's own text, link and topic", () => {
  const groups = groupLearnings(
    [
      { run_id: "run_20261023_103918_bfa247", post_id: "post_a", metrics: { likes: 0, reposts: 0, replies: 0 }, insight: thin },
      { run_id: "run_20261026_101942_a284db", post_id: "post_a", metrics: { likes: 3, reposts: 1, replies: 0 }, insight: "Sensory moments work." },
      { run_id: "run_20261027_061256_1c33ca", post_id: "post_b", metrics: { likes: 3, reposts: 2, replies: 1 }, insight: "Gentle tone works." },
    ],
    [
      { post_id: "post_a", status: "pending", text: "draft" },
      { post_id: "post_a", status: "published", text: "The class starts…", uri: "at://did:plc:abc123/app.bsky.feed.post/3xyz", posted_at: "2026-10-23T07:13:00Z" },
      { post_id: "post_b", text: "Feeding a starter…", posted_at: "2026-10-26T14:05:00Z", uri: "bad" },
      { post_id: "post_b", status: "published", dry_run: true, text: "dry" },
    ],
    [{ id: "post_b", topic: "starter maintenance", goal: "engagement", angle: "x" }],
  );
  assert.deepEqual(groups.map((g) => g.post_id), ["post_b", "post_a"], "newest post first");
  const a = groups[1];
  assert.equal(a.text, "The class starts…");
  assert.equal(a.bluesky, "https://bsky.app/profile/did:plc:abc123/post/3xyz");
  assert.equal(a.topic, null, "published before the plan existed");
  assert.equal(a.measurements.length, 2);
  assert.equal(a.lesson?.insight, "Sensory moments work.", "the lesson is the latest real insight, not the thin one");
  assert.equal(a.latest.metrics.likes, 3);
  assert.equal(groups[0].topic, "starter maintenance");
  assert.equal(groups[0].bluesky, null, "a malformed uri gives no link");
  assert.equal(groups[0].text, "Feeding a starter…", "a row without status is a published post");
});

test("a post with only a thin measurement has no lesson yet", () => {
  const [g] = groupLearnings([{ run_id: "run_20261028_061700_x", post_id: "p", metrics: {}, insight: thin }], [], []);
  assert.equal(g.lesson, null);
  assert.equal(g.latest.thin, true);
  assert.equal(runTime("run_20261028_061700_x"), "2026-10-28T06:17:00Z");
  assert.equal(blueskyUrl(undefined), null);
});
