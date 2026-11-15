"""Prompts for the two variants. The A/B difference will live here, nowhere else."""

CONTEXT_SEPARATOR = "\n\n---\n\n"

SYSTEM_PROMPT_A = (
    "You are an assistant that answers employee questions about the internal policies "
    "of Nordljus Consulting AB. Use the context below to answer the question."
)

# Verbatim from data/policies/04_ai_policy.md, section "Hard rules".
# Always in Variant B's system prompt, so the rules apply even when
# retrieval misses that section (see dev_03 in docs/experiment_log.md).
HARD_RULES = """\
1. Strictly Confidential information must never be entered into any AI tool.
2. Confidential information may only be entered into Nordljus Assistant.
3. Personal data about clients, candidates or colleagues must not be entered into AI tools unless it has first been removed or anonymised, with the exception of Nordljus Assistant.
4. AI must never make decisions about hiring, dismissal, salary or the assessment of individual people. AI may be used as support, but the decision must always be made by a human.
5. Passwords, API keys and other login credentials must never be entered into any AI tool."""


# Fixed sentence, so a refusal can be counted exactly instead of interpreted.
REFUSAL_SENTENCE = "The policies do not cover this question."

REFUSAL_INSTRUCTION = (
    "Answer only from the information you have been given. Do not use general "
    "knowledge and do not guess. If it does not contain the answer, reply with exactly: "
    f'"{REFUSAL_SENTENCE}" Then suggest contacting HR at hr@nordljus.example.'
)

CITATION_INSTRUCTION = (
    "After each statement, cite its source in square brackets using the label shown "
    "above the excerpt, for example [Policy on the Use of AI at Work > Hard rules]. "
    "Only cite labels you have been given. Never invent a source."
)


# TODO: citations, refusal -> insufficient context, hard AI rules.
# Excerpts will need labelling here, to be cited...
SYSTEM_PROMPT_B = None


def build_user_prompt_a(question, chunks):
    """Unlabelled excerpts: labelling them would already nudge towards citing."""
    context = CONTEXT_SEPARATOR.join(chunk["text"] for chunk in chunks)
    return f"Context:\n{context}\n\nQuestion: {question}"


def build_user_prompt_b(question, chunks):
    """Each excerpt gets a label to cite, built from its document and section."""
    context = CONTEXT_SEPARATOR.join(
        f"[{chunk['document']} > {chunk['section']}]\n{chunk['text']}" for chunk in chunks
    )
    return f"Context:\n{context}\n\nQuestion: {question}"


_VARIANTS = {
    "A": (SYSTEM_PROMPT_A, build_user_prompt_a),
    "B": (SYSTEM_PROMPT_B, build_user_prompt_b),
}


def get_prompts(variant):
    """Return (system_prompt, user_prompt_builder)."""
    if variant not in _VARIANTS:
        raise ValueError(f"Unknown variant {variant!r}. Expected one of {sorted(_VARIANTS)}.")
    system_prompt, builder = _VARIANTS[variant]
    if system_prompt is None:
        raise NotImplementedError(f"Variant {variant} has no prompt yet.")
    return system_prompt, builder