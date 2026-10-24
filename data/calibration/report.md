# Critic calibration report

- Generated: 2026-10-24T09:23:34+00:00
- Run: `run_20261024_092334_1f3174` (13 upstream requests)
- Pass threshold: every score at least 4 (the harness's rule)
- Drafts: 10 in the file, 10 scored by the critic, 10 with your scores, 10 compared
- Scored by: poolside/laguna-s-2.1:free
- **Note:** some of your hand scores were adjusted after review, so this is not purely your own judgment: see adjustments.md (your first-pass scores are kept in drafts.first_pass.csv). The review used the critic's own rubric, so the comparison is partly circular.

## Mean absolute error per dimension

| Dimension | Mean absolute error | Critic minus you (bias) |
|---|---|---|
| voice | 1.00 | +0.20 |
| clarity | 1.30 | +0.70 |
| cta | 0.70 | +0.10 |
| policy_risk | 0.40 | +0.20 |

## Pass or fail agreement

- Agreement: **6 of 10** (60%)
- Critic passes a draft you would fail (too lenient): 4 (d03, d06, d08, d10)
- Critic fails a draft you would pass (too strict): 0

## The 3 biggest disagreements

Scores are voice / clarity / cta / policy_risk.

| Draft | Text | You | Critic | Critic's reasons where you differ |
|---|---|---|---|---|
| d08 | Your first loaf might come out dense, and that's fine: mistakes are part of bak… | 2 / 2 / 4 / 4 | 5 / 5 / 5 / 5 | **voice**: Warm, unhurried, and craft-proud tone with concrete baking detail and beginner-friendly reassurance.; **clarity**: Single idea about mistakes in baking, readable quickly, under 300 characters, and on the planned topic.; **cta**: One clear, low-pressure next step pointing to the Saturday class signup link.; **policy_risk**: No banned phrases, no unsupported claims, and all details align with the brief and planned post. |
| d07 | Guaranteed results: bake a perfect loaf in one Saturday class. Act now, we are … | 3 / 2 / 2 / 2 | 1 / 1 / 1 / 1 | **voice**: The draft uses aggressive, salesy language ('Guaranteed results', 'Act now', 'best bakery in town') that directly contradicts the warm, unhurried, craft-proud voice and violates multiple 'dont' rules.; **clarity**: The draft is about the Saturday beginner sourdough class but covers a promotional sales pitch instead of the planned angle (one concrete detail a beginner would notice), making it off-topic for the planned post.; **cta**: The call to action is pushy and misleading ('Act now') rather than a clear, low-pressure next step, and it is bundled with banned urgency language.; **policy_risk**: The draft contains multiple banned phrases and variants: 'Guaranteed results', 'Act now', and 'best bakery in town', plus a promise of 'perfect loaf in one Saturday class' that the business cannot back up, making it the riskiest possible score. |
| d10 | In class we cut a loaf open and look at the crumb together. It is the quickest … | 2 / 4 / 4 / 4 | 4 / 5 / 5 / 5 | **voice**: Warm, unhurried, and craft-proud tone fits the brief, though it lacks a concrete sensory detail like crust or crumb texture.; **clarity**: One clear idea about reading a loaf's crumb, readable in 5 seconds, under 300 characters, and directly about the planned post's topic.; **cta**: One specific, low-pressure next step (Saturday class link) that fits the post's goal of driving clicks.; **policy_risk**: No banned phrases, no unsupported claims, and all content aligns with the brief and planned post. |

## Every draft

| Draft | You | Critic | Pass (you / critic) | Scored by |
|---|---|---|---|---|
| d01 | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 | pass / pass | poolside/laguna-s-2.1:free |
| d02 | 1 / 1 / 1 / 1 | 1 / 2 / 1 / 1 | fail / fail | poolside/laguna-s-2.1:free |
| d03 | 5 / 3 / 4 / 4 | 5 / 5 / 5 / 5 | fail / pass | poolside/laguna-s-2.1:free |
| d04 | 5 / 4 / 5 / 5 | 5 / 5 / 5 / 5 | pass / pass | poolside/laguna-s-2.1:free |
| d05 | 1 / 3 / 2 / 1 | 1 / 2 / 1 / 1 | fail / fail | poolside/laguna-s-2.1:free |
| d06 | 4 / 3 / 4 / 5 | 5 / 5 / 5 / 5 | fail / pass | poolside/laguna-s-2.1:free |
| d07 | 3 / 2 / 2 / 2 | 1 / 1 / 1 / 1 | fail / fail | poolside/laguna-s-2.1:free |
| d08 | 2 / 2 / 4 / 4 | 5 / 5 / 5 / 5 | fail / pass | poolside/laguna-s-2.1:free |
| d09 | 3 / 2 / 2 / 5 | 1 / 1 / 1 / 5 | fail / fail | poolside/laguna-s-2.1:free |
| d10 | 2 / 4 / 4 / 4 | 4 / 5 / 5 / 5 | fail / pass | poolside/laguna-s-2.1:free |
