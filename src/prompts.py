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

# Verbatim from data/policies/04_ai_policy.md, section "Information classes".
# The hard rules refer to these classes, so the rules can't be applied without
# them (dev_03 and dev_07 in the first Variant B dev run, 2026-11-15).
INFORMATION_CLASSES = """\
- Public: information that has already been published, for example on nordljus.example.
- Internal: information for employees, for example internal routines and meeting notes without client details.
- Confidential: client data, contracts, quotes, financial information and personal data.
- Strictly Confidential: sensitive personal data (for example health), payroll lists, security information and information that the client has marked as secret."""


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


def build_system_prompt_b(rules, refusal, citations):
    """Variant A's prompt plus the Variant B features that are switched on."""
    parts = [SYSTEM_PROMPT_A]
    if rules:
        parts.append(
            "Hard rules from [Policy on the Use of AI at Work > Hard rules]. "
            "They always apply and must never be broken:\n" + HARD_RULES
        )
        parts.append(
            "Information classes from [Policy on the Use of AI at Work > Information classes]. "
            "The hard rules refer to these classes:\n" + INFORMATION_CLASSES
        )
    if refusal:
        parts.append(REFUSAL_INSTRUCTION)
    if citations:
        parts.append(CITATION_INSTRUCTION)
    return "\n\n".join(parts)


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


# B is the full variant. The B_* variants switch on one feature each (ablation),
# so the effect of each feature can be measured on its own.
_VARIANTS = {
    "A": (SYSTEM_PROMPT_A, build_user_prompt_a),
    "B": (build_system_prompt_b(rules=True, refusal=True, citations=True), build_user_prompt_b),
    "B_rules": (build_system_prompt_b(rules=True, refusal=False, citations=False), build_user_prompt_a),
    "B_refusal": (build_system_prompt_b(rules=False, refusal=True, citations=False), build_user_prompt_a),
    "B_citations": (build_system_prompt_b(rules=False, refusal=False, citations=True), build_user_prompt_b),
}


def get_prompts(variant):
    """Return (system_prompt, user_prompt_builder)."""
    if variant not in _VARIANTS:
        raise ValueError(f"Unknown variant {variant!r}. Expected one of {sorted(_VARIANTS)}.")
    system_prompt, builder = _VARIANTS[variant]
    if system_prompt is None:
        raise NotImplementedError(f"Variant {variant} has no prompt yet.")
    return system_prompt, builder