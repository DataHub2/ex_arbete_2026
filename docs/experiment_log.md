# Experiment log

## 2026-10-28 – First retrieval test

**Setup:** We made a search index on `workspace.policy_rag.policy_chunks` (39 chunks). Embeddings: `gte-large-en`. top-k = 3. Notebook: `notebooks/02_vector_index`.

**Results:**

```
Q: How many vacation days do I get?
   0.644  02_vacation_and_sick_leave__01  (Vacation and Sick Leave Policy / Number of vacation days)
   0.618  02_vacation_and_sick_leave__03  (Vacation and Sick Leave Policy / Saving vacation days)
   0.584  01_parental_leave__05  (Parental Leave Policy / Vacation during parental leave)

Q: Can I stay home when my kid is sick?
   0.566  01_parental_leave__06  (Parental Leave Policy / Temporary parental benefit (care of a sick child))
   0.554  02_vacation_and_sick_leave__09  (Vacation and Sick Leave Policy / Sickness during vacation)
   0.537  02_vacation_and_sick_leave__05  (Vacation and Sick Leave Policy / Reporting sick)

Q: Can I paste a customer contract into Microsoft 365 Copilot?
   0.569  04_ai_policy__06  (Policy on the Use of AI at Work / Recording and transcribing meetings)
   0.534  04_ai_policy__01  (Policy on the Use of AI at Work / Approved AI tools)
   0.509  04_ai_policy__05  (Policy on the Use of AI at Work / Labelling and transparency)

Q: Who do I contact if my payslip is wrong?
   0.602  03_who_to_ask__03  (Who to Ask About What / Payroll department)
   0.527  03_who_to_ask__08  (Who to Ask About What / Whistleblowing)
   0.524  02_vacation_and_sick_leave__10  (Vacation and Sick Leave Policy / Contact)

Q: What is the company's pension plan?   (not covered by any policy)
   0.531  03_who_to_ask__03  (Who to Ask About What / Payroll department)
   0.516  04_ai_policy__02  (Policy on the Use of AI at Work / Information classes)
   0.512  01_parental_leave__04  (Parental Leave Policy / Parental pay supplement from Nordljus)
```

**Observations:**

1. Easy questions find the right chunk first, even with other words ("kid is sick" → "care of a sick child").
2. **Questions that need two parts are hard.** The Copilot question needs *Information classes* and *Approved AI tools* / *Hard rules*. The search only found *Approved AI tools*. → This can be a problem type for RQ3.
3. **The score is not enough to say "I don't know".** The pension question had the lowest score (0.531), but a real question was close (0.566). → In B the model must decide itself.



## 2026-10-31 – First end-to-end run of Variant A

**Setup:** Notebook `03_variant_a`. top-k = 3. Model: 'databricks-meta-llama-3-3-70b-instruct'. Temperature 0. A simple prompt with no sources, no "I don't know" and no hard rules.

**Results (summary):**

| Question | Result |
|---|---|
| Vacation days at Nordljus | Correct (30, and 25 for fixed-term) |
| Vacation days in Sweden | Correct. Law 25, Nordljus 30. The made up "16 public holidays" was gone |
| Can I stay home when my kid is sick? | Correct and complete |
| Customer contract in M365 Copilot | Half right (see below) |
| Pension plan (out of scope) | Said it did not know, and said to ask HR |

**Observations:**

1. **Decision (30 Oct): A works.** We go on with B.
2. **If the search misses, the answer is wrong.** The search did not find *Information classes*. So the model guessed ("a contract *typically* contains confidential information"). It also said something false ("the policy does not explicitly state that customer contracts cannot be used"). → We measure the search and the answer apart. In B we always give the model the hard rules.
3. **A already says "I don't know" on easy questions.** → We need harder trick questions, close to the rules (for example AI tools not on the list, travel money). If not, we can not see a difference between A and B.



## 2026-10-31 – Test set, and first measured run (dev split) / N

**Test set:** 40 questions in `data/questions/questions.jsonl` 10 development
(`dev_*`) and 30 held out until later (probably in W48) as scheduled (`final_*`). 
Six types: single_section, multi_section, statutory_vs_company, hard_rule, near_miss and out_of_scope.
`gold_chunk_ids` is the minimal sufficient set: the chunks that must all be
retrieved for a grounded answer. Out-of-scope questions have none and are scored
on whether the answer declines.

