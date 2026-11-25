"""Small measures computed on stored experiment rows."""

from src.prompts import REFUSAL_SENTENCE


def over_refusal(rows):
    """How often the answer refuses on questions that actually have an answer.

    Counts only rows with in_scope True. Returns n_in_scope, n_refused and share
    (None if there are no in-scope rows).
    """
    in_scope = [row for row in rows if row.get("in_scope")]
    n_refused = sum(REFUSAL_SENTENCE in (row.get("answer") or "") for row in in_scope)
    share = n_refused / len(in_scope) if in_scope else None
    return {"n_in_scope": len(in_scope), "n_refused": n_refused, "share": share}


if __name__ == "__main__":
    # Self-test
    rows = [
        {"in_scope": True, "answer": "Permanent employees get 30 vacation days."},
        {"in_scope": True, "answer": REFUSAL_SENTENCE},
        {"in_scope": True, "answer": "Notify your manager before 09:00."},
        {"in_scope": False, "answer": REFUSAL_SENTENCE},  # correct refusal, not counted
    ]
    result = over_refusal(rows)
    assert result["n_in_scope"] == 3 and result["n_refused"] == 1, result
    assert abs(result["share"] - 1 / 3) < 1e-9, result
    print("OK", result)