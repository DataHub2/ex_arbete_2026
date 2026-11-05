"""Runs test through a variant and saves every answer to Delta.

Same retrieval, prompt and model call as notebooks/03_variant_a, 
this adds the persistence of the evaluation and the final runs read back.

    cfg = RagConfig(variant="A")
    questions = load_questions("../data/questions/questions.jsonl", split="dev")
    rows = run_experiment(RagPipeline(cfg), questions, run_label="variant_a_dev")
    save_runs(spark, cfg, rows)
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.prompts import CONTEXT_SEPARATOR, get_prompts

# similarity_search returns these columns in order
RETRIEVE_COLUMNS = ["chunk_id", "document", "section", "text"]

# Per-chunk fields kept in the results table. 
# Chunk text dropped: already in context_text.
CHUNK_FIELDS = ["rank", "chunk_id", "document", "section", "score"]

QUESTION_FIELDS = [
    "question_id", "question", "question_type", "in_scope",
    "gold_chunk_ids", "gold_answer",
]

# Config fields stored per row,
# row says how it was produced.
CONFIG_FIELDS = [
    "answer_endpoint", "embedding_endpoint", "top_k", "temperature", "max_tokens",
]


@dataclass(frozen=True)
class RagConfig:
    """Defaults match notebooks/03_variant_a. Change here, not per notebook."""

    variant: str = "A"

    catalog: str = "workspace"
    schema: str = "policy_rag"

    vs_endpoint: str = "policy_rag_endpoint"
    top_k: int = 3

    # Serving endpoints, names in docs/model_choices.md
    # those are Unity Catalog model names and don't resolve as endpoints.
    answer_endpoint: str = "databricks-meta-llama-3-3-70b-instruct"
    embedding_endpoint: str = "databricks-gte-large-en"

    temperature: float = 0.0
    max_tokens: int = 500

    @property
    def index_name(self):
        return f"{self.catalog}.{self.schema}.policy_chunks_index"

    @property
    def chunks_table(self):
        return f"{self.catalog}.{self.schema}.policy_chunks"

    @property
    def runs_table(self):
        return f"{self.catalog}.{self.schema}.experiment_runs"

    def as_dict(self):
        return asdict(self)


# Questions


def load_questions(path, split=None):
    """Load the test set from JSON Lines. Lines starting with // are ignored.

    split="dev" or "final" filters on the question_id prefix. Use it, the final
    questions are held out until later.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No question file at {path}")

    questions = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            q = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno} is not valid JSON: {exc}") from exc

        missing = [f for f in QUESTION_FIELDS if f not in q]
        if missing:
            raise ValueError(f"{path}:{lineno} is missing: {', '.join(missing)}")
        if q["in_scope"] and not q["gold_chunk_ids"]:
            raise ValueError(f"{path}:{lineno} ({q['question_id']}) is in_scope but has "
                             "no gold_chunk_ids, so retrieval can't be scored.")
        if not q["in_scope"] and q["gold_chunk_ids"]:
            raise ValueError(f"{path}:{lineno} ({q['question_id']}) is out of scope but "
                             "has gold_chunk_ids.")
        questions.append(q)

    ids = [q["question_id"] for q in questions]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"Duplicate question_id(s) in {path}: {duplicates}")

    if split:
        questions = [q for q in questions if q["question_id"].startswith(f"{split}_")]
        if not questions:
            raise ValueError(f"No questions with prefix {split!r} in {path}")

    return questions


# Pipeline


class RagPipeline:
    """Retrieval and generation for one variant. Clients are created on first use.

    Pass index= and llm_client= to run without a workspace (how this is tested).
    """

    def __init__(self, cfg, index=None, llm_client=None):
        self.cfg = cfg
        self.system_prompt, self._build_user_prompt = get_prompts(cfg.variant)
        self._index = index
        self._llm = llm_client

    @property
    def index(self):
        if self._index is None:
            from databricks.vector_search.client import VectorSearchClient

            self._index = VectorSearchClient(disable_notice=True).get_index(
                endpoint_name=self.cfg.vs_endpoint, index_name=self.cfg.index_name
            )
        return self._index

    @property
    def llm(self):
        if self._llm is None:
            from databricks.sdk import WorkspaceClient

            self._llm = WorkspaceClient()
        return self._llm

    def retrieve(self, question):
        results = self.index.similarity_search(
            query_text=question,
            columns=RETRIEVE_COLUMNS,
            num_results=self.cfg.top_k,
        )
        return [
            {"rank": rank, "chunk_id": chunk_id, "document": document,
             "section": section, "text": text, "score": float(score)}
            for rank, (chunk_id, document, section, text, score)
            in enumerate(results["result"]["data_array"], start=1)
        ]

    def generate(self, question, chunks):
        from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

        user_prompt = self._build_user_prompt(question, chunks)
        started = time.perf_counter()
        response = self.llm.serving_endpoints.query(
            name=self.cfg.answer_endpoint,
            messages=[
                ChatMessage(role=ChatMessageRole.SYSTEM, content=self.system_prompt),
                ChatMessage(role=ChatMessageRole.USER, content=user_prompt),
            ],
            temperature=self.cfg.temperature,
            max_tokens=self.cfg.max_tokens,
        )
        usage = getattr(response, "usage", None)
        return {
            "answer": response.choices[0].message.content,
            "user_prompt": user_prompt,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
        }

    def answer(self, question):
        chunks = self.retrieve(question)
        return {"chunks": chunks, **self.generate(question, chunks)}


