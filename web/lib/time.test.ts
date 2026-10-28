import assert from "node:assert/strict";
import { test } from "node:test";

import { dateLabel, fmtDay, fmtHourMinute, fmtStamp, fmtTime, validTimeZone, zoneLabel } from "./time.ts";

const ISO = "2026-10-26T14:05:24.000Z";

test("formats an instant in the viewer's zone, 24-hour", () => {
  assert.equal(fmtTime(ISO, "UTC"), "14:05:24");
  assert.equal(fmtTime(ISO, "Asia/Manila"), "22:05:24");
  assert.equal(fmtStamp(ISO, "Asia/Manila"), "Oct 26, 22:05");
  assert.equal(fmtHourMinute("2026-10-28T06:17:00Z", "Asia/Manila"), "14:17");
  assert.equal(fmtDay("2026-10-28T20:00:00Z", "Asia/Manila"), "Thu 29", "late UTC evening is already tomorrow in Manila");
});

test("labels the zone so times are never ambiguous", () => {
  assert.equal(zoneLabel("UTC"), "UTC");
  assert.equal(zoneLabel("Asia/Manila"), "GMT+8");
});

test("rejects a zone Intl does not know, falling back to UTC", () => {
  assert.equal(validTimeZone("Asia/Manila"), "Asia/Manila");
  assert.equal(validTimeZone("Not/AZone"), "UTC");
  assert.equal(validTimeZone(undefined), "UTC");
});

test("plan days are calendar dates and never shift", () => {
  assert.equal(dateLabel("2026-10-28"), "Wed 28");
});
