# Category: Home Tools (厨房/家居工具)

## 工具7维审图（Tools Framework）

| Field | Check for home tools |
|---|---|
| **工具类型** | Tool type (knife / peeler / grater / strainer / spatula / whisk / measuring cup / scissors / opener) |
| **主体材质** | Primary material (stainless steel / plastic / silicone / wood / ceramic) + finish (matte / glossy / brushed / textured) |
| **功能部件** | Functional parts (blade / teeth / holes / bristles / measuring marks / grip zone / hinge) — count + position + size |
| **尺寸规格** | Overall dimensions (length × width × height) + scale anchor (hand width / credit card / common food item) |
| **手柄设计** | Handle type (ergonomic grip / straight / loop / no handle) + grip texture (ribbed / smooth / rubberized) |
| **功能特征** | Key feature (sharpness / flexibility / heat resistance / non-stick / dishwasher safe) — ONLY if visually verifiable |
| **机械结构** | Mechanical parts (hinge / spring / locking mechanism / collapsible / detachable) — if applicable |

**Special check:**
- **Scale realism:** tool size must match real-world kitchen tools (8–12cm paring knife, 25–30cm spatula)
- **Material truth:** stainless steel looks metallic with reflections, silicone looks matte/flexible, wood has grain
- **Functional geometry:** blade angle correct, strainer holes evenly spaced, measuring marks legible
- **Hand interaction:** grip position anatomically possible, tool weight distribution realistic
- **No phantom parts:** no extra blades, no invented brand text, no impossible hinges

## 食材交互规则 (Food Interaction Rules)

| Tool Type | Allowed Food Items | Physics Requirements | Forbidden |
|---|---|---|---|
| **Knife** | Carrot, apple, cucumber, bread, tomato | Blade enters food, clean cut line, food separates | Cutting through bone/steel, blade bending impossibly |
| **Peeler** | Apple, potato, carrot, cucumber | Blade angle 15–30°, peel comes off in ribbon | Peeling raw meat, peel teleporting off |
| **Grater** | Cheese, carrot, ginger | Food pressed against holes, shreds emerge | Grating liquid, shreds without contact |
| **Strainer** | Pasta, rice, vegetables in water | Water flows through holes, food stays in strainer | Water floating upward |
| **Spatula** | Pancake, egg, stir-fry vegetables | Spatula slides under food, food lifts | Spatula phasing through food |

## Detail actions (product-centric, 货不对板 verified)

| # | Action | Verifiability | Shot |
|---|---|---|---|
| 1 | Pick up tool with correct grip (thumb+fingers on handle, tool balanced) — shows true size vs hand scale | ✅ Verifiable: tool dimensions measurable | Mid-shot, hand + tool, 2s |
| 2 | Demonstrate primary function on appropriate food item (knife cutting carrot / peeler removing apple skin) — shows functional geometry + interaction realism | ✅ Verifiable: functional part visible. Physics MUST be realistic. | Close-up, hand + tool + food, 4s |
| 3 | Show key feature (flexible silicone spatula bending / measuring cup with clear marks) — proves advertised feature | ⚠️ Semi-verifiable: feature must be visible OR user-confirmed | Close-up, tool, 3s |
| 4 | Place tool in kitchen context (on cutting board / in drawer organizer) — shows realistic use scenario | ✅ Verifiable: tool size allows placement | Mid-shot, tool + context, 2s |

## Reference Sheet 适配（单张宫格）

Home tools 用**一张**宫格参考图表达 5 个角度，上排 3 格 + 下排 2 格；生成后仍须与原图逐格质检。

规格：1024×1024，5 格（上 3 下 2），20px 白色分隔线，底部标注尺寸锁定。

| Panel | 位置 | View | Purpose |
|---|---|---|---|
| 1 | 上左 | Top-down flat-lay | 完整轮廓，所有部件可见 |
| 2 | 上中 | Side profile | 刀刃几何角度，手柄曲线 |
| 3 | 上右 | 45° detail | 握持区 + 功能部件关系 |
| 4 | 下左 | In-use grip | 手持工具，与手的比例 |
| 5 | 下右 | Scale reference | 与常见物品（信用卡 / 苹果）对比 |

**Prompt 骨架：**

```
Create a single reference sheet (1024×1024) of {tool}, 5 panels (3 top + 2 bottom):
Panel 1: top-down flat-lay, full silhouette
Panel 2: side profile, blade angle + handle curve
Panel 3: 45° detail, grip zone + functional part
Panel 4: hand holding tool, correct grip, scale vs hand
Panel 5: tool beside {credit card / apple} for scale

Dimensions: {source-backed measurements, otherwise unknown}; match verified relative scale
Style: clean product grid, white background, studio light, 20px white borders
Negative: cross-panel distortion, different tools across panels, phantom blades,
invented brand text
```
