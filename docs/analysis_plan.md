# Analysis plan
 
Written before the final run. The final split has not been run or tuned on.
Anything not decided here counts as exploratory.
 
## What is run
 
- Final split: 30 questions, 23 in scope and 7 out of scope.
- Variants: A, B, B_rules, B_refusal, B_citations. One run each, temperature 0.
- Code, prompts, judge (v2, median of 3 votes) and test set are frozen as of
  2026-11-20.
## Primary comparison
 
A against B on the 23 in-scope questions, measured by correctness.
 
Correctness is graded by hand by project members, and that grading is the primary
measure. The judge is a second measure, and its agreement with the manual grading
(Cohen's kappa) is reported on final.
 
A and B are graded in one file, mixed in random order with the variant hidden
(`blind_template` in `src/evaluate.py`). The blinding is partial: B's citations may
still give the variant away. This is reported as a limitation.
 
## Grading protocol
 
- Two graders grade every answer independently, without seeing each other's grades
  and before seeing the judge's output.
- Disagreements are resolved by the third member, who sees both grades and decides.
- The share of answers the two graders disagreed on is reported per dimension,
  before adjudication.
- The key (`key_DO_NOT_OPEN.json`) stays closed until all grading and adjudication
  are finished.
## Secondary measures
 
- Groundedness, in scope.
- Out of scope, 7 questions: refusal, and whether a rule was invented.
- Over-refusal: in-scope answers that give the refusal sentence.
- Citations, B and B_citations: the share of cited [Document > Section] labels that
  match a retrieved excerpt.
- Retrieval: recall@k and MRR. Should be identical across all variants, since B only
  changes the prompt.
## How "B is better" is decided
 
B is better if it has more correct answers than A on the in-scope questions, without
more over-refusal and without more invented rules.
 
With n = 23 the result is a direction, not a proof. Results are reported per question
and per question type. A paired exact test (McNemar) on correct / not correct is
reported as an indication only.
 
## Ablation
 
B_rules, B_refusal and B_citations are compared with A in the same way, to show which
part of B makes the difference. They are graded by the judge only, so these results
carry the judge's caveat.
 
## Conventions decided on dev
 
- Gold chunks are the minimal sufficient set. Recall can undercount when another set
  of chunks is also enough, as seen on dev_03 and dev_07. Such cases are reported as
  a known limitation and the gold sets are not changed.
- dev_02's gold answer is left as it is. It is on the dev split and does not affect
  final.
## Not allowed after the final run
 
Changing the prompts, the judge, the test set or this plan. Anything added later is
labelled exploratory.