**Setup:** Notebook `04_run_experiment`, Variant A, dev split, top-k = 3,
`databricks-meta-llama-3-3-70b-instruct`, temperature 0. Retrieval, prompt and
model call are the same as in `03_variant_a`; this run also writes one row per
question to `workspace.policy_rag.experiment_runs`. Answers and contexts can
be graded later without calling the model again.

**Retrieval:**

| question_type | n | recall@k | MRR | full |
|---|---|---|---|---|
| hard_rule | 2 | 0.50 | 0.50 | 1/2 |
| multi_section | 2 | 0.50 | 0.50 | 1/2 |
| single_section | 2 | 1.00 | 1.00 | 2/2 |
| statutory_vs_company | 1 | 1.00 | 1.00 | 1/1 |

**Observations:**

1. **Both failures are the same two chunks.** `dev_03` (contract into Copilot)
   and `dev_07` (medical certificate into Nordljus Assistant) each scored
   recall 0.00, and in both cases the missing chunks were `04_ai_policy__02` (Information classes) 
   and `04_ai_policy__03` (Hard rules). 
   These hold the policy's classification scheme and its hard rules, the parts
   a question has to be reasoned against rather than matched against. 
   Retrieval instead favours chunks that share wording with the question. 
   This extends the 2026-10-28 observation from one question to a repeatable category.
2. **Direct consequence for Variant B.** The hard rules should be placed in the
   system prompt rather than left to retrieval, since the questions that need
   them are the ones that do not retrieve them.
3. `single_section` and `statutory_vs_company` at 1.00 confirm that the gold
   chunk ids and the pipeline itself are correct.
4. **Caveat on the metric.** `dev_03` has two valid grounding paths:
   `__02` + `__03`, or `__02` + `__01`. Only the first is recorded as gold, so a
   run retrieving the second is scored as a miss. Recall may therefore understate
   the system slightly. Either record alternative sufficient sets before the final run, 
   or state the convention in the method chapter.
5. n = 1–2 per type on the dev split. These are directions to test on the 30
   final questions, not results.



## 2026-11-05 – LLM judge on the dev run / N

**Setup:** Notebook `05_evaluate`, judge `databricks-gpt-oss-120b`, temperature 0.
Graded run `20261031T191325Z-09e6e4` (`variant_a_dev_01`, Variant A, 10 questions).
The answer model was not called again, the judge sees the stored answer and the exact
context that produced it. Judgments in `workspace.policy_rag.evaluation_results`.

**Results:**

| group | n | recall@k | correct | grounded | declined | invented |
|---|---|---|---|---|---|---|
| single_section | 2 | 1.00 | 0.50 | 0.50 | - | - |
| multi_section | 2 | 0.50 | 0.50 | 0.50 | - | - |
| statutory_vs_company | 1 | 1.00 | 1.00 | 1.00 | - | - |
| hard_rule | 2 | 0.50 | 1.00 | 1.00 | - | - |
| out_of_scope | 1 | - | - | - | 1.00 | 0.00 |
| near_miss | 2 | - | - | - | 1.00 | 0.00 |
| ALL in-scope | 7 | 0.71 | 0.71 | 0.71 | - | - |
| ALL out-of-scope | 3 | - | - | - | 1.00 | 0.00 |

**Observations:**

1. **The judge needs a large token budget, and fails silently without one.** At
   `max_tokens=400` three of ten questions came back as unparseable JSON, truncated
   mid-string. gpt-oss is a reasoning model, reasoning tokens count against the same
   budget, so the longest-reasoning questions fail first. Those three were `dev_02`,
   `dev_03` and `dev_07`, the hardest ones. The summary excluded them and showed
   1.00 across the board, which looked like a clean pass. Raised to 2000, all ten graded. 
   The summary now warns when anything is ungraded. Any judged run should report
   how many were graded, not only the scores.
2. **No headroom for the refusal intervention on the dev split.** Variant A declined
   all three out-of-scope and near_miss questions and invented no rules, including the
   two hard traps (`dev_09` bereavement leave, `dev_10` mileage rate). This confirms
   the concern from 2026-10-31. Either the final 30 show a difference, or the refusal
   part of RQ2 has to be reported as unmeasurable on this test set. These are questions,
   questions that should be raised amongst the group or with a supervisor.
