# 3.1 量化结果案例：Product UGC Pipeline Skill — 批量解决电商商品 UGC 视频生产效率与一致性问题

## 案例：AI 商品 UGC 视频生产 Skill 接入选品/素材/视频生成流程

### 背景

跨境电商商品短视频生产中，一个商品从链接到可投放素材通常需要经历：商品页素材抓取、商品图筛选、产品功能理解、卖点提炼、UGC 分镜脚本、首尾帧生成、视频模型调用、失败重试、文件整理等多个环节。  

在实际执行中，常见问题包括：

- 商品图很多但有效参考图少，容易引用错误 SKU、配件图或非产品图。
- 视频模型容易“改造产品外观”，例如产品形状漂移、凭空增加线缆/按钮/配件。
- Prompt 容易只描述“怎么用”，没有抓住“用户为什么买”的核心卖点。
- 追加生成视频时，文件夹、提示词、首尾帧、视频结果容易散落，难以追溯。
- VEO / Image2 / 备用视觉模型等多 API 通道状态不稳定，需要人工反复排查、重试和记录。

这些问题会直接拉长素材生产周期，也会影响商品视频的一致性、可复用性和投放前质检效率。

### 解决方案

基于本地 Codex Skill 机制，开发 `product-ugc-pipeline`，将“商品 URL → 商品认知 → Prompt → 首尾帧 → VEO 视频 → 文件归档”的流程固化为可复用生产流水线，实现：

1. **商品资料自动沉淀**  
   输入商品 URL 后，自动创建编号商品文件夹，抓取商品页信息和商品图，生成 `product_manifest.json`、`materials.md`、`images/` 等素材资产。

2. **视觉理解 + 产品认知文档化**  
   使用视觉模型分析商品图，输出 `image_analysis.json`；再综合商品页、视觉分析和用法信息生成 `product_brief.json`，记录产品身份、使用步骤、卖点、误用风险、参考图策略。

3. **核心卖点驱动 Prompt**  
   Prompt 生成阶段先构建 `benefit_ladder`：`core_selling_claim → buyer_problem → product_intervention → buyer_result → proof_moment`，确保每条视频围绕“买家为什么会买”展开，而不是只讲材质、按钮、扣子、摆放等细节。

4. **产品一致性防幻觉机制**  
   在图片和视频 Prompt 中自动注入产品保真约束、参考图锁定规则、禁止凭空增加部件规则、手机方向规则、首尾帧连续性规则、平台图标/字幕禁用规则。

5. **首尾帧 + VEO 视频生产**  
   使用 Image2 生成与分镜首尾一致的 start/end keyframes，再通过 LK888/updrama VEO 3.1 生成 8 秒竖屏 UGC 视频；生产默认坚持 VEO 通道，不静默切换到 Seedance/Kling/Omni。

6. **增量追加与版本追溯**  
   新增视频默认在原商品文件夹中按 `variant-XX` 递增，提示词统一追加到 canonical `ugc_prompts.json`，同时保留 `runs/` 历史批次，降低多轮追加生产时的管理混乱。

## 量化结果

统计时间：2026-06-29  
统计范围：`/Users/shane/Documents/Codex/2026-04-27/https-depthstores-com-products-flower-shaped` 本地 UGC 工作区，另统计 `/Users/shane/Downloads` 中相关导出副本。
线上案例文档：`https://github.com/peipeijiang/product-ugc-pipeline/blob/main/docs/evidence/product_ugc_skill_case_20260629.md`

