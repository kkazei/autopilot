# Critic calibration report

- Generated: 2026-10-29T07:45:55+00:00
- Run: `run_20261029_074555_dd4ccb` (10 upstream requests)
- Pass threshold: every score at least 4 (the harness's rule)
- Drafts: 10 in the file, 10 scored by the critic, 10 with your scores, 10 compared
- Scored by: cohere/north-mini-code:free
- **Note:** some of your hand scores were adjusted after review, so this is not purely your own judgment: see adjustments.md (your first-pass scores are kept in drafts.first_pass.csv). The review used the critic's own rubric, so the comparison is partly circular.

## Mean absolute error per dimension

| Dimension | Mean absolute error | Critic minus you (bias) |
|---|---|---|
| voice | 1.30 | -0.10 |
| clarity | 0.90 | -0.70 |
| cta | 0.90 | -0.10 |
| policy_risk | 0.70 | -0.10 |

## Pass or fail agreement

- Agreement: **8 of 10** (80%)
- Critic passes a draft you would fail (too lenient): 0
- Critic fails a draft you would pass (too strict): 2 (d01, d04)

## The 3 biggest disagreements

Scores are voice / clarity / cta / policy_risk.

| Draft | Text | You | Critic | Critic's reasons where you differ |
|---|---|---|---|---|
| d04 | We're a neighborhood sourdough bakery that teaches small, hands-on weekend brea… | 5 / 4 / 5 / 5 | 2 / 3 / 2 / 5 | **voice**: The tone is generic and lacks the warm, unhurried, craft-proud language called for.; **clarity**: It presents two competing messages—a brand description and an invitation—rather than a single focused idea.; **cta**: Only a URL is provided without a clear, low‑pressure next step. |
| d08 | Your first loaf might come out dense, and that's fine: mistakes are part of bak… | 2 / 2 / 4 / 4 | 4 / 1 / 5 / 2 | **voice**: The tone is warm and unhurried but lacks explicit craft‑proud language.; **clarity**: It mixes reassurance, a reader question, and a class invitation, making it cluttered with multiple ideas.; **cta**: It provides a single, low‑pressure next step to sign up for the Saturday class.; **policy_risk**: It includes unsupported factual claims: "Your first loaf might come out dense" and "Saturday's small class is a friendly place to make a few". |
| d10 | In class we cut a loaf open and look at the crumb together. It is the quickest … | 2 / 4 / 4 / 4 | 5 / 5 / 5 / 3 | **voice**: Uses warm, inclusive language and craft‑proud description, matching the brief's voice.; **clarity**: One clear idea about reading crumb, under 300 chars, matches topic, CTA separate.; **cta**: Specific low‑pressure next step (Saturday class signup) aligns with goal.; **policy_risk**: "It is the quickest way to see what the dough has been through." is an unsupported factual claim. |

## Every draft

| Draft | You | Critic | Pass (you / critic) | Scored by |
|---|---|---|---|---|
| d01 | 5 / 5 / 5 / 5 | 5 / 3 / 5 / 5 | pass / fail | cohere/north-mini-code:free |
| d02 | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 2 | fail / fail | cohere/north-mini-code:free |
| d03 | 5 / 3 / 4 / 4 | 5 / 3 / 5 / 5 | fail / fail | cohere/north-mini-code:free |
| d04 | 5 / 4 / 5 / 5 | 2 / 3 / 2 / 5 | pass / fail | cohere/north-mini-code:free |
| d05 | 1 / 3 / 2 / 1 | 1 / 1 / 1 / 2 | fail / fail | cohere/north-mini-code:free |
| d06 | 4 / 3 / 4 / 5 | 5 / 3 / 5 / 5 | fail / fail | cohere/north-mini-code:free |
| d07 | 3 / 2 / 2 / 2 | 1 / 1 / 1 / 1 | fail / fail | cohere/north-mini-code:free |
| d08 | 2 / 2 / 4 / 4 | 4 / 1 / 5 / 2 | fail / fail | cohere/north-mini-code:free |
| d09 | 3 / 2 / 2 / 5 | 1 / 1 / 2 / 5 | fail / fail | cohere/north-mini-code:free |
| d10 | 2 / 4 / 4 / 4 | 5 / 5 / 5 / 3 | fail / fail | cohere/north-mini-code:free |