3. **The known hallucination was caught automatically.** `dev_03` was graded partial /
   partial: the answer advises against using Copilot for a contract but claims the
   policy does not explicitly forbid it. Same failure as logged on 2026-10-31, now
   found by the judge instead of by hand.
4. **Retrieval failure and generation failure separate cleanly.** `dev_02` had
   recall@k 1.00 and was still partial: it gets the 09:00 notification right but
   claims the manager registers the sick leave, which the context does not say. Right
   chunks, wrong answer. Without separate measures this would be indistinguishable
   from `dev_03`, where retrieval was the problem.
5. **The minimal sufficient set can undercount.** `dev_07` scored recall@k 0.50 but was
   graded correct and grounded, one of the two gold chunks was enough to answer. Second
   instance of this, after the `dev_03` caveat on 2026-10-31, and the first with evidence.
   Retrieval metrics alone would have called it a failure. Decide before the final run:
   record alternative sufficient sets, or state the convention and report this case as
   its known limitation.
6. **The judge is not validated yet.** Manual grading of the ten dev questions is
   exported but not done, so no agreement figure exists. The numbers above are the
   judge's alone and should carry that caveat until the agreement figure exists.



## 2026-11-15 – Judge against manual grading / N

**Setup:** I (Nasser) graded the ten dev questions from run `20261031T191325Z-09e6e4` by hand, 
using the same labels as the judge, in `manual_grading_20261031T191325Z-09e6e4.csv`. 
The judge was re-run the same day on the same stored answers and contexts, and the two compared 
with `agreement` in `src/evaluate.py`.

**Results:**

| dimension | n | exact match | kappa |
|---|---|---|---|
| correctness | 7 | 0.57 | 0.00 |
| groundedness | 7 | 0.57 | 0.22 |
| refusal | 3 | 1.00 | 1.00 |

Disagreements, judge vs manual:

| question | correctness | groundedness |
|---|---|---|
| dev_02 | correct / partial | grounded / partial |
| dev_03 | correct / partial | partial / ungrounded |
| dev_07 | correct / partial | partial / ungrounded |

**Observations:**

1. **The judge called every in-scope answer correct.** All seven got `correct`, so it
   has no spread and nothing to agree about beyond chance. That is why kappa is 0.00
   while exact match reads 0.57. The judge has no discriminative power on correctness
   in this run.
2. **Every disagreement runs the same way.** The judge is more lenient than the human
   on all six, never stricter. A systematic bias. It appears to read "right conclusion" 
   as "right answer": `dev_07` reaches the correct no but with a reason the policy never gives, 
   and the judge still passed it.
3. **The judge changed its mind since 2026-11-05.** It then graded `dev_02` and
   `dev_03` as partial / partial. It now grades both, and `dev_07`, as correct. Same model, 
   same stored answers and contexts, temperature 0. Two things differ: the judge prompt was reworded, 
   and this is a second run. Revert the prompt to the 2026-11-05 wording and re-run to tell them apart. 
   If the labels still move, the judge is not reproducible, which matters more than its leniency.
4. **refusal kappa 1.00 carries no weight.** Three rows, all `declined` on both sides.
   Zero variance gives kappa 1.00 by definition and says nothing about reliability.
5. **Consequence.** The judge cannot carry correctness as it stands. Either tighten the
   rubric in the prompt so it has worked examples of `partial`, or report the manual
   grading as the primary measure on dev and use the judge as a secondary signal on final. 
   To be decided before the final run.
6. **Caveat on independence.** I (Nasser) had seen the judge's reasoning for `dev_02` and `dev_03` 
   before grading, so three of tthe ten were not graded blind. The direction of that bias would be 
   toward agreement, and the measured agreement is low anyway, so it does not explain the result. 
   A second grader from the group would/could settle it.



## 2026-11-15/16 – Variant B on the dev split, v1 and v2 / Z

**Setup:** Branch `feature/variant-b`. B = A's prompt plus three things:
the hard rules, a fixed "I don't know" sentence, and sources.
Same search, model and temperature as A. Judge: `databricks-gpt-oss-120b`, notebook `05_evaluate`.
The judge now also sees the hard rules (`judge_context`). If not, answers that use
the rules would get "ungrounded".

