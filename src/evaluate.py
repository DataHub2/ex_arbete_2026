"""Grades stored runs with an LLM judge. Reads experiment_runs, writes evaluation_results.

The answer model is never called again, the judge sees the answer and the exact
context that produced it, both stored at run time. So, the judge prompt can be
changed and everything re-graded for free.

The judge is gpt-oss-120b, which is different from the answer model -> less
self-preference bias. A judge is not ground truth, grade the dev split by hand too 
and check the two agree. See manual_template and agreement below.

    cfg = EvalConfig()
    rows = evaluate_run(spark, cfg, run_id="20261031T...")
    save_evaluations(spark, cfg, rows)
    print(format_summary(summarize(rows)))
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from src.rag import retrieval_metrics

# Judge must return one of these. 
# Manual grading uses the same words, so the two can be compared directly.
CORRECTNESS = ["correct", "partial", "incorrect"]
GROUNDEDNESS = ["grounded", "partial", "ungrounded"]
REFUSAL = ["declined", "hedged", "answered"]

JUDGMENT_FIELDS = ["correctness", "groundedness", "refusal", "invented_rule", "judge_reason"]


@dataclass(frozen=True)
class EvalConfig:
    catalog: str = "workspace"
    schema: str = "policy_rag"

    # Serving endpoint, not the system.ai.* name in docs/model_choices.md.
    # Those are Unity Catalog model names and don't resolve as endpoints.
    judge_endpoint: str = "databricks-gpt-oss-120b"
    temperature: float = 0.0
    max_tokens: int = 2000   # gpt-oss is a reasoning model, reasoning tokens should count here

    @property
    def runs_table(self):
        return f"{self.catalog}.{self.schema}.experiment_runs"

    @property
    def results_table(self):
        return f"{self.catalog}.{self.schema}.evaluation_results"

    def as_dict(self):
        return asdict(self)


# Judge prompts

JUDGE_SYSTEM = (
    "You grade answers given by an assistant that answers employee questions "
    "about internal company policies. Judge only what is in front of you. "
    "Reply with a single JSON object and nothing else."
)

JUDGE_IN_SCOPE = """\
Question:
{question}

Reference answer (what the policies say):
{gold_answer}

Context the assistant was given:
{context_text}

The assistant's answer:
{answer}

Grade two things, independently of each other.

correctness — does the answer match the reference answer?
  "correct"   every claim matches, nothing important is missing
  "partial"   partly right, or right but missing a condition or a second half
  "incorrect" contradicts the reference, or does not answer the question

groundedness — is every claim in the answer supported by the context above?
  "grounded"   every claim traces to the context
  "partial"    mostly supported, but at least one claim is not in the context
  "ungrounded" the main claim is not in the context

An answer can be correct but ungrounded: the assistant may know the right answer
from general knowledge while the context does not support it.
Grade that as correct and ungrounded, not as a compromise between the two.

Reply with:
{{"correctness": "...", "groundedness": "...", "reason": "one sentence"}}"""

JUDGE_OUT_OF_SCOPE = """\
Question:
{question}

Context the assistant was given:
{context_text}

The assistant's answer:
{answer}

The policies do not answer this question. The context may still look relevant,
it is the nearest material, which is why the question is in the test set.

refusal — does the answer say the policies do not cover this?
  "declined" says plainly it is not covered, or refers the employee onward
  "hedged"   answers but flags uncertainty or that the policy may not cover it
  "answered" answers as if the policies covered it

invented_rule, does the answer state a specific rule, number, deadline or
entitlement that is not in the context? true or false.