| 指标 | 改进前（基线） | 改进后（实测） | 提升幅度 | 核查方式 |
|---|---|---|---|---|
| 商品 UGC 视频生产规模 | 单商品/单批次主要靠人工逐步处理：商品图筛选、卖点理解、prompt、首尾帧、视频调用、文件归档分散完成，难以稳定批量追加 | 已建档 37 个商品目录；生成 38 个 `ugc_prompts.json`；累计 227 条 prompt 变体；canonical 视频产出 230 个 MP4 | 从单点试验升级为多商品、多批次、可追加的批量生产流水线 | 见佐证②；统计文件 `product_ugc_skill_stats_20260629.json`；命令 `find . -path "*/videos/variant-*.mp4" | grep -v "/runs/" | grep -vi "backup" | wc -l` |
| 视频素材资产沉淀 | 传统方式通常只保留最终视频，商品认知、首尾帧、参考图选择和 prompt 中间过程容易散落，后续复盘困难 | 已生成首帧 237 张、尾帧 237 张、单图素材 22 张，图片素材总计 496 张；每条 canonical 视频平均约 2.16 张前置图片资产 | 每条视频都沉淀可复用视觉锚点，支持复跑、质检和二次创作 | 见佐证④；命令 `find . -path "*/generated_images/variant-*-start.png" | wc -l`、`find . -path "*/generated_images/variant-*-end.png" | wc -l` |
| 视频生成成功率与异常可追踪性 | 手动调用视频模型时，失败原因、任务状态、成本和输出路径容易靠聊天记录/人工记忆维护，失败后难以复盘 | `video_generation_results.json` 中记录 244 条成功、7 条失败；明确终态成功率约 97.2%；失败原因包含渠道不可用、超时、断管等 | 失败从“不可解释”变成“可记录、可重试、可复盘”；明确终态成功率约 97.2% | 见佐证②；统计文件 `product_ugc_skill_stats_20260629.json` 中 `video_result_success`、`video_result_failed`、`derived_metrics.explicit_terminal_success_rate` |
| 单条视频成本可估算性 | 未结构化记录 API 成本时，只能事后查平台账单，难以按商品/批次估算投产成本 | 已记录视频 API 成本合计 222.728；平均成功任务记录成本约 0.913/条，平均 canonical 视频记录成本约 0.968/条 | 从不可估算变成可按任务/批次预估成本，为批量生产预算提供依据 | 见统计文件 `product_ugc_skill_stats_20260629.json` 中 `video_result_cost_sum_recorded`、`derived_metrics.recorded_cost_per_successful_video_task` |
| Prompt 质量与核心卖点表达 | 早期 prompt 容易只讲“怎么用”或产品部件，如 buckle、材质、按钮、摆放，视频核心卖点不突出 | Skill 已固化 `benefit_ladder`：`core_selling_claim / buyer_problem / product_intervention / buyer_result / proof_moment`；每条视频先确定买家为什么买，再写口播、分镜和 VEO prompt | 从功能说明型 prompt 升级为卖点转化型 prompt，降低“视频好看但没抓住卖点”的返工 | 见佐证⑥；`SKILL.md` 中 `Core Selling-Point Flow`；`generate_ugc_prompts.py` 中 `def build_benefit_ladder`；最新提交 `722d370` |
| 8 秒口播完整度 | 未限制口播长度时，VEO 8 秒视频容易出现结尾台词没说完、重复口播、节奏拖沓 | 固化 8 秒口播规则：14–18 英文词，硬上限 20 词，不重复 spoken line，不额外加 filler/CTA | 显著降低“台词没讲完”的视频返工风险 | 见佐证⑥；`SKILL.md` 中 8-second voiceover 规则；`generate_ugc_prompts.py` 中 `VOICEOVER_TARGET_WORDS`、`VOICEOVER_HARD_MAX_WORDS` |
| 产品一致性与防幻觉 | 视频模型易凭空增加线缆、按钮、盖子、容器、错误配件，或改变产品形状/材质/比例 | Skill 固化 6 类幻觉防御：phantom parts、shape preservation、material lock、action bounds、context contamination、scale anchor；所有 image/video prompt 自动注入产品保真约束 | 将人工质检经验前置到 prompt 和流程中，降低产品形变、凭空部件、错误用法风险 | 见佐证⑥；`SKILL.md` 中 `Universal Hallucination Defense`；提交 `4ecbdaa` |
| 首尾帧连续性 | 首尾帧分别生成时，容易出现人物、场景、道具、产品状态变化过大，导致 VEO 中途漂移 | Skill 要求 start/end keyframes 对应同一 storyboard 的首尾 beat；尾帧优先基于首帧 + 商品参考图生成，保持同一房间、人物、光线、机位，只改变动作结果 | 从“随机前后图”升级为“同一故事弧首尾帧”，提升视频连贯性和产品稳定性 | 见佐证⑥；`SKILL.md` 中 start/end keyframe continuity 规则；提交 `0dfd063`、`8261197` |
| 文件管理与追加生产效率 | 每次追加视频容易新建目录、prompt 分散、结果文件混乱，后续很难知道哪个 prompt 对应哪个视频 | canonical 视频统一为 `videos/variant-XX.mp4`；prompt 统一追加到 `ugc_prompts.json`；`runs/` 保存批次历史；Downloads 相关导出副本 781 个 | 支持“先产几条、后续继续追加”，文件查找和交付整理效率显著提升 | 见佐证②/⑦；`SKILL.md` Product Folder Requirements；提交 `ef93d68`、`522189a` |
| 模型通道治理 | 早期多模型尝试时，可能因通道失败而静默切到 Seedance/Kling/Omni，导致质量和能力不一致 | 生产默认 LK888 `veo3.1`，Skill 明确禁止静默切换非 VEO 模型；失败时报告具体状态、成本、错误 | 视频生产模型口径稳定，便于质量对比和成本核算 | 见佐证⑥；`SKILL.md` 中 `Video generation is VEO-first`；提交 `f76d7c8`、`447865d` |
| Skill 资产化与可复用性 | 经验分散在单次对话和人工判断里，难以复用到下一批商品 | Skill 仓库已有 41 次提交；Prompt/口播/分镜相关 18 次，质量门禁/幻觉防御相关 11 次，VEO/LK888 相关 4 次，输出管理相关 3 次；核心脚本 8 个 | 从一次性人工经验沉淀为可版本管理、可迁移、可复用的生产工具 | 见佐证①/⑤；命令 `git log --format="%ai %h %s"`；Skill 仓库 `/Users/shane/.codex/skills/product-ugc-pipeline` |
| 人力协作成本 | 传统链路通常需要选品/运营整理素材、编导写脚本、设计/视频人员做首尾帧、技术人员调用模型和整理结果，多角色串行协作 | 1 人借助 Codex + Skill 完成商品抓取、视觉分析、brief、prompt、首尾帧、VEO 调用、失败重试、统计与案例文档输出 | 多角色串行流程收敛为单人可执行流水线，人力协调成本显著下降 | 见佐证⑤；Skill 脚本入口和 git commit 时间线；本文件统计结果 |