**Problem:** the first B run failed on all 10 questions with `NOT_FOUND: AI Search
endpoint ... not found`. The search endpoint was gone. Free Edition probably removed it
because we did not use it for a while. Fix: we ran `02_vector_index` again, deleted the
old index and built a new one from `policy_chunks`. The test from 2026-10-28 gave the
same results, so we can still compare with A.

**Runs:**

| version | run_id | change |
|---|---|---|
| B v1 | `20261115T210723Z-7fac1f` | hard rules, refusal, citations |
| B v2 | `20261116T144015Z-c88b7d` | + Information classes in the system prompt |

**Results (dev, 7 in-scope / 3 out-of-scope):**

| | A | B v1 | B v2 |
|---|---|---|---|
| recall@k | 0.71 | 0.71 | 0.71 |
| correct | 0.71 | 0.57 | 0.86 |
| grounded | 0.71 | 1.00 | 1.00 |
| declined | 1.00 | 1.00 | 1.00 |
| invented_rule | 0.00 | 0.00 | 0.00 |

**Observations:**

1. **The search is the same.** B only changes the prompt, so recall@k is the same as A.
   All changes in the answers come from the prompt.
2. **Groundedness went from 0.71 to 1.00.** B stopped guessing.
3. **The hard rules were not enough (v1).** `dev_03` said a contract can go into Copilot
   "if it is Public or Internal". `dev_07` said "no" because of rule 3, but rule 3 says
   "yes" for Nordljus Assistant. The rules need the information classes, and the search
   did not find them. In v2 we added the classes too. Then both answers were right.
4. **The judge changes its mind.** By mistake we graded v1 two times. `dev_01` went
   from partial to correct, and `dev_03` from partial to incorrect. Same answers,
   temperature 0. We must check the judge by hand.
5. **The judge does not check the reason well.** In v1 it said `dev_07` was correct,
   but the reason in the answer was wrong.
6. **The gold answer for `dev_02` may be wrong.** The policy says sick leave "is then
   registered in the HR Portal", but not by who. Look at it before the final run.
7. **We still can not see a difference in "I don't know" on dev.** A and B both said
   "I don't know" on all three. With only 7 in scope questions, one question changes
   correct by 0.14. This is a direction, not a result.



## 2026-11-22 - Judge v2 against the manual grades / N

**Setup:** Notebook `06_judge_check`. Judge v2, three votes with the median taken,
graded run `20261031T191325Z-09e6e4` again and compared with the manual grades from
2026-11-15. Same answers and contexts, nothing re-run on the answer model. Done before 
the final run so the plan could still change.

**Results:**

| dimension | n | exact match | kappa v1 | kappa v2 |
|---|---|---|---|---|
| correctness | 7 | 0.86 | 0.00 | 0.70 |
| groundedness | 7 | 0.71 | 0.22 | 0.53 |
| refusal | 3 | 1.00 | 1.00 | 1.00 |

Vote agreement: mean 0.97, lowest 0.67 on `dev_02`.

**Observations:**

1. **v2 has spread, v1 did not.** v2 gives 5 correct and 2 partial on the seven
   in-scope questions. v1 gave `correct` to all seven, which is why its kappa was
   0.00 however good the exact match looked.
2. **Correctness is usable.** kappa 0.70. v2 corrected three of v1's six
   disagreements: `dev_02` on both dimensions and `dev_03` on correctness.
3. **Groundedness is weaker.** kappa 0.53, below the 0.6 mark. It is reported with
   an explicit caveat, correctness is not.
4. **The remaining disagreements are one-directional and concentrated.** `dev_07`
   on both dimensions and `dev_03` on groundedness, all with the judge milder than
   the human. This inflates A and B equally and compresses the difference between them, 
   so the judge will sooner miss an effect than invent one.
5. **Median vote does its job.** Votes agreed completely on nine of ten
   questions. The one split was `dev_02`, where the gold answer itself is ambiguous
   about who registers the sick leave to the systam. The judge wavering there is reasonable.
6. **n = 7.** A single label moves kappa a lot at this size. 0.70 is a good sign,
   not a fixed value. The real estimate comes from the final split at n = 23.

**Decision, written into `analysis_plan.md` before the final run:** the ablation
(B_rules, B_refusal, B_citations) is graded by the judge alone for correctness.
Groundedness carries the judge's caveat wherever it is reported.