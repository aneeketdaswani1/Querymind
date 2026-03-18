# Evaluation Comparison

| Run | Standard Cases | Adversarial Cases | Execution Accuracy | Result Accuracy | Avg SQL Similarity | Safety Pass Rate |
|---|---:|---:|---:|---:|---:|---:|
| Full (all cases, previous run) | 50 | 20 | 0.0% | 0.0% | 0.0% | 80.0% |
| Active key smoke (this run) | 1 | 1 | 0.0% | 0.0% | 0.0% | 100.0% |

## Quota Status

- Active-key smoke run failed SQL generation with `429 RESOURCE_EXHAUSTED` from Gemini.
- A full keyed run would currently repeat failures until quota/billing is restored.
