"""Prompts for the two variants. The A/B difference will live here, nowhere else."""

CONTEXT_SEPARATOR = "\n\n---\n\n"

SYSTEM_PROMPT_A = (
    "You are an assistant that answers employee questions about the internal policies "
    "of Nordljus Consulting AB. Use the context below to answer the question."
)

# TODO: citations, refusal -> insufficient context, hard AI rules.
# Excerpts will need labelling here, to be cited...
SYSTEM_PROMPT_B = None


def build_user_prompt_a(question, chunks):
    """Unlabelled excerpts: labelling them would already nudge towards citing."""
    context = CONTEXT_SEPARATOR.join(chunk["text"] for chunk in chunks)
    return f"Context:\n{context}\n\nQuestion: {question}"


def build_user_prompt_b(question, chunks):
    raise NotImplementedError("Variant B is W46.")


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