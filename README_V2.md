# Product UGC Pipeline v2

V2 activates when `identity_lock/` exists. It adds factorized product classification, one category-aware identity grid, a source-backed usage ledger, an operation grid for supported state-changing products, provenance validation and evidence-based QC.

The v2 video path is identical for every product: Omni Flash with `omni-reference`.

## Reference set

1. Chronological storyboard: complete 0–10 second scene progression.
2. Identity grid: exact SKU and physical truth.
3. Optional operation grid: only source-supported configuration guidance that passed QC.

The adapter validates current hashes, provenance, QC and the three-reference limit before a paid submission. References are all-purpose; none is assigned a timeline endpoint.

## Required order

```text
complete extraction
→ full image analysis
→ product brief
→ category classification
→ identity grid and usage ledger
→ identity/operation QC
→ UGC prompts
→ chronological storyboard
→ storyboard QC
→ Omni Flash omni-reference video
→ sampled-frame video QC
```

See `SKILL.md` and the matching files in `references/` for complete rules.
