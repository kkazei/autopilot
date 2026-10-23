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
