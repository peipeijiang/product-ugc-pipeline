# Category: Furniture (家具 / 户外折叠家具)

## 家具 7 维审图（Furniture Framework）

| Field | Check for furniture |
|---|---|
| **家具类型** | Furniture type (folding chair / reclining lounge chair / moon chair / cot / stool / table) |
| **主体材质** | Primary material (fabric sling / canvas / Oxford / tubular steel / aluminium / plastic joints) + finish (matte / gloss / powder-coated) |
| **结构部件** | Structural parts (X-frame, cross-brace, armrest, foot caps, hinges, locking lever, headrest, footrest) — count + position + size |
| **尺寸规格** | Overall dimensions (open length × width × height) + folded size + scale anchor (adult person, smartphone, carry bag) |
| **承载与稳定性** | Foot contact, load path through the frame, whether a stated load rating is visually or textually evidenced — never invent a capacity |
| **功能特征** | Key feature (recline steps, padding, cup holder, side pocket, carry bag) — ONLY if visually verifiable |
| **机械结构** | Folding / reclining mechanism (scissor hinge, multi-position lock, collapsible frame, detachable headrest) — if applicable |

**Special check:**
- **Scale realism:** the furniture must fit one adult occupant; a fully reclined lounge chair reads roughly 1.6–1.9 m long against a standing person
- **Material truth:** sling fabric is taut and flexible rather than a rigid board, metal tubes stay round and thin, plastic joints read matte
- **Gravity and stability:** every foot contacts the ground; no floating legs, no load carried by fabric that obviously cannot bear it
- **Recline realism:** angle changes stay continuous and inside the source-backed range; no phantom ratchet, knob, motor or powered tilt
- **Never treat a folding chair as a rigid cot or flat sun bed** unless the source shows a genuinely flat configuration
- **No phantom parts:** extra cushions, wheels, side tables, canopies, motors, cup holders or branding that the source does not show

## 使用动作（product-centric, 货不对板 verified）

| # | Action | Verifiability | Shot |
|---|---|---|---|
| 1 | Unfold the scissor frame and set it on a flat surface — shows true size vs a standing adult | Verifiable: frame geometry and foot contact visible | Mid-shot, chair + person, 3s |
| 2 | Sit down and recline to a supported angle — shows contact points and frame load path | Verifiable: contact and support surfaces visible | Mid-shot, person + chair, 3s |
| 3 | Show the key feature (integrated headrest / extended leg support / cup holder) | Semi-verifiable: feature must be visible in source photos | Close-up, chair, 2s |
| 4 | Fold and carry the chair in its carry bag — shows portability | Verifiable when a carry bag is evidenced | Mid-shot, person + bag, 2s |

## Reference Sheet 适配（单张宫格）

家具用**一张**宫格参考图表达 5 个角度，上排 3 格 + 下排 2 格；生成后仍须与原图逐格质检。

规格：1024×1024，5 格（上 3 下 2），20px 白色分隔线。

| Panel | 位置 | View | Purpose |
|---|---|---|---|
| 1 | 上左 | Three-quarter full silhouette | 完整轮廓与整体比例 |
| 2 | 上中 | Side profile | 框架几何、坐面倾斜角、脚接触 |
| 3 | 上右 | 45° detail | 铰链 / 调节机构 / 头枕关系 |
| 4 | 下左 | In-use reclined posture | 人与家具的接触位置和真实比例 |
| 5 | 下右 | Scale reference | 与常见物品对比（成人 / 手机 / 收纳袋） |

**Prompt 骨架：**

```
Create a single reference sheet (1024x1024) of {furniture}, 5 panels (3 top + 2 bottom):
Panel 1: three-quarter full silhouette
Panel 2: side profile, frame geometry and foot contact
Panel 3: 45 degree detail, hinge and adjustment mechanism
Panel 4: adult using it in the evidenced posture, true relative scale
Panel 5: beside {adult / phone / carry bag} for scale

Dimensions: {source-backed measurements, otherwise unknown}; match verified relative scale
Style: clean product grid, neutral background, studio light, 20px white borders
Negative: cross-panel distortion, different products across panels, phantom cushions,
wheels, motors or invented brand text
```
