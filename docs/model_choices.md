# Model choices

Decided: 2026-10-27. All models run on Databricks.

## The models

| What | Model | Name in Unity Catalog | Name in the code |
|---|---|---|---|
| Embedding | GTE Large (English) | `system.ai.gte-large-en` | `databricks-gte-large-en` |
| Answers (A and B) | Llama 3.3 70B Instruct | `system.ai.meta-llama-3-3-70b-instruct` | `databricks-meta-llama-3-3-70b-instruct` |
| Judge | gpt-oss-120b | `system.ai.gpt-oss-120b` | `databricks-gpt-oss-120b` |

## Why we picked them

- gte-large-en: our rules are in English. It can read 8,192 tokens, so no part gets cut.
  bge-large-en can only read 512 tokens, so we did not use it.
- Llama 3.3 70B: it is good at following instructions. B needs that.
  Many RAG projects use it. It does not change during our project.
- gpt-oss-120b: it is not the same kind of model as Llama. A judge can like its own
  kind of answers more, so we picked a different one. We check the judge by hand.

## Not picked

- `deepseek-v4-flash`: it had a warning in AI Gateway.
- `databricks-genie`: a Databricks helper, not a normal model.

## Test without RAG

We asked Llama 3.3 70B in the Playground, without the rules:

1. "How many paid vacation days do employees at Nordljus Consulting AB have?"
   It did not know. The right answer is 30.
2. "How many paid vacation days do employees in Sweden get?"
   It said 25. That is the Swedish law, not Nordljus. It also made up "16 public holidays".

So the model needs the company's rules to answer right.
