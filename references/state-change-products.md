# State-changing products: folding, assembly and installation

This reference applies when the advertised use changes the product's configuration:
fold/unfold, collapse/deploy, assemble/disassemble, install/remove, attach/detach,
extend/retract, open/close, zip/unzip or lock/unlock.

## Why the identity grid is insufficient

An identity grid describes appearance at a few static views. It does not establish
which part moves, what stays fixed, where the hand contacts, how two parts connect,
or which intermediate shapes are physically valid. Asking a video model to infer
those facts from two endpoints commonly produces morphing, duplicated parts,
crossed tubes, wrong hinges, wrong attachment locations or a plausible-looking
mechanism that the product does not have.

The pipeline therefore separates three jobs:

1. `identity_lock/reference_sheet.png` locks product type, SKU, shape and part inventory.
2. `usage_poses/reference_sheet.png` locks evidenced configuration states and only
   those transition poses directly supported by a motion source or instruction diagram.
3. The chronological ad storyboard locks scene order, people, camera and commercial beat.

For Omni reference mode these are images 2, 3 and 1 respectively. For first/final
frame video models the operation sheet guides Image2 keyframe creation; the video
still receives the generated start and end frames.

## Product cognition contract

`product_brief.json` must always contain `state_change_contract`. Non-transforming
products use `required: false` plus a product-specific reason. Transforming products
use `required: true` and the following structure:

```json
{
  "required": true,
  "mechanism_type": "folding",
  "part_invariants": [
    {"part": "left X-frame", "count": 1, "evidence": "images/main-05.webp"}
  ],
  "connections": [
    {"parts": ["front tube", "cross brace"], "type": "pivot", "evidence": "images/detail-03.jpg"}
  ],
  "states": [
    {"state_id": "collapsed", "visible_configuration": "...", "evidence": "images/main-06.webp"},
    {"state_id": "open_locked", "visible_configuration": "...", "evidence": "images/main-05.webp"}
  ],
  "transitions": [
    {
      "transition_id": "deploy",
      "from_state": "collapsed",
      "to_state": "open_locked",
      "evidence_level": "state_pair_only",
      "render_policy": "hard_cut_only",
      "evidence": "Only the two endpoint photos above are available",
      "forbidden_intermediates": ["crossed frame tubes", "floating feet", "duplicated braces"]
    }
  ]
}
```

Evidence levels and rendering policy:

| Evidence | Meaning | Allowed rendering |
|---|---|---|
| `direct_motion` | Source video visibly shows the complete action | `continuous_allowed` when all motion fields are recorded |
| `instruction_diagram` | Source-backed ordered diagrams show contact and motion | `continuous_allowed` when the diagrams resolve the path |
| `state_pair_only` | Only before/after configurations are visible | `hard_cut_only` or `omit_transition`; never invent a midpoint |

Directly evidenced transitions also need `actor_action`, `contact_points`,
`moving_parts`, `fixed_parts` and `completion_cue`. Every transition needs a
non-empty `forbidden_intermediates` list. A generated reference sheet remains
secondary guidance and never upgrades weak evidence.

## QC failure taxonomy

Use the mistake types independently; one clean-looking final frame cannot average
away a structural failure:

- wrong product class: source is a sleeping bag but target is a chair;
- wrong order: later attachment or locking happens before its prerequisite;
- wrong position: correct parts connect at the wrong site or orientation;
- extra action: a detach/open/unlock action occurs when it should not;
- inventory drift: a part appears, disappears, duplicates, recolours or changes side;
- invalid motion path: tubes cross, fabric becomes rigid, a hinge moves on the wrong axis;
- incomplete state: the lock/contact/support cue for the target state is absent;
- support failure: feet, load paths, gravity or hand contacts are physically inconsistent.

## GitHub research basis

- [IKEA ASM Dataset](https://github.com/IkeaASM/IKEA_ASM_Dataset) combines atomic
  actions, object segmentation/tracking and human pose for furniture assembly. Its
  separation of action, object and pose motivates checking the product, active part
  and hand contact as distinct evidence.
- [Assembly101 annotations](https://github.com/assembly-101/assembly101-annotations)
  provide fine and coarse procedural labels. The companion
  [mistake-detection annotations](https://github.com/assembly-101/assembly101-mistake-detection)
  represent actions as verb plus two working objects and distinguish wrong order,
  wrong position and unnecessary detach actions. This is the basis for the QC taxonomy.
- [Articulate Anything](https://github.com/vlongle/articulate-anything) accepts text,
  image or video and models articulated objects with PartNet-Mobility/URDF concepts.
  The pipeline borrows the lightweight idea of parts, connections, states and motion
  constraints without adding its heavy 3D retrieval/simulation stack.
- [PartNet-Mobility utilities](https://github.com/r-pad/partnet_mobility_utils) expose
  articulated object links and joints through SAPIEN, PyBullet and Trimesh. They are
  useful for future CAD-backed products, but ecommerce photos rarely justify claiming
  a precise joint axis or range.
- [SAM 2](https://github.com/facebookresearch/sam2) can propagate object masks through
  video; [CoTracker](https://github.com/facebookresearch/co-tracker) tracks selected
  points. They are optional future motion-QC backends for detecting part loss,
  duplication and broken contact. They are not installed as production dependencies:
  SAM 2 expects a substantial PyTorch/CUDA stack, while most CoTracker code/checkpoints
  are non-commercially licensed.

The implementation uses these public projects as design references. It does not copy
their datasets, weights or source code into this skill.
