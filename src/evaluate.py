"""An AI judge grades the saved answers.
Reads from experiment_runs and saves to evaluation_results.

The judge reads the saved answer and the saved text. We do not ask the
answer model again, so we can grade again for free.

The judge is gpt-oss-120b. It is not the same model as the one that answers,
so it does not like its own answers more. The judge can be wrong, so we also
grade by hand and compare. See manual_template and agreement.

Example:
    cfg = EvalConfig()
    rows = evaluate_run(spark, cfg, run_id="20261031T...")
    save_evaluations(spark, cfg, rows)
    print(format_summary(summarize(rows)))
"""

import json
import random
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from src.prompts import CONTEXT_SEPARATOR, HARD_RULES, INFORMATION_CLASSES
from src.rag import retrieval_metrics

# The judge must use one of these words.
# We use the same words when we grade by hand.
CORRECTNESS = ["correct", "partial", "incorrect"]
GROUNDEDNESS = ["grounded", "partial", "ungrounded"]
REFUSAL = ["declined", "hedged", "answered"]

JUDGMENT_FIELDS = ["correctness", "groundedness", "refusal", "invented_rule", "judge_reason"]


@dataclass(frozen=True)
class EvalConfig:
    catalog: str = "workspace"
    schema: str = "policy_rag"

    # The judge model. Use this name, the system.ai.* name does not work here.
    judge_endpoint: str = "databricks-gpt-oss-120b"
    temperature: float = 0.0
    max_tokens: int = 2000   # gpt-oss thinks first, and thinking uses tokens too
    n_votes: int = 3         # the judge can change its mind, so it grades every answer 3 times

    @property
    def runs_table(self):
        return f"{self.catalog}.{self.schema}.experiment_runs"

    @property
    def results_table(self):
        return f"{self.catalog}.{self.schema}.evaluation_results"

    def as_dict(self):
        return asdict(self)


# Judge prompts

# Change this when the judge prompt changes. It is saved with every grade,
# so we never mix old and new grades. Old rows without it are v1.
# v2: the judge also checks the reason, not only the answer.
JUDGE_VERSION = "v2"

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

correctness — compare the answer with the reference answer. Check the reason
before the conclusion.
  "correct"   the conclusion and the reason both match the reference, and nothing
              the reference treats as essential is missing
  "partial"   the conclusion matches, but the reason is wrong or missing, or a
              condition or a second half of the reference is missing, or the answer
              is uncertain ("probably", "likely") where the reference is definite
  "incorrect" the conclusion contradicts the reference, the answer allows (even
              conditionally) something the reference forbids, or it does not answer

  Example: reference "No, rule A forbids it." Answer "No, because of rule B."
  -> partial: right conclusion, wrong reason.
  Example: reference "No, rule A forbids it." Answer "Yes, if condition C holds."
  -> incorrect: it allows something the reference forbids.

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
    """Ask the judge one time. This is not in rag.py, because the judge
    has its own model and settings."""
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
    """Get the JSON from the judge's reply, even if there is more text."""
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
    """Put the reply in our fields. Stop if the judge used a wrong word."""
    judgment = dict.fromkeys(JUDGMENT_FIELDS)
    judgment["judge_reason"] = (parsed.get("reason") or "")[:500]

    def label(key, allowed):
        value = parsed.get(key)
        if value not in allowed:
            raise ValueError(f"{key}={value!r} is wrong, use one of {allowed}")
        return value

    if in_scope:
        judgment["correctness"] = label("correctness", CORRECTNESS)
        judgment["groundedness"] = label("groundedness", GROUNDEDNESS)
    else:
        judgment["refusal"] = label("refusal", REFUSAL)
        judgment["invented_rule"] = bool(parsed.get("invented_rule"))
    return judgment