## 佐证（评审专家可按路径/命令核查）

### ① Skill Git commit 时间线 — 核查“能力持续迭代与版本管理”

- GitHub 仓库：`https://github.com/peipeijiang/product-ugc-pipeline`
- GitHub commits：`https://github.com/peipeijiang/product-ugc-pipeline/commits/main/`
- 首次版本化提交：`2026-05-12 15:10:32 +0800 1604542 chore: initialize product ugc pipeline skill versioning`
- 核心卖点提交：`https://github.com/peipeijiang/product-ugc-pipeline/commit/722d370`
- 最新推送提交：`https://github.com/peipeijiang/product-ugc-pipeline/commit/dcdb600`
- 当前共 41 次 skill 提交：
  - Prompt / voiceover / storyboard / selling / benefit 相关：18 次
  - 质量门禁 / 幻觉防御 / 几何约束 / 连续性相关：11 次
  - VEO / LK888 接入相关：4 次
  - 输出目录 / 增量管理相关：3 次

核查方法：

```bash
cd /Users/shane/.codex/skills/product-ugc-pipeline
git log --format="%ai %h %s"
git log --grep="prompt\\|voiceover\\|storyboard\\|selling\\|benefit" --oneline
git log --grep="hallucination\\|geometry\\|continuity\\|fail fast" --oneline
```

### ② 产出视频统计 — 核查“历史产出规模”

- 线上统计文件：`https://github.com/peipeijiang/product-ugc-pipeline/blob/main/docs/evidence/product_ugc_skill_stats_20260629.json`
- Canonical 视频目录规则：`*/videos/variant-*.mp4`
- 当前 canonical 视频：230 个
- 当前 Downloads 相关导出副本：781 个

核查方法：

```bash
cd /Users/shane/Documents/Codex/2026-04-27/https-depthstores-com-products-flower-shaped
find . -path "*/videos/variant-*.mp4" | grep -v "/runs/" | grep -vi "backup" | wc -l
cat product_ugc_skill_stats_20260629.json
```

### ③ Prompt 与商品认知文件 — 核查“从商品理解到视频脚本的链路”

每个商品目录通常包含：

- `product_manifest.json`：商品页标题、链接、卖点、图片来源。
- `materials.md`：素材记录和人工可读说明。
- `image_analysis.json`：视觉模型对商品图的分析。
- `product_brief.json`：产品身份、用法、卖点、误用风险、证明镜头。
- `ugc_prompts.json`：每个视频变体的口播、分镜、首尾帧 Prompt、VEO Prompt。

示例目录：

```text
/Users/shane/Documents/Codex/2026-04-27/https-depthstores-com-products-flower-shaped/wibly-ugc-output/11-dog-deworming-collar-cat-mosquito-repellent-collar-flea-removal-and-louse-preven
```

核查方法：

```bash
find /Users/shane/Documents/Codex/2026-04-27/https-depthstores-com-products-flower-shaped -name "ugc_prompts.json" | wc -l
find /Users/shane/Documents/Codex/2026-04-27/https-depthstores-com-products-flower-shaped -name "product_brief.json" | wc -l
```

### ④ 首尾帧与视频一致性资产 — 核查“产品保真与视频可控性”