# Running


def new_run_id():
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def _build_row(cfg, system_prompt, run_id, run_label, question, result, error):
    chunks = result["chunks"] if result else []
    return {
        "run_id": run_id,
        "run_label": run_label,
        "variant": cfg.variant,
        **{f: question.get(f) for f in QUESTION_FIELDS},
        "retrieved": [{f: c[f] for f in CHUNK_FIELDS} for c in chunks],
        "retrieved_chunk_ids": [c["chunk_id"] for c in chunks],
        "context_text": CONTEXT_SEPARATOR.join(c["text"] for c in chunks) if chunks else None,
        "system_prompt": system_prompt,
        "user_prompt": result["user_prompt"] if result else None,
        "answer": result["answer"] if result else None,
        "error": error,
        **{f: getattr(cfg, f) for f in CONFIG_FIELDS},
        **{f: result[f] if result else None
           for f in ("latency_ms", "prompt_tokens", "completion_tokens")},
        "created_at": datetime.now(timezone.utc),
    }


def run_experiment(pipeline, questions, run_label, run_id=None, on_progress=None):
    """Run every question, one row each.

    A question that raises is recorded in the `error` column, the run continues, 
    so one failed call doesn't discard a 40-question (or so) run.
    """
    run_id = run_id or new_run_id()
    questions = list(questions)
    rows = []

    for position, question in enumerate(questions, start=1):
        result, error = None, None
        try:
            result = pipeline.answer(question["question"])
        except Exception as exc:  # noqa: BLE001 — recorded in the row, not swallowed
            error = f"{type(exc).__name__}: {exc}"

        rows.append(_build_row(pipeline.cfg, pipeline.system_prompt,
                               run_id, run_label, question, result, error))
        if on_progress:
            on_progress(position, len(questions), rows[-1])

    return rows


def retrieval_metrics(row):
    """recall@k and reciprocal rank against the minimal sufficient gold set.

    Two gold chunks, one retrieved scores 0.5, that fraction is what makes
    the multi-section failure visible. None for out-of-scope rows, which are
    scored on whether the answer declines.
    """
    gold = set(row.get("gold_chunk_ids") or [])
    if not gold:
        return {"recall_at_k": None, "reciprocal_rank": None, "n_gold_retrieved": None}

    retrieved = row.get("retrieved_chunk_ids") or []
    hits = gold & set(retrieved)
    ranks = [i for i, c in enumerate(retrieved, start=1) if c in gold]

    return {
        "recall_at_k": len(hits) / len(gold),
        "reciprocal_rank": 1.0 / ranks[0] if ranks else 0.0,
        "n_gold_retrieved": len(hits),
    }


# Saving

# Declared, not inferred: Spark can't infer the element type of an empty array,
# so -> run where every question errored would fail to write.
RUNS_SCHEMA = """
    run_id string, run_label string, variant string,
    question_id string, question string, question_type string, in_scope boolean,
    gold_chunk_ids array<string>, gold_answer string,
    retrieved array<struct<rank:int, chunk_id:string, document:string,
                           section:string, score:double>>,
    retrieved_chunk_ids array<string>,
    context_text string, system_prompt string, user_prompt string,
    answer string, error string,
    answer_endpoint string, embedding_endpoint string,
    top_k int, temperature double, max_tokens int,
    latency_ms int, prompt_tokens int, completion_tokens int,
    created_at timestamp
"""


def save_runs(spark, cfg, rows, table=None):
    """Append rows to the results table. Variants accumulate side by side."""
    if not rows:
        raise ValueError("No rows to save.")

    table = table or cfg.runs_table
    (spark.createDataFrame(rows, schema=RUNS_SCHEMA)
          .write.mode("append").option("mergeSchema", "true").saveAsTable(table))
    return table