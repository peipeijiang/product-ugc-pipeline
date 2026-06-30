# Product UGC Pipeline — PDCA 建模优化分析

> 套用 DAL 建模 PDCA 思路，分析该 Skill 在商品 UGC 视频生产中如何通过"认知建模 → 正负样本训练 → 效果监控 → 重点优化"实现持续改进。

## 一、Plan — 建模设计（利用认知 Agent 构建视频生产模型）

### 建模目标
将"商品 URL → 可投放带货视频"的全过程建模为一个可批量执行的认知-创意-生成流水线，替代传统多角色串行协作。

### 认知 Agent 建模架构（4 层 → 5 层）

| 版本 | 认知层数 | 核心模型 | 关键提交 |
|---|---|---|---|
| V1（5 月中旬） | 4 层 | 商品身份 / 商业承诺 / 商品功能 / 买家可见效果 | `1604542` 初始化 |
| V2（6 月中下旬） | 5 层 | 新增「场景想象」层，且新增 **核心卖点梯子** 字段 | `722d370`、`7a98b8d` |

**最终 5 层建模体系**：

```
Layer 1: Product Identity（商品身份）
  → 外观、材质、功能面、可见机构、SKU/配色，锁定不变形

Layer 2: Commercial Promise（商业承诺）
  → 商品标题、页面卖点、确认卖点 → "买家为什么买"

Layer 3: Product Function（商品功能）
  → 确认用法、分步操作、证明镜头、误用风险

Layer 4: Buyer-Visible Effect（买家可见效果）
  → 产品创造的结果：宠物更安心、厨房更高效、空间更整洁

Layer 5: Scene Imagination（场景想象）
  → 基于买家问题/功能/卖点推断的真实生活场景
```

### 建模 Agent 架构

```
商品URL → [抓取Agent] → 商品图+基础资料
         → [视觉分析Agent] → 每张图的外观/用法/风险
         → [商品认知Agent] → 产品身份确认+用法合成+卖点提炼+幻觉防御
         → [创意生成Agent] → 核心卖点梯子×N + 口播分镜 + 首尾帧prompt + VEO prompt
         → [图片Agent] → Image2 生成 start/end keyframes
         → [视频Agent] → LK888 VEO 3.1 生成 8s 带货视频
```

---

## 二、Do — 正负样本训练（利用正负样本组合提升生成质量）

### 正样本（引导模型产出高质量结果）

| 正样本类别 | 具体内容 | 在 Skill 中的体现 |
|---|---|---|
| **商品参考图** | 完整商品外观、正确 SKU、全比例、可见功能区 | `canonical_reference_images`、`selected_reference_images` |
| **确认卖点** | 商品页标题 + 描述 + 用户预期利益 | `confirmed_selling_points`、`benefit_ladder.core_selling_claim` |
| **正确用法** | 分步操作、功能场景、证明镜头 | `step_by_step_usage`、`confirmed_use_cases`、`proof_moments` |
| **买家结果** | 使用后的可见改善效果 | `buyer_effect`、`buyer_result` |
| **首尾帧对应** | start/end keyframes 对应同一故事弧首尾 beat | `storyboard` 驱动的 keyframe 生成 |
| **口播节奏** | 14-18 词 / 8 秒，问题 → 产品介入 → 结果 | `VOICEOVER_TARGET_WORDS`、`benefit_ladder` 顺序 |

### 负样本（防止模型产出不合格结果）

| 负样本类别 | 具体内容 | 在 Skill 中的体现 |
|---|---|---|
| **幻觉部件** | 凭空增加的线缆、按钮、盖子、容器、马达 | `phantom_parts` 防御 |
| **形状漂移** | 产品外观变形、比例失调、颜色变化 | `shape_preservation` 防御 |
| **材质改变** | 塑料变金属、织物变皮革等 | `material_texture_lock` 防御 |
| **动作越界** | 展示不存在的功能/效果 | `action_bounds` 防御 |
| **场景污染** | 错误配件、错误用法、错误场景 | `context_contamination` 防御 |
| **比例错乱** | 产品放大/缩小到不合理尺寸 | `scale_anchor` 防御 |
| **平台图标** | Ins/TikTok 图标、字幕、水印 | `platform_icon_hard_ban` 规则 |
| **口播未说完** | 台词过长被 VEO 截断 | `VOICEOVER_HARD_MAX_WORDS=20`、`voiceover_script_8s` |
| **首尾帧雷同** | 首尾帧几乎一样，8 秒无情节 | `start/end keyframe continuity` 差异检查 |
| **卖点缺失** | Prompt 只讲部件不讲买点 | `benefit_ladder` 强约束 |
| **模型静默切换** | VEO 失败自动切到 Seedance/Kling/Omni | `VEO-first` 禁止静默切换 |

