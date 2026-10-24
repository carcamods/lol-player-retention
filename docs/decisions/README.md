# Decisions

Architecture decision records: one decision per file, never rewritten. A reversed decision gets
a new ADR, and the old one is marked superseded. Read the index, then only the ADR you need.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-new-repo-fresh-history.md) | Start a new repo with a fresh history; the 2024 repo leaked credentials | Accepted |
| [0002](0002-static-snapshot-site.md) | Public demo is a static snapshot site; live lookup only via CLI or a later production key | Accepted |
| [0003](0003-point-in-time-labels.md) | Point-in-time features and labels; the 2024 leak explained | Accepted |
| [0004](0004-neural-nets-on-colab.md) | Neural nets (MLP, GRU) in PyTorch, trained on Colab; keep Python 3.12 support | Accepted |
| [0005](0005-collection-design.md) | Collection: ladder sampling, weekly buckets, SQLite cache, failure policy; pilot results | Accepted |
| [0006](0006-eligible-population.md) | Eligible = played in the 28 days before the cutoff; timing rules per column; forward test | Accepted |
| [0007](0007-layered-repo-memory.md) | Layered repo memory for AI-assisted development: map, module context, ADRs, checkpoint | Accepted; file names amended by 0009 |
| [0008](0008-classical-model-evaluation.md) | Classical models: held-out players at the latest cutoff, selection and Platt calibration inside training, bootstrap comparison with the recency rule | Accepted |
| [0009](0009-agents-md.md) | Context files are named `AGENTS.md`, the cross-tool format, instead of `CLAUDE.md` | Accepted |
| [0010](0010-break-features.md) | Break features tried under a rule set in advance; not met, so removed | Accepted |

## Template

```markdown
# NNNN: Title

**Status:** Accepted, YYYY-MM-DD

## Context

What prompted the decision, with the facts that matter.

## Decision

What we chose, specific enough to check against the code.

## Consequences

What follows from it, including costs and what it rules out.
```
