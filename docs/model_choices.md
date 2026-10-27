# Model choices

Decided: 2026-10-27. All models are Databricks-hosted foundation models accessed through Unity Gateway.

| Role | Model | Endpoint name |
|---|---|---|
| Embedding | GTE Large (English) | `system.ai.gte-large-en` |
| Answer model (Variant A and B) | Llama 3.3 70B Instruct | `system.ai.meta-llama-3-3-70b-instruct` |
| LLM judge | gpt-oss-120b | `system.ai.gpt-oss-120b` |

## Rationale

- **Embedding: gte-large-en.** The policy documents are in English. Supports up to 8,192 tokens per input, so no policy section is truncated. bge-large-en was not chosen because of its 512-token limit.
- **Answer model: Llama 3.3 70B Instruct.** Strong instruction following, which Variant B depends on (citations, refusal, hard rules). Widely used in RAG research. Stable version (not updated during the project), which supports reproducibility.
- **Judge: gpt-oss-120b.** A different model family from the answer model, to reduce the risk of self-preference bias where a judge rates answers from its own model family higher. The judge is validated against manual assessment of a sample.

## Rejected

- `deepseek-v4-flash`: marked with a warning in AI Gateway (possibly deprecated or limited).
- `databricks-genie`: a Databricks assistant, not a general model.

## Baseline observation (Playground, no RAG)

Asked Llama 3.3 70B without any policy context:

1. "How many paid vacation days do employees at Nordljus Consulting AB have?" – The model said it has no information about the company. Correct answer according to the policy: 30.
2. "How many paid vacation days do employees in Sweden get?" – The model answered 25 (statutory minimum, wrong for Nordljus) and added an incorrect detail about "16 public holidays".

This illustrates why answers must be grounded in the company's documents.