### 正负样本组合策略

```
VEO Prompt 构建逻辑：

1. 正样本注入（告诉模型做什么）:
   "Core buyer reason to buy: {core_selling_claim}"
   "Benefit ladder: problem={buyer_problem} → action={product_intervention} → result={buyer_result}"
   "Use provided product reference as canonical source"

2. 负样本排除（告诉模型不做什么）:
   "Do not redesign, recolor, simplify, distort the product"
   "No cables, wires, hoses, motors, buttons, lids"
   "No social media icons, platform logos, subtitles, captions"
   "No unsupported claims, no magic effects"
```

---

## 三、Check — 效果监控与波动分析

### 全周期产出总览（截至 2026-06-29）

| 指标 | 数值 |
|---|---|
| Canonical 视频总产出 | 230 个 |
| Prompt 变体数量 | 227 条 |
| 已建档商品数 | 37 个 |
| 生成图片素材 | 496 张 |
| 视频任务成功率 | 97.21%（244/251） |
| 平均成功任务成本 | ≈ 0.91 / 条 |
| Skill 迭代提交 | 42 次 |

### 分阶段建模效果分析

#### ✅ 5 月：基础建模期（效果良好）

| 阶段 | 关键事件 | 效果评估 | 对应提交 |
|---|---|---|---|
| 5-12 ~ 5-16 | Skill 初始化 + LK888 VEO 接入 + 商品锁定与场景分离 | 流程跑通，视频可产出 | `1604542` → `de13e2a` → `7a98b8d` |
| 5-19 ~ 5-20 | 8s 口播标准化 + 首尾帧链接 + 增量文件管理 + 功能多样性 | 视频节奏和文件管理显著改善 | `0fadd46` → `3096739` → `892855f` |
| 5-21 | 平台图标硬禁令 | 杜绝了 Ins/TikTok 图标混入 | `f7bd916` |

**5 月总结**：建模基础扎实，核心规则快速迭代，产出稳定。

#### ⚠️ 6 月中旬：模型通道波动期（效果下滑）

| 问题 | 现象 | 根因 | 影响范围 |
|---|---|---|---|
| Omni-flash 试验 | 默认 prompt 切换到 omni-flash，VEO 通道不稳定 | 新模型接入时未坚持 VEO-first | `b21cba0` ~ `1d5b660` |
| 即梦/Seedance 静默切换 | 当 VEO 失败时脚本自动切到 Seedance 等非 VEO 模型 | 缺少 fail-fast 和模型通道治理 | 部分 wibly 商品视频 |
| Prompt 卖点弱化 | 部分 prompt 只描述"怎么用"（snap buckle、place on table）而没讲"为什么买" | 缺少商业卖点梯子约束 | 宠物项圈等商品早期变体 |

**6 月总结**：相当于 DAL 建模中"3 月份建模效果下滑"——模型通道不稳定 + 正负样本配置不完善导致产出质量波动。

#### 🔧 6 月下旬：质量回归期（重点优化恢复）

| 优化 | 内容 | 效果 | 对应提交 |
|---|---|---|---|
| VEO-first 强制执行 | 生产默认 LK888 `veo3.1`，禁止静默切换 | 模型通道口径统一 | `f76d7c8` |
| 核心卖点梯子 | 强制在 prompt 前构建 benefit_ladder | 口播从"部件说明"变"卖点转化" | `722d370` |
| 幻觉防御通用化 | 6 类幻觉自动注入所有 prompt | 产品形变和凭空部件显著减少 | `4ecbdaa` |
| Fail-Fast 生产契约 | 视觉分析/认知/prompt/首尾帧任意环节失败，立即停止 | 不浪费视频 API 费用 | `9bc0f8d` |

