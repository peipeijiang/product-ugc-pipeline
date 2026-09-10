# Category: Electronics (电子产品 / 搭积木玩具)

## 电子产品8维审图（全新框架）

| Field | Check for electronics |
|---|---|
| **产品身份** | Product type (earbuds / smartwatch / power bank / speaker / keyboard / mouse / charger / cable / toy blocks) + brand-agnostic description |
| **外观轮廓** | Silhouette (shape / size / proportions) — must not morph (圆形→方形 / 扁平→鼓起) |
| **尺寸规格** | Exact dimensions in mm/cm + scale anchor (hand width / AA battery / credit card / smartphone) |
| **材质表面** | Material (plastic / metal / silicone / fabric) + finish (matte / glossy / brushed / textured) |
| **功能区域** | Buttons / ports / sensors / display / LED indicators — count + position + size |
| **功能状态** | Power on/off / screen content / LED color / charging indicator / connection status |
| **交互类型** | Touch / press / slide / twist / plug-in / snap-on — physically possible hand positions only |
| **配件组件** | Charging case / cable / adapter / manual / packaging — shown separately or integrated |

**Special check:**
- **Scale lock:** product size MUST match real-world dimensions. Use hand/finger as scale reference in every shot.
- **Port/button accuracy:** count must match (2 USB-C ports cannot become 3). Position must not shift.
- **Interaction physics:** finger touch area correct (触摸板 not 按压坑), cable bend radius realistic, plug orientation correct.
- **LED/screen truth:** only show states visible in source photo OR explicitly user-confirmed. Do not invent screen content.
- **No phantom parts:** do not add cables/wires/motors/chambers/hinges/text not in source photo.
- **Assembly logic (for toy blocks):** connection points must align, pieces must interlock correctly, gravity must work.

## 交互类型锁定表 (Interaction Type Lock Table)

| Product Element | Correct Interaction | Wrong Interaction (禁止) |
|---|---|---|
| **Touchpad/Touch sensor** | Fingertip lightly resting on flat surface, no depression | Finger pressing into surface, visible dent |
| **Physical button** | Finger pressing, button visibly depressed | Finger hovering over button claiming it was pressed |
| **USB-C/Lightning port** | Plug inserted with correct orientation (USB-C symmetrical, Lightning one-way), visible alignment | Plug backwards, plug tilted/bent, plug halfway in |
| **Wireless charger pad** | Phone lying flat on pad, screen up (unless stand type) | Phone standing upright on flat pad |
| **Earbud charging case** | Lid opening with visible hinge, earbuds nested inside | Earbuds floating above case, lid teleporting open |
| **Toy block studs** | Piece aligned → downward pressure → audible/visual snap → pieces locked | Pieces hovering near each other claiming they are connected |

## Detail actions (product-centric, 货不对板 verified)

| # | Action | 货不对板 verifiability | Shot |
|---|---|---|---|
| 1 | **Pick up product with correct grip (thumb+index on body, not blocking ports/buttons)** — shows true size vs hand scale | ✅ Verifiable: product dimensions measurable in flat-lay. Hand grip must be anatomically possible. Use "slow controlled" qualifier. | Mid-shot, hand + product, 2s |
| 2 | **Demonstrate primary interaction (touch sensor / press button / plug cable / snap blocks together)** — shows correct interaction type + hand position | ✅ Verifiable: interaction type visible in source photo (touch sensor=flat surface / button=raised element / port=opening / block connection points=visible studs). Interaction must match physics (touch≠press). | Close-up, hand + interaction zone, 3s |
| 3 | **Show functional state change (power on → LED lights / screen wakes / charging indicator)** — shows verified function only | ⚠️ Semi-verifiable: only show states visible in source photo OR user-confirmed. Do NOT invent screen content/LED colors. If unverified, skip this action. | Close-up, product, 2s |
| 4 | **Place product in use context (on desk / in pocket / connected to phone)** — shows realistic scale + daily use scenario | ✅ Verifiable: product size allows this placement. Props (phone/desk) must not dwarf or miniaturize the product. | Mid-shot, product + context, 3s |
| 5 | **Toy blocks: build/assemble motion (pick piece → align → snap together → show completed structure)** — shows connection logic + assembly satisfaction | ✅ Verifiable: connection points (studs/holes) visible in flat-lay. Assembly must obey physics (pieces interlock, structure is stable, gravity works). Use "slow deliberate" qualifier. | Mid-shot, hands + blocks, 5–8s |

**Screen/LED content rule:** ONLY show screen content or LED colors that are visible in the source photo OR explicitly confirmed by user. Do NOT invent app UI, notification icons, battery percentage, time displays, or decorative graphics.

## Reference Sheet 适配（单张 3 行×2 列宫格）

Electronics 用**一张** 3 行 × 2 列竖版宫格参考图表达 6 个角度/关系。生成图仍可能在格间画错，必须与原图逐格质检。宫格指导场景首尾帧，VEO 接收的是首尾帧；没有证据的角度应复用已有视角。

规格：1024×1536（2:3 竖版），6 格等分，20px 白色分隔线。产品名与尺寸锁定值保存在 `manifest.json` / `product_brief.json`，不要求图片模型在宫格内渲染文字，以免乱码污染后续视频参考。

| Panel | 位置 | Angle | Purpose |
|---|---|---|---|
| 1 | 上左 | Front view | 主身份锁（轮廓、尺寸、材质） |
| 2 | 上右 | 45° angle | 厚度与曲面，侧面按键/接口 |
| 3 | 中左 | Side profile 90°（仅有来源证据时；否则重复已知 45°） | 接口数量 + 位置验证，禁止补画未知侧后结构 |
| 4 | 中右 | Top view | 按键布局，LED 指示灯位置 |
| 5 | 下左 | In-use close-up | 手持比例锁，交互区 |
| 6 | 下右 | Scale reference | 绝对尺寸锚（AA 电池 / 信用卡 / 手机） |

**Prompt 骨架：**

```
Create a 3-row × 2-column product reference sheet (1024×1536, portrait) of {product}:
Panel 1 (top-left): front view, primary functional surface
Panel 2 (top-right): 45° angle, thickness and contour
Panel 3 (middle-left): side profile only when source-backed; otherwise repeat a supported 45° view
Panel 4 (middle-right): top view, button layout + LED positions
Panel 5 (bottom-left): in-use close-up, correct hand grip
Panel 6 (bottom-right): beside {AA battery / credit card} for scale

Dimensions: {source-backed measurements, otherwise unknown}; match verified relative scale
Ports/buttons: {exact count and positions}
Style: clean product grid, white background, studio light, 6 equal panels,
20px white borders, no rendered header/footer/caption text; keep product name and dimensions in metadata
Negative: panel-to-panel distortion, different products across panels,
text inside panels, phantom ports/buttons
```

**Dual-consistency check:**
- [ ] Product identity matches 8维审图 (silhouette / size / material / function zones)
- [ ] Scale accurate (size vs hand / scale object correct)
- [ ] Port/button count + position correct
- [ ] Interaction type correct (touch not press, plug orientation correct)
- [ ] No phantom parts (cables/wires/buttons/text not in source)