- 首帧：237 张
- 尾帧：237 张
- 单图素材：22 张
- 图片总数：496 张

核查方法：

```bash
cd /Users/shane/Documents/Codex/2026-04-27/https-depthstores-com-products-flower-shaped
find . -path "*/generated_images/variant-*-start.png" | wc -l
find . -path "*/generated_images/variant-*-end.png" | wc -l
find . -path "*/generated_images/variant-*.png" | wc -l
```

### ⑤ AI 驱动开发证据 — 核查“研发流程被 Skill 化沉淀”

Skill 源码入口：

- `https://github.com/peipeijiang/product-ugc-pipeline/blob/main/SKILL.md`
- `https://github.com/peipeijiang/product-ugc-pipeline/blob/main/scripts/scrape_products.py`
- `https://github.com/peipeijiang/product-ugc-pipeline/blob/main/scripts/analyze_materials.py`
- `https://github.com/peipeijiang/product-ugc-pipeline/blob/main/scripts/build_product_brief.py`
- `https://github.com/peipeijiang/product-ugc-pipeline/blob/main/scripts/generate_ugc_prompts.py`
- `https://github.com/peipeijiang/product-ugc-pipeline/blob/main/scripts/generate_images.py`
- `https://github.com/peipeijiang/product-ugc-pipeline/blob/main/scripts/generate_videos_lk888.py`
- `https://github.com/peipeijiang/product-ugc-pipeline/blob/main/scripts/run_fresh_batch.py`

关键能力提交示例：

- `de13e2a skill: add lk888 veo video adapter`
- `0fadd46 skill: tighten 8s voiceover and chain keyframes`
- `ef93d68 skill: append videos in existing folders`
- `892855f skill: enforce function diversity and phone geometry`
- `4ecbdaa skill: add universal hallucination defense framework`
- `f76d7c8 skill: enforce LK888 VEO default and no silent fallback`
- `722d370 skill: anchor UGC prompts to core selling ladder`

### ⑥ 质量门禁与防幻觉机制 — 核查“质量保障由流程承担”

核心规则已沉淀在 `SKILL.md` 和生成脚本中：

- 失败快停：视觉分析、产品认知、Prompt、首尾帧任何关键步骤失败，不继续付费跑视频。
- 产品保真：产品形状、材质、颜色、部件、比例、SKU 必须由参考图锁定。
- 幻觉防御：禁止凭空出现线缆、按钮、盖子、容器、错误手机方向、错误佩戴方式等。
- 卖点梯子：先抓核心购买理由，再写口播和分镜，避免只生成“how it works”式弱视频。
- VEO 默认：生产默认 LK888 `veo3.1`，不可静默切到其他模型。
- 文件规范：新增视频在原产品目录递增编号，提示词统一追加到 canonical 文件。

核查方法：

```bash
# 在线打开：
# https://github.com/peipeijiang/product-ugc-pipeline/blob/main/SKILL.md
# https://github.com/peipeijiang/product-ugc-pipeline/blob/main/scripts/generate_ugc_prompts.py
# 或本地 clone 后执行：
grep -n "Core Selling-Point Flow" SKILL.md
grep -n "Universal Hallucination Defense" SKILL.md
grep -n "def build_benefit_ladder" scripts/generate_ugc_prompts.py
grep -n "Video generation is VEO-first" SKILL.md
```

### ⑦ 当前代码与统计总入口

- GitHub Skill 仓库：`https://github.com/peipeijiang/product-ugc-pipeline`
- UGC 工作区：`/Users/shane/Documents/Codex/2026-04-27/https-depthstores-com-products-flower-shaped`
- 线上统计文件：`https://github.com/peipeijiang/product-ugc-pipeline/blob/main/docs/evidence/product_ugc_skill_stats_20260629.json`
- 推荐核查对象：
  - `wibly-ugc-output/`
  - `product-ugc-output/`
  - `offer831629666450-ugc-output/`
  - `offer802023822536-ugc-output/`
  - `shopify-glasses-ugc-output/`

## 结论

`product-ugc-pipeline` 已经从单次视频生成脚本，迭代为一套可复用的商品 UGC 生产 Skill。它把商品理解、卖点提炼、Prompt 生成、首尾帧控制、VEO 调用、失败重试、质量门禁和文件归档串成闭环。  

截至 2026-06-29，本地可核查的 canonical 视频产出为 **230 个 MP4**，累计 prompt 变体 **227 条**，生成图片素材 **496 张**，并通过 **41 次 Git 提交**沉淀了 VEO 接入、核心卖点、首尾帧连续性、幻觉防御、增量输出管理等关键能力。
