# Critic calibration report

- Generated: 2026-10-29T08:02:55+00:00
- Run: `run_20261029_080255_28579e` (8 upstream requests)
- Pass threshold: every score at least 4 (the harness's rule)
- Drafts: 10 in the file, 5 scored by the critic, 10 with your scores, 5 compared
- Scored by: nvidia/nemotron-3.5-super-vl:free
- **Stopped early:** LLMUnavailable: all 1 models failed
- **Note:** some of your hand scores were adjusted after review, so this is not purely your own judgment: see adjustments.md (your first-pass scores are kept in drafts.first_pass.csv). The review used the critic's own rubric, so the comparison is partly circular.

## Mean absolute error per dimension

| Dimension | Mean absolute error | Critic minus you (bias) |
|---|---|---|
| voice | 0.00 | +0.00 |
| clarity | 1.00 | -0.20 |
| cta | 0.60 | +0.20 |
| policy_risk | 1.20 | -0.80 |

## Pass or fail agreement

- Agreement: **3 of 5** (60%)
- Critic passes a draft you would fail (too lenient): 0
- Critic fails a draft you would pass (too strict): 2 (d01, d03)

## The 3 biggest disagreements

Scores are voice / clarity / cta / policy_risk.

| Draft | Text | You | Critic | Critic's reasons where you differ |
|---|---|---|---|---|
| d05 | Only 2 spots left for Saturday's class!! Book TODAY before they're gone, you wi… | 1 / 5 / 2 / 1 | 1 / 2 / 1 / 2 | **clarity**: The Saturday beginner sourdough class is mentioned, but the draft is mainly about scarcity pressure and regret rather than the class topic or its required angle of one concrete detail a beginner would notice.; **cta**: The call to action is pushy and uses urgency pressure ('Book TODAY before they're gone, you will regret it if you wait') instead of a low-pressure next step.; **policy_risk**: It uses urgency pressure ('Only 2 spots left... before they're gone') and makes an unsupported factual claim ('Only 2 spots left') that does not appear in the brief or the planned post topic. |
| d03 | Flour on the counter, the smell of the oven, a crust you can hear when you tear… | 5 / 4 / 4 / 5 | 5 / 5 / 5 / 3 | **clarity**: At 212 characters it covers one idea—the sights and smells of a Saturday morning at the bakery—and ends with a single low-pressure CTA link.; **cta**: It offers one clear, low-pressure next step: visiting the class signup URL whenever the reader is ready.; **policy_risk**: It includes an unsupported sensory claim not in the brief or the 'sights and smells' topic: 'a crust you can hear when you tear it'. |
| d01 | Saturday's beginner sourdough class starts with flour on your hands and no pres… | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 3 | **policy_risk**: The claim starts with flour on your hands is an unsupported process detail not found in the brief or the planned post topic. |

## Every draft

| Draft | You | Critic | Pass (you / critic) | Scored by |
|---|---|---|---|---|
| d01 | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 3 | pass / fail | nvidia/nemotron-3.5-super-vl:free |
| d02 | 1 / 1 / 1 / 2 | 1 / 1 / 1 / 1 | fail / fail | nvidia/nemotron-3.5-super-vl:free |
| d03 | 5 / 4 / 4 / 5 | 5 / 5 / 5 / 3 | pass / fail | nvidia/nemotron-3.5-super-vl:free |
| d04 | 5 / 4 / 4 / 5 | 5 / 5 / 5 / 5 | pass / pass | nvidia/nemotron-3.5-super-vl:free |
| d05 | 1 / 5 / 2 / 1 | 1 / 2 / 1 / 2 | fail / fail | nvidia/nemotron-3.5-super-vl:free |
| d06 | 4 / 3 / 5 / 5 | - | - | not scored: LLMUnavailable: all 1 models failed |
| d07 | 2 / 1 / 2 / 1 | - | - | not attempted: the run stopped earlier |
| d08 | 4 / 5 / 4 / 5 | - | - | not attempted: the run stopped earlier |
| d09 | 1 / 1 / 1 / 5 | - | - | not attempted: the run stopped earlier |
| d10 | 3 / 3 / 4 / 4 | - | - | not attempted: the run stopped earlier |

## Not scored

- d06: not scored: LLMUnavailable: all 1 models failed
- d07: not attempted: the run stopped earlier
- d08: not attempted: the run stopped earlier
- d09: not attempted: the run stopped earlier
- d10: not attempted: the run stopped earlier
