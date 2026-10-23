# Critic calibration report

- Generated: 2026-10-23T11:40:19+00:00
- Run: `run_20261023_114019_557734` (11 upstream requests)
- Pass threshold: every score at least 4 (the harness's rule)
- Drafts: 10 in the file, 7 scored by the critic, 10 with your scores, 7 compared
- Scored by: poolside/laguna-s-2.1:free
- **Stopped early:** LLMBudgetExceeded: critic: upstream attempt budget of 4 used up
- **Note:** some of your hand scores were adjusted after review, so this is not purely your own judgment: see adjustments.md (your first-pass scores are kept in drafts.first_pass.csv). The review used the critic's own rubric, so the comparison is partly circular.

## Mean absolute error per dimension

| Dimension | Mean absolute error | Critic minus you (bias) |
|---|---|---|
| voice | 0.43 | -0.14 |
| clarity | 1.29 | +0.43 |
| cta | 0.57 | +0.00 |
| policy_risk | 0.29 | +0.00 |

## Pass or fail agreement

- Agreement: **5 of 7** (71%)
- Critic passes a draft you would fail (too lenient): 2 (d03, d06)
- Critic fails a draft you would pass (too strict): 0

## The 3 biggest disagreements

Scores are voice / clarity / cta / policy_risk.

| Draft | Text | You | Critic | Critic's reasons where you differ |
|---|---|---|---|---|
| d07 | Guaranteed results: bake a perfect loaf in one Saturday class. Act now, we are … | 3 / 2 / 2 / 2 | 1 / 1 / 1 / 1 | **voice**: The draft uses aggressive, salesy language ('Guaranteed results', 'Act now', 'best bakery in town') that directly contradicts the warm, unhurried, craft-proud voice and triggers multiple banned phrases.; **clarity**: The draft is about the Saturday beginner sourdough class but fails to deliver the planned angle of 'one concrete detail a beginner would notice' and instead makes vague promises.; **cta**: The call to action is pushy and misleading, using 'Act now' which is a banned phrase, rather than a clear, low-pressure next step.; **policy_risk**: The draft contains multiple banned phrases ('Guaranteed results', 'Act now', 'best bakery in town') and makes unbacked claims ('bake a perfect loaf in one Saturday class') that the brief cannot support, resulting in the lowest risk score. |
| d03 | Flour on the counter, the smell of the oven, a crust you can hear when you tear… | 5 / 3 / 4 / 4 | 5 / 5 / 5 / 5 | **clarity**: One clear idea about a Saturday morning at the bakery, readable in 5 seconds and under 300 characters.; **cta**: One specific, low-pressure next step with the class link.; **policy_risk**: No banned phrases, no unsupported claims, and all details align with the brief and planned post. |
| d06 | Book your first class with us and a free sample loaf comes home with you. Come … | 4 / 3 / 4 / 5 | 5 / 5 / 5 / 5 | **voice**: Warm, unhurried, and craft-proud tone with no off-tone language or banned phrases.; **clarity**: One clear idea about the free sample loaf hook, readable in 5 seconds and under 300 characters.; **cta**: One specific, low-pressure next step pointing to the class booking link. |

## Every draft

| Draft | You | Critic | Pass (you / critic) | Scored by |
|---|---|---|---|---|
| d01 | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 | pass / pass | poolside/laguna-s-2.1:free |
| d02 | 1 / 1 / 1 / 1 | 1 / 2 / 1 / 1 | fail / fail | poolside/laguna-s-2.1:free |
| d03 | 5 / 3 / 4 / 4 | 5 / 5 / 5 / 5 | fail / pass | poolside/laguna-s-2.1:free |
| d04 | 5 / 4 / 5 / 5 | 5 / 5 / 5 / 5 | pass / pass | poolside/laguna-s-2.1:free |
| d05 | 1 / 3 / 2 / 1 | 1 / 1 / 1 / 1 | fail / fail | poolside/laguna-s-2.1:free |
| d06 | 4 / 3 / 4 / 5 | 5 / 5 / 5 / 5 | fail / pass | poolside/laguna-s-2.1:free |
| d07 | 3 / 2 / 2 / 2 | 1 / 1 / 1 / 1 | fail / fail | poolside/laguna-s-2.1:free |
| d08 | 2 / 2 / 4 / 4 | - | - | not scored: LLMBudgetExceeded: critic: upstream attempt budget of 4 used up |
| d09 | 3 / 2 / 2 / 5 | - | - | not attempted: the run stopped earlier |
| d10 | 2 / 4 / 4 / 4 | - | - | not attempted: the run stopped earlier |

## Not scored

- d08: not scored: LLMBudgetExceeded: critic: upstream attempt budget of 4 used up
- d09: not attempted: the run stopped earlier
- d10: not attempted: the run stopped earlier