def judge_context(row):
    """All text the chatbot could read: the chunks, plus the hard rules
    if it had them (B and B_rules). Without the rules, a right answer
    from the rules would get "ungrounded"."""
    context = row["context_text"] or ""
    system_prompt = row.get("system_prompt") or ""
    if INFORMATION_CLASSES in system_prompt:
        context = "Information classes (in the system prompt):\n" + INFORMATION_CLASSES + CONTEXT_SEPARATOR + context
    if HARD_RULES in system_prompt:
        context = "Hard rules (in the system prompt):\n" + HARD_RULES + CONTEXT_SEPARATOR + context
    return context


# The words for each field, best first. The order is used when we count votes.
SCALES = {"correctness": CORRECTNESS, "groundedness": GROUNDEDNESS, "refusal": REFUSAL}


def _median_label(labels, scale):
    """Pick the middle grade. If it is a tie, pick the worse one."""
    ranked = sorted(labels, key=scale.index)
    return ranked[len(ranked) // 2]


def _combine(votes, in_scope):
    """Make one grade from the judge's votes.

    Each field gets the middle vote. invented_rule is true if half or more
    of the votes say true. judge_agreement is how many votes gave the
    final grade (correctness in scope, refusal out of scope).
    """
    fields = ["correctness", "groundedness"] if in_scope else ["refusal"]
    judgment = dict.fromkeys(JUDGMENT_FIELDS)
    for field in fields:
        judgment[field] = _median_label([vote[field] for vote in votes], SCALES[field])
    if not in_scope:
        judgment["invented_rule"] = 2 * sum(vote["invented_rule"] for vote in votes) >= len(votes)

    main_field = fields[0]
    same_votes = [vote for vote in votes if vote[main_field] == judgment[main_field]]
    judgment["judge_reason"] = same_votes[0]["judge_reason"]
    judgment["judge_agreement"] = len(same_votes) / len(votes)
    return judgment


def judge_row(client, cfg, row):
    """Grade one answer 3 times (cfg.n_votes) and make one grade.

    If a vote fails, we skip it and use the others.
    Gives back the grade, the judge's replies and how many votes worked.
    Stops only if all votes failed.
    """
    template = JUDGE_IN_SCOPE if row["in_scope"] else JUDGE_OUT_OF_SCOPE
    prompt = template.format(
        question=row["question"],
        gold_answer=row.get("gold_answer") or "",
        context_text=judge_context(row),
        answer=row["answer"],
    )

    votes, raws, errors = [], [], []
    for _ in range(cfg.n_votes):
        raw = None
        try:
            raw = _chat(client, cfg, prompt)
            votes.append(_validate(_parse(raw), row["in_scope"]))
        except Exception as exc:  # noqa: BLE001 - saved, and raised below if no vote worked
            errors.append(f"{type(exc).__name__}: {exc}")
        if raw is not None:
            raws.append(raw)

    if not votes:
        raise RuntimeError(f"All {cfg.n_votes} votes failed: " + " | ".join(errors))
    return _combine(votes, row["in_scope"]), raws, len(votes)


# Running


def load_run(spark, cfg, run_id):
    """Get the rows for one run. Rows with an error are skipped."""
    rows = (spark.table(cfg.runs_table)
                 .filter(f"run_id = '{run_id}' AND error IS NULL")
                 .collect())
    return [r.asDict(recursive=True) for r in rows]


def evaluate_rows(cfg, rows, client=None, on_progress=None):
    """Grade the rows. If one fails, save the error in judge_error and go on."""
    client = client or _judge_client()
    evaluations = []

    for number, row in enumerate(rows, start=1):
        evaluation = {
            "run_id": row["run_id"],
            "question_id": row["question_id"],
            "variant": row["variant"],
            "question_type": row["question_type"],
            "in_scope": row["in_scope"],
            **dict.fromkeys(JUDGMENT_FIELDS),
            **retrieval_metrics(row),
            "judge_endpoint": cfg.judge_endpoint,
            "judge_version": JUDGE_VERSION,
            "judge_votes": None,
            "judge_agreement": None,
            "judge_raw": None,
            "judge_error": None,
            "created_at": datetime.now(timezone.utc),
        }

        try:
            judgment, raws, n_votes = judge_row(client, cfg, row)
            evaluation.update(judgment)
            evaluation["judge_votes"] = n_votes
            evaluation["judge_raw"] = "\n---\n".join(raws)[:6000]
        except Exception as exc:  # noqa: BLE001 - the error is saved
            evaluation["judge_error"] = f"{type(exc).__name__}: {exc}"

        evaluations.append(evaluation)
        if on_progress:
            on_progress(number, len(rows), evaluation)

    return evaluations


def evaluate_run(spark, cfg, run_id, client=None, on_progress=None):
    return evaluate_rows(cfg, load_run(spark, cfg, run_id), client, on_progress)


# Summary


def _share(values, wanted):
    """How many of the values are `wanted`, from 0 to 1."""
    values = [value for value in values if value is not None]
    return sum(value == wanted for value in values) / len(values) if values else None


def summarize(evaluations):
    """Results for each question type, plus in scope and out of scope in total."""
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


# Compare the judge with our grades


def manual_template(rows):
    """Make rows to grade by hand. The grade columns are empty.

    Save as CSV, fill in the empty columns, read it back and use agreement.
    Grade before you look at the judge.
    """
    return [{
        "run_id": r["run_id"],
        "question_id": r["question_id"],
        "question_type": r["question_type"],
        "in_scope": r["in_scope"],
        "question": r["question"],
        "gold_answer": r.get("gold_answer") or "",
        "answer": r["answer"],
        "context_text": judge_context(r),
        "correctness": "",      # correct | partial | incorrect     (in-scope)
        "groundedness": "",     # grounded | partial | ungrounded   (in-scope)
        "refusal": "",          # declined | hedged | answered      (out-of-scope)
        "invented_rule": "",    # true | false                      (out-of-scope)
        "notes": "",
    } for r in rows]


def blind_template(rows, seed=0):
    """Grade A and B by hand, without knowing which is which.

    The rows are mixed and run_id is changed to item_id.
    Gives back the rows and a key (item_id -> run_id).
    Do not look at the key before all grading is done.

    It is not fully blind: B shows sources and hard rules,
    so you may still guess that it is B.
    """
    mixed_rows = list(rows)
    random.Random(seed).shuffle(mixed_rows)

    template, key = [], {}
    for number, row in enumerate(mixed_rows, start=1):
        item_id = f"item_{number:03d}"
        key[item_id] = row["run_id"]
        item = manual_template([row])[0]
        del item["run_id"]
        template.append({"item_id": item_id, **item})
    return template, key


def unblind(manual, key):
    """Put the graded rows back with their run: {run_id: rows}."""
    per_run = {}
    for row in manual:
        per_run.setdefault(key[row["item_id"]], []).append(row)
    return per_run


def cohens_kappa(labels_a, labels_b):
    """How much two graders agree, when we remove agreement by luck.
    1.0 = always agree. 0.0 = same as luck.

    Over 0.6 is good. Under 0.6, write a warning in the report.
    """
    pairs = [(a, b) for a, b in zip(labels_a, labels_b) if a and b]
    if not pairs:
        return None
    a, b = [p[0] for p in pairs], [p[1] for p in pairs]
    n = len(pairs)

    observed = sum(x == y for x, y in pairs) / n
    expected = sum((a.count(label) / n) * (b.count(label) / n) for label in set(a) | set(b))
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def agreement(evaluations, manual):
    """Compare the judge with our grades, for each field."""
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
    judge_endpoint string, judge_version string,
    judge_votes int, judge_agreement double,
    judge_raw string, judge_error string,
    created_at timestamp
"""


def save_evaluations(spark, cfg, evaluations, table=None):
    """Add the grades to the table. If we grade again, we get new rows
    and the old ones stay. Use created_at to see which is which."""
    if not evaluations:
        raise ValueError("Nothing to save.")

    table = table or cfg.results_table
    (spark.createDataFrame(evaluations, schema=RESULTS_SCHEMA)
          .write.mode("append").option("mergeSchema", "true").saveAsTable(table))
    return table