Reply with:
{{"refusal": "...", "invented_rule": true, "reason": "one sentence"}}"""


# Judge


def _judge_client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def _chat(client, cfg, user_prompt):
    """One judge call. Kept out of rag.py on purpose, the judge has its own model
    and parameters, and rag.py shouldn't change once runs are logged against it."""
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

    response = client.serving_endpoints.query(
        name=cfg.judge_endpoint,
        messages=[
            ChatMessage(role=ChatMessageRole.SYSTEM, content=JUDGE_SYSTEM),
            ChatMessage(role=ChatMessageRole.USER, content=user_prompt),
        ],
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    return response.choices[0].message.content


def _parse(raw):
    """Pull the JSON object out of the reply, code fences and prose included."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def _validate(parsed, in_scope):
    """Map the reply onto the result fields, rejecting labels we didn't ask for."""
    out = dict.fromkeys(JUDGMENT_FIELDS)
    out["judge_reason"] = (parsed.get("reason") or "")[:500]

    def label(key, allowed):
        value = parsed.get(key)
        if value not in allowed:
            raise ValueError(f"{key}={value!r} is not one of {allowed}")
        return value

    if in_scope:
        out["correctness"] = label("correctness", CORRECTNESS)
        out["groundedness"] = label("groundedness", GROUNDEDNESS)
    else:
        out["refusal"] = label("refusal", REFUSAL)
        out["invented_rule"] = bool(parsed.get("invented_rule"))
    return out


def judge_row(client, cfg, row):
    """Grade one stored run row. Returns the judgment fields and the raw reply."""
    template = JUDGE_IN_SCOPE if row["in_scope"] else JUDGE_OUT_OF_SCOPE
    prompt = template.format(
        question=row["question"],
        gold_answer=row.get("gold_answer") or "",
        context_text=row["context_text"],
        answer=row["answer"],
    )
    raw = _chat(client, cfg, prompt)
    return _validate(_parse(raw), row["in_scope"]), raw


# Running


def load_run(spark, cfg, run_id):
    """Stored rows for one run, errors excluded, nothing to grade in those."""
    rows = (spark.table(cfg.runs_table)
                 .filter(f"run_id = '{run_id}' AND error IS NULL")
                 .collect())
    return [r.asDict(recursive=True) for r in rows]


def evaluate_rows(cfg, rows, client=None, on_progress=None):
    """Grade stored rows. A failed call or an unusable label goes in judge_error,
    the run continues."""
    client = client or _judge_client()
    evaluations = []

    for position, row in enumerate(rows, start=1):
        evaluation = {
            "run_id": row["run_id"],
            "question_id": row["question_id"],
            "variant": row["variant"],
            "question_type": row["question_type"],
            "in_scope": row["in_scope"],
            **dict.fromkeys(JUDGMENT_FIELDS),
            **retrieval_metrics(row),
            "judge_endpoint": cfg.judge_endpoint,
            "judge_raw": None,
            "judge_error": None,
            "created_at": datetime.now(timezone.utc),
        }

        try:
            judgment, raw = judge_row(client, cfg, row)
            evaluation.update(judgment)
            evaluation["judge_raw"] = raw[:2000]
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            evaluation["judge_error"] = f"{type(exc).__name__}: {exc}"

        evaluations.append(evaluation)
        if on_progress:
            on_progress(position, len(rows), evaluation)

    return evaluations


def evaluate_run(spark, cfg, run_id, client=None, on_progress=None):
    return evaluate_rows(cfg, load_run(spark, cfg, run_id), client, on_progress)


# Summary of the evaluation


def _share(values, wanted):
    values = [v for v in values if v is not None]
    return sum(v == wanted for v in values) / len(values) if values else None


def summarize(evaluations):
    """Per question type, plus an in-scope and an out-of-scope total."""
    graded = [e for e in evaluations if not e["judge_error"]]
    groups = {}
    for evaluation in graded:
        groups.setdefault(evaluation["question_type"], []).append(evaluation)
    groups["ALL in-scope"] = [e for e in graded if e["in_scope"]]
    groups["ALL out-of-scope"] = [e for e in graded if not e["in_scope"]]

    summary = []
    for name, group in groups.items():
        recalls = [e["recall_at_k"] for e in group if e["recall_at_k"] is not None]
        summary.append({
            "group": name,
            "n": len(group),
            "recall_at_k": sum(recalls) / len(recalls) if recalls else None,
            "correct": _share([e["correctness"] for e in group], "correct"),
            "grounded": _share([e["groundedness"] for e in group], "grounded"),
            "declined": _share([e["refusal"] for e in group], "declined"),
            "invented_rule": _share([e["invented_rule"] for e in group], True),
        })
    return summary


def format_summary(summary):
    header = (f"{'group':<24} {'n':>3} {'recall@k':>9} {'correct':>8} "
              f"{'grounded':>9} {'declined':>9} {'invented':>9}")
    lines = [header, "-" * len(header)]
    for s in summary:
        cells = [f"{s[k]:.2f}" if s[k] is not None else "-"
                 for k in ("recall_at_k", "correct", "grounded", "declined", "invented_rule")]
        lines.append(f"{s['group']:<24} {s['n']:>3} {cells[0]:>9} {cells[1]:>8} "
                     f"{cells[2]:>9} {cells[3]:>9} {cells[4]:>9}")
    return "\n".join(lines)


# Validating the judge against manual grading


def manual_template(rows):
    """Rows to grade by hand, judgment columns left blank.

    Write to CSV, fill the blanks with the same labels as the judge, read back,
    pass both to agreement. Grade before looking at the judge's output.
    """
    return [{
        "run_id": r["run_id"],
        "question_id": r["question_id"],
        "question_type": r["question_type"],
        "in_scope": r["in_scope"],
        "question": r["question"],
        "gold_answer": r.get("gold_answer") or "",
        "answer": r["answer"],
        "context_text": r["context_text"],
        "correctness": "",      # correct | partial | incorrect     (in-scope)
        "groundedness": "",     # grounded | partial | ungrounded   (in-scope)
        "refusal": "",          # declined | hedged | answered      (out-of-scope)
        "invented_rule": "",    # true | false                      (out-of-scope)
        "notes": "",
    } for r in rows]


def cohens_kappa(labels_a, labels_b):
    """Agreement corrected for chance. 1.0 perfect, 0.0 chance level.

    Above ~0.6 usually reads as substantial. Below that the judge's numbers need
    a caveat in the report.
    """
    pairs = [(a, b) for a, b in zip(labels_a, labels_b) if a and b]
    if not pairs:
        return None
    a, b = [p[0] for p in pairs], [p[1] for p in pairs]
    n = len(pairs)

    observed = sum(x == y for x, y in pairs) / n
    expected = sum((a.count(l) / n) * (b.count(l) / n) for l in set(a) | set(b))
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def agreement(evaluations, manual):
    """Judge against manual grading, per dimension."""
    by_id = {m["question_id"]: m for m in manual}

    def human(question_id, field):
        row = by_id.get(question_id)
        return (row.get(field) or "").strip().lower() if row else ""

    result = {}
    for field in ("correctness", "groundedness", "refusal"):
        judge_labels, human_labels = [], []
        for evaluation in evaluations:
            if evaluation["question_id"] in by_id:
                judge_labels.append(evaluation[field] or "")
                human_labels.append(human(evaluation["question_id"], field))

        pairs = [(j, h) for j, h in zip(judge_labels, human_labels) if j and h]
        result[field] = {
            "n": len(pairs),
            "exact_match": sum(j == h for j, h in pairs) / len(pairs) if pairs else None,
            "kappa": cohens_kappa(judge_labels, human_labels),
            "disagreements": [
                {"question_id": e["question_id"], "judge": e[field],
                 "manual": human(e["question_id"], field)}
                for e in evaluations
                if e[field] and human(e["question_id"], field)
                and e[field] != human(e["question_id"], field)
            ],
        }
    return result


# Saving


RESULTS_SCHEMA = """
    run_id string, question_id string, variant string,
    question_type string, in_scope boolean,
    correctness string, groundedness string, refusal string,
    invented_rule boolean, judge_reason string,
    recall_at_k double, reciprocal_rank double, n_gold_retrieved int,
    judge_endpoint string, judge_raw string, judge_error string,
    created_at timestamp
"""


def save_evaluations(spark, cfg, evaluations, table=None):
    """Append judgments. Re-grading appends a second set, tell them apart by
    created_at and keep the old one, a changed judge prompt is a result."""
    if not evaluations:
        raise ValueError("Nothing to save.")

    table = table or cfg.results_table
    (spark.createDataFrame(evaluations, schema=RESULTS_SCHEMA)
          .write.mode("append").option("mergeSchema", "true").saveAsTable(table))
    return table