---

## 四、Act — 重点产品线下建模优化输出

### 已固化到 Skill 的重点优化（可复用、可版本追溯）

#### 1. 通用幻觉防御框架（`4ecbdaa`）

```
6 类防御自动注入所有产品 Prompt：

phantom_parts → 防凭空线缆/按钮/盖子/容器
shape_preservation → 防产品外形漂移
material_texture_lock → 防材质/颜色变化
action_bounds → 防展示不存在功能
context_contamination → 防错误配件/场景
scale_anchor → 防产品尺寸错乱
```

#### 2. 核心卖点梯子（`722d370`）

```
每个 variant 强制写入 5 个字段，否则不生成 Video Prompt：

core_selling_claim → "买家为什么买"
buyer_problem → "买家的痛点/欲望"
product_intervention → "产品如何解决"
buyer_result → "使用后的可见改善"
proof_moment → "证明镜头"
```

#### 3. VEO 通道治理（`f76d7c8` + `447865d`）

```
- 生产默认模型 : LK888 veo3.1
- 静默切换规则 : 禁止
- 失败处理 : 报告具体状态/成本/错误，人工决策
- 非 VEO 模型 : 仅用户明确批准时使用
```

#### 4. Fail-Fast 生产契约（`9bc0f8d`）

```
在调用付费视频 API 前必须满足：

✓ image_analysis.json 无 error 字段
✓ product_brief.json 包含完整身份/用法/风险
✓ ugc_prompts.json 基于有效商品认知生成
✓ start/end keyframes 由 Image2 从 canonical reference 生成

任一不满足 → 停止，报告失败步骤/模型/供应商
```

#### 5. 8 秒口播完整度规范

```
- 目标词数 : 14-18 个英文单词
- 硬上限 : 20 词
- 最多 3 条 spoken line
- 每条只分配给一个 storyboard beat
- 顺序 : buyer problem → product intervention → buyer result
- 禁止 : "here is how it works"、"easy setup"、"soft material" 等无卖点台词
```

### 优化效果量化

| 维度 | 优化前 | 优化后 | 提升 |
|---|---|---|---|
| 视频任务成功率 | 通道不稳定期间曾有较多失败 | 97.2% 明确终态成功率 | 可记录可重试 |
| Prompt 口播质量 | 部分仅描述产品部件/材质 | 每个 variant 强制写卖点梯子 | 从"部件说明"升级为"卖点转化" |
| 产品一致性 | 偶有形状漂移/凭空部件 | 6 类幻觉防御自动注入 | 人工质检经验前置到流程 |
| 首尾帧连贯性 | 首尾帧有时场景/人物变化过大 | 尾帧基于首帧生成，同场景同人物 | 视频中途突变风险降低 |
| 模型通道稳定性 | 曾静默切到即梦/Seedance | VEO-first 强制执行 | 视频质量口径统一 |
| 文件管理 | 追加视频时目录混乱 | canonical 递增编号 + 统一 prompt 文件 | 查找和交付效率显著提升 |

---

## 五、PDCA 循环总结

```
Plan → 设计 5 层认知建模 + 多 Agent 流水线架构
  ↓
Do  → 正样本（商品参考 + 卖点 + 用法 + 证明镜头）
       + 负样本（6 类幻觉防御 + 平台 icon 禁令 + 口播约束）
  ↓
Check→ 5 月效果良好 → 6 月中旬通道波动（omni-flash/即梦静默切换）
       → 6 月下旬质量回归（VEO-first + 卖点梯子 + 幻觉防御）
  ↓
Act  → 固化 5 项重点优化到 SKILL.md + 脚本
       效果：成功率 97.2%，230 条 canonical 视频，42 次迭代提交
```

**下一步**：在新商品上跑完整 PDCA 循环，用统计 JSON 监控成功率、成本、模型分布，持续发现和修复新的"效果下滑"信号。
