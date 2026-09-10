# v2 实现说明

v2 保留原视频模型和提交参数，在视频前增加单张宫格、来源明确的动作账本、类目质检和引用追踪。完整命令见 [README](README.md)。

## 单张多宫格契约

默认每个商品仅生成 identity_lock/reference_sheet.png 一张参考图，全部广告版本复用。usage_poses/manifest.json 引用同一张图，不生成分散的动作图片。它记录完整动作顺序；一张静态宫格不等于逐帧动作视频。

`generate_product_identity_lock.py` 复用 `generate_images.generate_image_file` 的 GPT-Image-2 `/images/edits` 路径。类目布局定义在 `scripts/v2_contract.py`，专项检查读取 `references/category-*.md`。优先使用产品简报选中的完整商品原图，拒绝缺少原图、认知失败和无依据的动作。

| 类目 | 布局（按行读） | 请求画布 |
|---|---|---|
| apparel | 2 行 × 2 列 | 1024×1024 |
| jewelry | 1 行 × 3 列 | 1536×1024 |
| electronics | 3 行 × 2 列 | 1024×1536 |
| home-tools / pet-tools | 上 3 下 2 | 1024×1024 |

同一次生成有助于集中表达参考，但不保证所有格一致。没有背面证据时复用有证据的角度，不能强行补出背面接口。具体布局和视觉一致性交给视觉 QC 检查；代码不宣称能像 CAD 一样锁死几何。

需要另一个操作图时显式执行：

```bash
python scripts/generate_usage_pose_sheet.py output --separate-sheet
python scripts/qc_dual_consistency.py output --stage usage
```

该选项再生成一张三格使用图；默认不启用。

## 来源、动作与比例

产品简报至少包含 confirmed_identity、confirmed_use_cases、step_by_step_usage、misuse_risks_to_avoid，视觉分析必须有成功的 images 记录。原始产品图应在 canonical_reference_images 中明确指定，或被分析为完整商品。

每个动作要带来源，示例仅表示字段结构：

```json
{
  "step_by_step_usage": [
    {"step": 1, "action": "将手机放入已证实的支撑位置", "evidence": "商品说明第2张图；需换成实际来源"}
  ]
}
```

字符串动作、缺失 evidence、标注 inference/推断的动作会报错。代码检查结构与明显的未知标记，不能自动验证某个来源描述是否真实；人工/视觉分析仍须核对原资料。尺寸、接口数量、功能状态未知时应明确未知，不能用类别常识补成确定规格。

“权威分离”可理解为选择规则，而非加权平均：

`外观 ← 真实商品图；功能/尺寸 ← 有依据的说明；人物/房间 ← 场景首帧；宫格 ← 次级指导`

原图和生成宫格冲突时以原图为准并修正宫格。`@ref{1.0}` 或 `scale authority 1.0` 不是本项目传给视频模型的参数。

已知实物长度和同平面标尺时，比例可辅助检查：`产品像素长度 / 标尺像素长度 ≈ 产品实际长度 / 标尺实际长度`。透视、角度和遮挡会影响比较；本项目没有自动标定或毫米级测量模块。默认 QC 评估可见相对比例，不声称精确测量。

## 接入现有流程

生成首帧时传入：真实主商品图 + 已质检宫格。生成尾帧时传入：场景首帧 + 真实主商品图 + 已质检宫格。若启用独立姿态宫格，再加入该图。v2 的必要引用不受旧 `--max-reference-images 1` 默认值裁掉。

每张场景图输出对应的 `.provenance.json`，保存实际参考文件摘要、完整提示词、图片模型和供应商。图片提示词明确只输出一张正常的竖版照片，不复制宫格布局。

VEO 继续接收场景首尾帧。Omni Flash 默认 10 秒，并提供两种显式模式：`first-last` 使用场景首尾帧；v2 的 `omni-reference` 固定使用两张全能参考图，顺序为“Image2 时序故事板 + 产品锁定宫格”。故事板必须有当前 provenance 并通过关键帧 QC，锁定宫格必须通过身份 QC。真实主商品图只负责生成和校验锁定宫格，不传给 Omni 作为第三张参考图。三个视频入口在 v2 中都先检查参考来源和相应 QC。`parallel_pipeline.py` 当前是已有关键帧的 VEO 批量提交器，不会自动生成宫格或首尾帧；Omni 请用 `generate_videos_lk888.py`。

使用 `omni-reference` 时，在单个变体的 `reference_images` 中指定 Image2 生成的时序故事板即可；适配器会自动把当前产品锁定宫格作为第二张参考，并忽略其他视频参考候选。故事板需保存 provenance 并通过 `qc_dual_consistency.py --stage keyframes --target <path>`；每格只能出现一台实体产品。真实主图仍是上游商品真值：如果故事板或锁定宫格与真实主图冲突，应先修正相关生成图再提交视频。

## 双重一致性质检

`qc_dual_consistency.py` 将真实原图与待检图发给可配置的视觉聊天模型，默认 gpt-5.2。六个必需检查字段为 identity、scale、placement、operation、continuity、category_specific，分别涵盖外观、比例、位置、操作、连续性和类目细节。

没有人为捏造的总分公式。判定规则：

- 任一检查 fail → fail。
- 任一检查 unknown，或产品身份没有明确通过 → needs_review。
- 所有必需检查通过，且不适用项给出理由 → pass。
- 模型调用失败或结构不合法 → error。

命令退出码 0 表示所选检查全部通过，2 表示出现不通过/待复核/API 错误；输入、依赖缺失也会非零退出。失败不自动触发付费重拍。报告包含具体观察依据和 corrections，修正后显式重生成、重检。

```bash
python scripts/qc_dual_consistency.py output --stage identity
python scripts/qc_dual_consistency.py output --stage keyframes --variants 1-3
python scripts/qc_dual_consistency.py output --stage videos --variants 1-3 --samples 8 --report qc_report.json
```

视频阶段使用 ffprobe 读取时长，ffmpeg 等距抽帧，并记录时间戳。它不是完整运动/音频审查；有需要可增加 --samples（2–32），仍需观看完整视频。报告按 stage 保存；检查某个新的变体集合会替换该 stage 的报告，提交时应包含要生成的全部变体。

## 文件结构

```text
01-product/
├── product_manifest.json
├── category.json
├── image_analysis.json
├── product_brief.json
├── images/
├── identity_lock/
│   ├── category_spec.json
│   ├── manifest.json
│   └── reference_sheet.png
├── usage_poses/
│   └── manifest.json
├── ugc_prompts.json
├── generated_images/
│   ├── variant-01-start.png
│   ├── variant-01-start.provenance.json
│   ├── variant-01-end.png
│   └── variant-01-end.provenance.json
├── qc/
│   ├── identity.json
│   ├── keyframes.json
│   └── videos.json
└── videos/
```

没有调用商业 API 的本地模拟测试仅验证代码契约与异常处理。五类实物的质量和成本尚未实测；旧文档“40%→10%”及每产品固定美元估算不再作为性能说明。
