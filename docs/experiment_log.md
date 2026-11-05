# Experiment log

## 2026-10-28 – First retrieval test

**Setup:** Vector Search Delta Sync index on `workspace.policy_rag.policy_chunks` (39 chunks), embeddings with `gte-large-en`, top-k = 3. Notebook: `notebooks/02_vector_index`.

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

1. Single-section questions retrieve the correct chunk at rank 1, also when the wording differs from the document ("kid is sick" → "care of a sick child").
2. **Multi-section questions are weak.** The Copilot question needs both *Information classes* (a contract is Confidential) and *Approved AI tools* / *Hard rules*. Only *Approved AI tools* was retrieved (rank 2); *Information classes* was missing. → Candidate failure category for RQ3.
3. **Score threshold alone is not enough for refusal.** The out-of-scope pension question had the lowest top score (0.531), but the margin to valid questions is small (0.566). → Refusal in Variant B must rely on the LLM judging whether the context answers the question, not only on a score threshold.



## 2026-10-31 – First end-to-end run of Variant A

**Setup:** Notebook `03_variant_a`. Retrieval top-k = 3, answer model 'databricks-meta-llama-3-3-70b-instruct', temperature 0, simple system prompt (no citations, no refusal instructions, no hard rules).

**Results (summary):**

| Question | Result |
|---|---|
| Vacation days at Nordljus | Correct (30, and 25 for fixed-term) |
| Vacation days in Sweden | Correct, separated statutory 25 from Nordljus 30. Hallucinated "16 public holidays" from the Playground test was gone |
| Can I stay home when my kid is sick? | Correct and complete |
| Customer contract in M365 Copilot | Partly correct, partly ungrounded (see below) |
| Pension plan (out of scope) | Correctly declined, referred to HR |

**Observations:**

1. **Decision point (30 Oct): Variant A works.** Variant B is kept as planned.
2. **Retrieval errors become answer errors.** *Information classes* was not retrieved for the Copilot question. The model filled the gap with general knowledge ("a contract *typically* contains confidential information") and made a false claim about the policy ("the policy does not explicitly state that customer contracts cannot be used"). → Supports measuring retrieval and correctness separately, and motivates always including hard rules in the system prompt in Variant B.
3. **The baseline already declines obvious out-of-scope questions.** → The test set needs harder trap questions that are close to policy topics (e.g. unlisted AI tools, travel allowance, edge cases of eligibility rules). Otherwise no difference between A and B can be measured for refusal.



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