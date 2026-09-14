# Lowest-risk video direction router

Use this router before prompt generation for every product and target video model.
Its job is to find the most commercially useful direction that asks the generator
to perform the least fragile physical reasoning.

## Risk dimensions

Score the advertised actions rather than the product category. The highest-risk
signals are topology and connection changes: install, assemble, insert, thread,
attach, detach, reverse, fold, inflate or join. Precision contact, occlusion,
deformable materials, multiple dependent steps, multiple objects and an unseen
intermediate state add risk.

The routing ladder is:

| Risk | Generated-video direction |
|---|---|
| Low | One product, one evidenced action, one camera move |
| Medium | Product pre-positioned; show one simple contact or use action |
| High | Keep one verified endpoint configuration; convey setup with an external hard cut |
| Critical | Result-first static reveal, detail/scale proof and creator reaction; use real source footage if the mechanism itself must be shown |

For high/critical risk, start and end keyframes must preserve the same product
topology. Do not give a first/last-frame model two different configurations and
then tell it to hard-cut: the model may still interpolate between them. Generate
endpoint assets separately and make the cut in editing.

## Model profiles

Model profiles adjust creator and camera motion budgets, never the product-evidence
rules. Seedance 2.0 and MiniMax H3 may receive moderate creator/camera motion;
Omni Flash and VEO use a more conservative motion budget. A protected Omni route
uses only a regenerated ready-state storyboard and the identity grid; it omits the
operation grid so conflicting configurations cannot steer the model. No vendor capability
claim permits an unobserved connection or topology change.

## Research basis

- [OSCBench](https://github.com/iLearn-Lab/ACL26-OSCBench) separates state-change
  accuracy from temporal consistency and finds complex hand-object interactions
  and novel/composed changes especially difficult.
- [VideoPhy](https://github.com/Hritikbansal/videophy) evaluates semantic adherence
  and physical commonsense jointly; strong visual quality does not imply correct physics.
- [T2V-CompBench](https://github.com/KaiyueSun98/T2V-CompBench) separately evaluates
  action binding, motion binding, object interaction, numeracy and attribute consistency.
- [WorldModelBench](https://github.com/WorldModelBench-Team/WorldModelBench) checks
  conservation of mass/solid form, impenetrability and gravity in addition to instruction following.

The implementation uses their evaluation dimensions as a conservative routing
heuristic. It does not copy benchmark data, evaluator weights or model rankings.
