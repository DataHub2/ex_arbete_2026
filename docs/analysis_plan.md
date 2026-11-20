# Analysis plan

This was written before i did final run. The final split has not yet  been run or tuned on.
Anything we decisded here can be seen as exploritory.


## What is run
- Final split: 30 questions, 23 in scope and 7 out of  the scope.
- Variants: A, B, B_rules, B_refusal, B_citations. One run each, temperature 0.
- Code, prompts, judge (v2, median of 3 votes) and test set are maybe getting froze from the date below 
  2026-11-20.

## Primary comparison
A against B on the 23 in scope questions, and we will try to see it from a correctnous perspectiv.

And in this case correctnous needs to be handled by hand, and the manual grade is the primary measure.
The in this case the judge is a second measure. Its agreement with the manual grading
(Cohen's kappa) is reported on final.

A and B should be graded by hand in a file, mixed in random order with the variant
hidden (`blind_template` in `src/evaluate.py`). This blinding is in a way partial: B's
citations maybe still give the variant away. This is reported as a limitation in the analasis we made.

## Secondary measures
- Groundedness (in scope).
- Out of scope (7 questions): refusal, and to see if a rule was invented.
- Over refusal: in scope answers that gives us the refusal sentence.
- citations (B and B_citations): should both be cited [Document > Section] label s
  that match a retriefed excerpt.
- Retrieval: recall@k and MRR. Should be the same in  all variants, and this is beacuse B only changes the prompt.

## How "B is better" is decided
B is better if it has more correct answers than A on the in scop questions,
without more over refusal and also without more added invented rules. So that we can see a good and fair measure.

With n = 23 the result is a direction, not a proof alone. Results get reported for each question and for each question type. A paird exact test (McNemar) on correct /
not correct is reported as an indication only.

## Ablation
B_rules, B_refusal and B_citations are compared with the A in the same way, to show us witch part of b is makes a difference. They are scored by the judge only,
so these results carry the judge's caveat.

## Conventions decided from dev
- Gold chunks are the mini sufficient set to the system. A Recall can undercount when
  another set of chunks is also enough and (seen onn dev_03 and dev_07). Such case should be reported as a known limittaation, the gold sets are not changed.

- dev_02's gold answer is left as it is. It is on the dev split and does not
  affect final.

## Not allowed after the final run
Changing of the prompts, the judgeing system, the test set and or this plan. Anything added later will then be added as a
is labelled as exploratory.
