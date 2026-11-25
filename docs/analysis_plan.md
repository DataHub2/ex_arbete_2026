# Analysis plan

We wrote this before the final run. We have not looked at the final questions.
Things that are not in this plan are extra (exploratory).

## What we run

- 30 final questions. 23 are in scope, 7 are out of scope.
- 5 variants: A, B, B_rules, B_refusal, B_citations. We run each one one time, temperature 0.
- From 2026-11-20 we do not change the code, the prompts, the judge (v2, 3 votes)
  or the questions.

## The main test

We compare  the A and B on the 23 in scope questions. We check if the answers are correct.

We grade this by hand. Our hand grades are the main result.
The judge is the second result. We show how much it agrees with us (kappa).

A and B are mixed in one file, so we can not see which is which (`blind_template`).
But B shows sources, so we may still guess. We write this as a limitation.

## How we grade

- Two people grade all answers alone. They do not look at each other or at the judge.
- If they do not agree, a third person decides.
- We show how often the two did not agree, before the third person decides.
- Nobody opens `key_DO_NOT_OPEN.json` before all grading is done.

## Other things we look at

- Groundedness for in scope questions.
- The 7 out of scope questions: does it say "I don't know"? Does it make up a rule?
- Does it say "I don't know" when it should answer?
- B and B_citations: how many of the sources it shows match the text it got?
- Search: recall@k and MRR. These should be the same for all variants.

## When is B better?

B is better if it gets more correct answers than A, but does not say "I don't know"
more often and does not make up more rules.

23 questions is not many. So the result shows a direction, not a proof.
We show the result for each question and each question type.
We also do a McNemar test, but only as a hint.

## Ablation

We compare B_rules, B_refusal and B_citations with A in the same way.
Then we see which part of B helps. Only the judge grades these.

We checked the judge on dev on 2026-11-22. Kappa was 0.70 for correctness and 0.53
for groundedness. So we trust correctness, but we add a warning for groundedness.

## Rules from dev

- Gold chunks are the smallest set of chunks that is enough. Sometimes another set also
  works, and then recall looks too low (dev_03 and dev_07). We write this as a limitation.
  We do not change the gold chunks.
- We do not change the gold answer for dev_02. It is only a dev question.

## After the final run

We do not change the prompts, the judge, the questions or this plan.
If we add something later, we call it extra (exploratory).
