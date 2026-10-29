# Adjustments to the hand scores

`drafts.first_pass.csv` holds the user's own scores, exactly as first entered. `drafts.csv` is what the calibration run
compares against. They differ in six numbers, all changed by Claude at the user's request ("decide for me") after a
review against the critic's rubric. The rule used: change a number only where it contradicts the rubric's own wording;
leave every matter of taste alone. Any report that cites these scores should say they were adjusted after review.

| Draft | Score | First pass | Now | Reason (rubric wording) |
|---|---|---|---|---|
| d05 | voice | 3 | 1 | 1 = "breaks the dont list": scarcity pressure and all-caps "TODAY". |
| d06 | cta | 1 | 4 | 1 = "no action, or pushy"; the draft has one clear, gentle next step. |
| d06 | policy | 1 | 5 | The free loaf is in the row's own topic; the rest is from the brief. |
| d07 | policy | 3 | 2 | A banned phrase caps policy at 2 or lower; it has three. |
| d08 | policy | 2 | 4 | 2 needs a banned phrase, health claim, pressure or promise; none present. One point off for "might come out dense". |
| d10 | clarity | 1 | 4 | 1 = vague, cluttered or off topic; it is one idea on its topic. |

No change flips a pass or fail at the threshold of 4: the same two drafts (d01, d04) pass before and after, so the
pass/fail agreement figure is unaffected; only the mean absolute error and bias move.

Left as the user scored them (taste, not rubric): d08 voice 2 and clarity 2, d10 voice 2, d09, d03, d01, d02, d04.

## Second revision (Oct 29, by the user)

The user re-scored all ten drafts on Oct 29, **after seeing two critic reports** on them (laguna, and
north-mini-code's run `run_20261029_074555_dd4ccb`). The previous `drafts.csv` is in git history; the original first
pass stays in `drafts.first_pass.csv`. The reasons below are the user's own, condensed from their write-up.

| Draft | Changed | Reason (the user's) |
|---|---|---|
| d01 | nothing | Welcoming, no pressure, clear invitation and link, no unrealistic promise. |
| d02 | clarity 1 to 4, policy 1 to 2 | Unprofessional (caps, hashtags) but readers understand it promotes sourdough. "The best thing you will ever eat" is an unsupported superlative: a trust concern, not a serious violation. |
| d03 | clarity 3 to 4, policy 4 to 5 | The sensory description is vivid and understandable; no obviously misleading claim. |
| d04 | clarity 4 to 5, cta 5 to 4 | Clearly says what the bakery does; "Come and see for yourself" is an invitation, not a direct ask to book. |
| d05 | clarity 3 to 5 | Very easy to understand. Clear is not the same as good: cta stays 2 (pressure, fear of regret), policy 1 (the scarcity claim must be true). |
| d06 | clarity 3 to 4, cta 4 to 5 | The free loaf is a concrete benefit and the booking step is clear; could be a little more concise. |
| d07 | voice 3 to 2, clarity 2 to 4, policy 2 to 1 | Understandable, but "a perfect loaf in one class" is unrealistic and "best in town" cannot be substantiated. |
| d08 | voice 2 to 4, clarity 2 to 4, policy 4 to 5 | Empathetic, reassures beginners, invites readers to share; no guaranteed results. cta stays 4: it invites engagement more than booking. |
| d09 | voice 3 to 1, clarity 2 to 1, cta 2 to 1 | Fragmented and confusing; "a link exists" is not a reason to click. Policy stays 5: poor writing is not a policy violation. |
| d10 | voice 2 to 3, policy 4 to 5 | Concrete and informative, more instructional than distinctive; a grounded educational statement with no guarantee. |

Effect at the threshold of 4: d03, d06 and d08 now pass (they failed before); d01 and d04 still pass; d10 still fails.

**Definition note (Claude, Oct 29).** These clarity scores rate how easy a draft is to understand. The critic's rubric
(`agents/critic.py`) rates focus: 5 is one idea about the planned topic, 3 is a main idea plus a competing message
(its example: a question to the reader as well as the link), 1 is vague, cluttered or two messages at once. So the
two disagree by definition on drafts like d02, d05, d07 and d08, and a calibration against these scores measures that
difference as well as the critic. Two policy scores also sit apart from the rubric's fact check, which counts
comparisons and sensory details beyond the brief as unsupported claims: d10's "the quickest way to see what the dough
has been through" and d03's "a crust you can hear". Re-graded without new model calls, laguna agrees with these scores
on 8 of 10 and north-mini-code on 5 of 10 (north fails d01, d03, d04, d06 and d08, mostly on clarity).

## Third revision: clarity re-scored for focus (Oct 29, by the user)

After the definition note above, the user adopted focus as the meaning of clarity ("one bake, one technique or one class
detail per post" is the brief's own rule) and re-scored only the clarity column, with anchors 5 = one idea about the
planned topic, readable in 5 seconds; 3 = a main idea plus something competing with it; 1 = vague, cluttered, or two
messages at once (2 and 4 in between). The user's reasons:

| Draft | Clarity | Reason (the user's) |
|---|---|---|
| d01 | 5 to 5 | One idea: trying a first sourdough class; nothing competes. |
| d02 | 4 to 1 | The superlative, hashtag clutter and "Come or don't" pull in different directions: readable, not focused. |
| d03 | 4 to 4 | The sensory details build one picture; the class invitation adds a secondary promotional message. |
| d04 | 5 to 4 | The bakery introduction and the class offer fit, but the "how real bread is made" question adds an angle. |
| d05 | 5 to 5 | One purpose, booking Saturday's class; the pressure is a tone and trust problem, not clarity. |
| d06 | 4 to 3 | The free loaf is the hook, but the mistakes reassurance and the class invitation split the focus. |
| d07 | 4 to 1 | A guarantee, a "best bakery" claim and an urgent instruction compete. |
| d08 | 4 to 5 | The dense first loaf, the reassurance and the question all support one idea: mistakes are part of learning. |
| d09 | 1 to 1 | Vague, disconnected fragments with no main idea. |
| d10 | 4 to 3 | One technique (reading the crumb), then a pivot to promoting the class. |

Policy: d10 5 to 4 ("quickest" is an absolute comparison with no basis; low stakes, one point). d03's "a crust you can
hear" keeps 5: figurative sensory language, not a verifiable claim.

Pass at the threshold of 4: d01, d03, d04, d08. Re-graded without new model calls: laguna 7 of 10 (too lenient on d06
and d10, too strict on d08), north-mini-code 6 of 10 (never too lenient; too strict on d01, d03, d04 and d08).

**Note (Claude).** The anchors given to the user for this round left out two clauses of the rubric in
`agents/critic.py`: "the closing call to action alone is not a second idea", and its example of a 3, "a question to the
reader as well as the link". The scores above follow the shortened anchors; d03, d06, d08 and d10 are the drafts where
the full rubric reads differently.
