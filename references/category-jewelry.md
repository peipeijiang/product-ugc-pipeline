# Category: Jewelry (首饰专用)

## 首饰6维审图（替代服装7要素）

| Field | Check for jewelry |
|---|---|
| **材质+色调** | Metal type (gold / silver / rose gold / platinum) + finish (polished / brushed / oxidized) + stones (diamond / pearl / jade / none) |
| **款式结构** | Design type (solitaire / cluster / halo / pendant / hoop / stud / chain / bangle) |
| **尺寸规格** | Physical dimensions + size reference (ring: inner diameter mm / necklace: chain length cm / earring: drop length mm) |
| **佩戴位置精度** | Exact placement (ring: which finger + above/below knuckle / necklace: collarbone/mid-chest / earring: lobe/cartilage) |
| **扣合机制** | Closure type (lobster clasp / spring ring / push-back / screw-back / magnetic / hook) |
| **功能细节** | Adjustable chain / removable charm / stackable / reversible / hidden compartment |

**Special check:** 
- Scale accuracy: ring must fit finger realistically, necklace length matches body proportion
- Metal sheen: reflections must follow light source, no plastic-looking metal
- Stone setting: prongs/bezels visible, stones not floating
- Weight distribution: earrings hang naturally, necklace drapes correctly
- Skin interaction: no floating between jewelry and skin, pressure points visible

## 场景预设

- **E-commerce studio:** jewelry on model, white/gray background, key:fill 1.5:1, 5600K, 100mm macro f/5.6
- **Lifestyle close-up:** jewelry in daily context (hand holding coffee / typing / gesture), natural light, 85mm f/2.8
- **Detail macro:** extreme close-up of setting/clasp/engraving, ring light, 150mm macro f/8

## 负向增量

```
floating jewelry, skin clipping through metal, warped prongs,
plastic-looking metal, invented brand marks, distorted stones,
wrong finger size (ring too loose/tight), necklace length mismatch,
earring penetrating earlobe instead of hanging from it,
impossible clasp position (back of neck visible from front angle)
```

## Detail actions (product-centric, 货不对板 verified)

| # | Action | Verifiability | Shot |
|---|---|---|---|
| 1 | **Ring: slide onto finger slowly, stop at correct position (above/below knuckle per design)** — shows inner diameter fit and metal finish during motion | ✅ Verifiable: ring size visible in flat-lay (inner diameter measurable). Metal finish visible. Use "slow controlled" qualifier. | Macro close-up, hand + ring, 3s |
| 2 | **Necklace: clasp at back of neck, then rotate camera 180° to front** — shows chain length settling at correct chest position (collarbone/mid-chest/below-bust per spec) | ✅ Verifiable: chain length measurable in flat-lay. Clasp type visible. Camera must show clasp fastening, then cut/rotate to front view. | Mid-shot back → cut → mid-shot front, 4s total |
| 3 | **Earring: close-up of fastening mechanism (push-back click / screw-back turn / hook insert)** — shows closure security and metal detail | ✅ Verifiable: closure type visible in flat-lay. Macro must show actual fastening motion, not floating earring. | Extreme close-up, ear + hand, 2s |
| 4 | **Material showcase: rotate jewelry slowly under light** — metal sheen, stone facets catching light, no plastic appearance | ✅ Verifiable: material finish visible in flat-lay. Rotation speed: 1 full turn in 3–4s. | Close-up, rotating, 4s |

**佩戴位置锁定表 (Placement Lock Table):**

| Jewelry Type | Placement Lock | Scale Anchor |
|---|---|---|
| **Ring** | Finger identity (index/middle/ring/pinky) + position (above/below knuckle) | Inner diameter vs finger width |
| **Necklace** | Chain length → chest position (collarbone=40cm / mid-chest=45cm / below-bust=50cm+) | Chain length vs neck-to-chest distance |
| **Earring** | Ear position (lobe center / upper lobe / cartilage) + drop length | Drop length vs earlobe height |
| **Bracelet** | Wrist position (loose slide / snug fit / above wrist bone) | Inner circumference vs wrist diameter |
| **Brooch** | Garment placement (lapel / collar / chest pocket) | Brooch size vs garment scale |

## Character Sheet 适配（4视图 → 3视图 + 1特写）

Jewelry 不需要 90° 侧面全身图，改为：

| View | Pose | Purpose |
|---|---|---|
| **Front close-up** | Jewelry on body, face visible for scale | Overall placement + scale verification |
| **45° detail** | Three-quarter angle, jewelry + skin interaction | Depth, drape (necklace), weight distribution |
| **Extreme macro** | Jewelry only, no body | Material finish, stone setting, clasp detail, hallmark |

**Dual-consistency check:**
- [ ] Jewelry matches 6维审图 (material / structure / size / placement / closure / function)
- [ ] Scale accurate (ring fits finger / necklace length correct / earring proportional)
- [ ] Metal sheen realistic (follows light source, not plastic-looking)
- [ ] No floating (jewelry touches skin at all contact points)

