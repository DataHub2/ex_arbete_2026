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