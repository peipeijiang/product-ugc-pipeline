# Category: Pet Tools (宠物工具)

## 工具7维审图（继承 Tools Framework，宠物特化）

| Field | Check for pet tools |
|---|---|
| **工具类型** | Tool type (brush / comb / nail clipper / leash / collar / bowl / toy ball / grooming scissors / de-shedding tool) |
| **主体材质** | Primary material (plastic / metal / rubber / fabric / silicone / stainless steel) + finish |
| **功能部件** | Functional parts (bristles / teeth / blade / clasp / mesh / rim) — count + position + density |
| **尺寸规格** | Overall dimensions + scale anchor (hand width / cat/dog size reference) |
| **手柄/握持区** | Handle type + grip texture — if applicable |
| **宠物安全特征** | Safety features (rounded tips / soft bristles / safety guard / quick-release clasp) — ONLY if visible |
| **机械结构** | Mechanical parts (spring clipper / retractable leash / collapsible bowl) — if applicable |

**Special check (宠物工具专项):**
- **Pet scale match:** tool size appropriate for target pet (small brush for cat, large brush for golden retriever)
- **Bristle/teeth density:** spacing realistic, not too dense or sparse
- **Pet comfort:** no sharp edges near pet contact zones, bristles not poking into skin
- **Human-pet interaction:** hand position allows control, pet posture natural (not forced/uncomfortable)
- **No phantom features:** no invented "anti-hair-loss formula", no glowing tech features unless visible in source

## 宠物交互规则 (Pet Interaction Rules)

| Tool Type | Allowed Pet Subjects | Safety Requirements | Forbidden |
|---|---|---|---|
| **Brush / Comb** | Cat, dog (breed-appropriate size) | Gentle stroke direction (with fur grain), bristles/teeth not digging into skin, pet relaxed | Brushing against grain aggressively, pet showing pain (ears back, growling), bristles disappearing into skin |
| **Nail Clipper** | Cat paw, dog paw (size-appropriate) | Blade positioned on nail tip only (not quick/pink part), paw held gently, pet calm | Blade near quick (red/pink zone), pet struggling violently, blood visible |
| **Leash / Collar** | Dog (size-appropriate), cat (if harness type) | Collar snug but not tight (2-finger rule), leash attached to collar ring, pet walking naturally | Collar choking tight, leash pulling pet off ground, pet gasping |
| **Food/Water Bowl** | Cat, dog, small pet | Bowl stable on ground, pet head position natural (not neck twisted), bowl size appropriate | Bowl tipping over defying physics, pet head phasing through bowl, wrong size |
| **Toy** | Cat, dog, small pet | Pet playing naturally (pawing, biting, chasing), toy size appropriate (no choking hazard) | Toy too large/small for species, pet ignoring toy entirely, pet choking |

## 宠物舒适度检查 (Pet Comfort Check)

| Pet Body Language | Comfort Level | Usable in Video? |
|---|---|---|
| Relaxed posture, normal breathing, eyes soft, ears neutral | ✅ Comfortable | YES |
| Leaning into grooming, purring (cat), tail wagging gently (dog) | ✅ Enjoying | YES (ideal) |
| Sitting still, tolerating, not resisting | ✅ Accepting | YES |
| Ears pinned back, tail tucked, wide eyes, body tense | ❌ Uncomfortable | NO |
| Trying to escape, pulling away, growling, hissing | ❌ Distressed | NO (re-shoot required) |
| Limp/sedated (professional grooming) | ⚠️ Context-dependent | YES if clearly professional setting |

## Detail actions (product-centric, 货不对板 verified)

| # | Action | Verifiability | Shot |
|---|---|---|---|
| 1 | Pick up tool with correct grip (handle/body held comfortably, tool balanced) — shows size vs hand | ✅ Verifiable: tool dimensions measurable. Use "slow controlled" qualifier. | Mid-shot, hand + tool, 2s |
| 2 | Demonstrate primary function on appropriate subject (brush strokes on long fur / comb through cat coat / nail clipper on paw / leash attached to collar) — shows functional realism | ✅ Verifiable: functional parts visible. Pet subject MUST be appropriate. Pet body language MUST be calm. Use "gentle slow" qualifier. | Close-up, hand + tool + pet, 4–6s |
| 3 | Show key feature (de-shedding tool removing loose fur / retractable leash extending/retracting / brush self-cleaning button) — proves advertised feature | ⚠️ Semi-verifiable: feature must be visible OR user-confirmed. Do NOT claim "painless" unless pet appears comfortable. | Close-up, tool + result, 3s |
| 4 | Place tool in pet context (on pet bed / in grooming station / with other pet supplies) — shows realistic use scenario | ✅ Verifiable: tool size allows this placement. Props realistic. | Mid-shot, tool + pet context, 2s |

**Safety disclaimer:** 
All pet tools must be used safely. Do not generate videos showing:
- Sharp blades near pet eyes/ears/nose
- Tight collars restricting breathing
- Pets in obvious distress
- Unsafe human grip (pulling fur, bending limbs unnaturally)
- Choking hazards

## Reference Sheet 适配（单张宫格）

Pet tools 用**一张**宫格参考图覆盖 5 个角度，上排 3 格 + 下排 2 格。单张生成保证各格工具身份一致。

规格：1024×1024，5 格（上 3 下 2），20px 白色分隔线，底部标注尺寸与适配宠物体型。

| Panel | 位置 | View | Purpose |
|---|---|---|---|
| 1 | 上左 | Flat-lay with scale | 完整轮廓，功能部件可见 |
| 2 | 上中 | Side profile | 人机工学、梳齿长度、刀刃角度 |
| 3 | 上右 | 45° detail | 握持区 + 功能部件 |
| 4 | 下左 | In-use with pet | 手持工具作用于宠物毛发/爪部，宠物平静 |
| 5 | 下右 | Scale reference with pet | 与宠物体型对比 |

**Prompt 骨架：**

```
Create a single reference sheet (1024×1024) of {pet tool}, 5 panels (3 top + 2 bottom):
Panel 1: flat-lay, full silhouette + functional parts
Panel 2: side profile, bristle length / blade angle
Panel 3: 45° detail, grip zone
Panel 4: hand using tool on {cat/dog} fur, pet relaxed (ears forward, eyes soft)
Panel 5: tool beside pet for size appropriateness

Dimensions locked: {exact cm} — scale authority 1.0
Target pet: {species + size range}
Style: clean product grid, neutral background, 20px white borders
Negative: cross-panel distortion, pet distress (ears back, wide eyes, escaping),
wrong species, teeth digging into skin, phantom electric features
```

**可选：宠物舒适度宫格**

如需强化宠物体态控制，再出**一张** 1×3 宫格：放松 / 享受 / 接受三种体态，同一宠物身份，作为 `@pet_ref{0.70}` 使用。
