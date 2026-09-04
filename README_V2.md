# Product UGC Pipeline v2

基于 Higgsfield、蓝书 Lanshu、Virtual Try-On Video 三个开源 skill 构建的**五类产品 UGC 视频生成流程**。

## 🎯 覆盖产品类型

| 类目 | 子类示例 | 审图维度 | 身份锁定视图 | 核心检查项 |
|------|---------|---------|-------------|-----------|
| **Apparel** (服装) | T恤、连衣裙、牛仔裤、外套 | 7要素 | 4视图 Character Sheet | 布料动态、版型、人脸8维 |
| **Jewelry** (首饰) | 戒指、项链、耳环、手链 | 6维 | 3视图 + 特写 | 金属反光、佩戴位置精度 |
| **Electronics** (电子产品) | 耳机、音箱、键盘、积木 | 8维 | 6视图 | 功能状态、交互类型、无幻觉零件 |
| **Home Tools** (厨房工具) 🆕 | 菜刀、削皮刀、锅铲、滤网 | 7维 Tools | 5视图 | 食材交互物理、安全握持 |
| **Pet Tools** (宠物工具) 🆕 | 宠物梳、牵引绳、宠物碗 | 7维 Tools | 5视图 + 宠物参考 | 宠物舒适度、物种匹配 |

## 🚀 快速开始

### 前置依赖

```bash
# 1. 安装三个核心 skill（如果尚未安装）
cd ~/.agents/skills

# Higgsfield (MIT)
git clone https://github.com/OSideMedia/higgsfield-ai-prompt-skill.git

# 蓝书 Lanshu (MIT)
git clone https://github.com/cclank/lanshu-awesome-ai-video-kit.git

# Virtual Try-On Video (source-available, 个人非商业可用)
git clone https://github.com/fsn021920-prog/virtual-try-on-video.git

# 2. 确认当前 pipeline 已包含 v2 类目文件
ls ~/.agents/skills/product-ugc-pipeline/references/category-*.md
# 应看到: category-home-tools.md, category-pet-tools.md, category-jewelry.md, category-electronics.md
```

### 基础流程

```bash
# 1. 爬取产品（支持淘宝/京东/1688）
python scripts/scrape_products.py urls.txt --out product-ugc-output

# 2. 🆕 自动分类（识别五大类目）
python scripts/classify_product_category.py product-ugc-output

# 3. 视觉分析（根据类目加载对应审图维度）
LAOZHANG_API_KEY=sk-xxx python scripts/analyze_materials.py product-ugc-output

# 4. 构建产品简报
LAOZHANG_API_KEY=sk-xxx python scripts/build_product_brief.py product-ugc-output

# 5. 🆕 生成产品身份锁定（根据类目生成 4/3/6/5 视图）
LAOZHANG_API_KEY=sk-xxx python scripts/generate_product_identity_lock.py product-ugc-output

# 6. 🆕 生成使用姿态库（从类目 Detail Actions 生成）
LAOZHANG_API_KEY=sk-xxx python scripts/generate_usage_pose_sheet.py product-ugc-output

# 7. 生成 UGC 提示词（使用类目对应模板）
LAOZHANG_API_KEY=sk-xxx python scripts/generate_ugc_prompts.py product-ugc-output --count 10

# 8. 生成关键帧
LAOZHANG_API_KEY=sk-xxx python scripts/generate_images.py product-ugc-output

# 9. 生成视频（VEO 3.1 / Omni Flash）
LK888_API_KEY=sk-xxx python scripts/generate_videos_lk888.py product-ugc-output --model veo3.1

# 10. 🆕 双重一致性 QC（根据类目加载专项检查）
python scripts/qc_dual_consistency.py product-ugc-output --auto-retry-failed
```

## 📂 目录结构（v2）

```
product-ugc-output/
├── 01-product-name/
│   ├── product_manifest.json
│   ├── category.json                    # 🆕 类目标识 (apparel/jewelry/electronics/home-tools/pet-tools)
│   ├── materials.md
│   ├── images/
│   ├── image_analysis.json
│   ├── product_brief.json
│   │
│   ├── identity_lock/                   # 🆕 产品身份锁定（类目特定视图数）
│   │   ├── manifest.json
│   │   ├── category_spec.json           # 类目专属规格
│   │   ├── view_0_front.png
│   │   ├── view_1_45deg.png
│   │   ├── view_2_side.png
│   │   ├── view_3_top.png              # Electronics 专用
│   │   ├── view_4_inuse.png
│   │   └── view_5_scale.png             # Electronics 专用
│   │
│   ├── usage_poses/                     # 🆕 使用姿态库（从 Detail Actions 生成）
│   │   ├── manifest.json
│   │   ├── panel_0_grip.png
│   │   ├── panel_1_interaction.png
│   │   ├── panel_2_function_active.png
│   │   └── panel_3_context.png
│   │
│   ├── ugc_prompts.json
│   ├── runs/
│   ├── generated_images/
│   └── videos/
```

## 🆕 v2 新增功能

### 1. 自动类目识别

```bash
python scripts/classify_product_category.py product-ugc-output

# 输出示例:
# 处理: 01-black-tshirt
#   分类为: apparel (confidence: 0.95, from: title_keywords)
# 处理: 02-silver-ring
#   分类为: jewelry (confidence: 0.95, from: title_keywords)
# ...
```

### 2. 类目特定的身份锁定

不同类目生成不同数量的视图：

- **Apparel**: 4视图 Character Sheet（Virtual Try-On 标准）
- **Jewelry**: 3视图 + 1特写（改造 Accessories）
- **Electronics**: 6视图（Higgsfield 风格，覆盖所有接口）
- **Home Tools**: 5视图（平铺/侧面/45度/握持/尺寸参考）
- **Pet Tools**: 5视图 + 宠物舒适度参考

### 3. 类目特定的 QC 检查

每个类目有专属的检查项：

**Apparel (服装):**
- 7要素审图（主色/领口/肩线/袖型/腰线/衣长/面料）
- 布料动态行为
- 人脸8维一致性

**Jewelry (首饰):**
- 6维审图（材质色调/款式/尺寸/佩戴位置/扣合/功能）
- 金属反光真实性
- 佩戴位置精度（戒指指围、项链链长）

**Electronics (电子产品):**
- 8维审图（身份/轮廓/尺寸/材质/功能区/状态/交互/配件）
- 功能状态验证（LED颜色、屏幕内容）
- 交互类型正确性（触控 vs 按压）
- 无幻觉零件

**Home Tools (厨房工具):**
- 7维 Tools审图
- 食材交互物理正确性（刀片角度、削皮方向）
- 功能几何验证
- 安全握持检查

**Pet Tools (宠物工具):**
- 7维 Tools审图（宠物特化）
- 宠物舒适度检查（耳朵/眼睛/姿态）
- 物种匹配（猫工具用在猫身上）
- 安全使用验证

## 📋 五类产品测试用例

仓库包含完整的五类产品测试用例：

```bash
# 创建测试用例
python scripts/create_test_cases.py tests/five-products

# 测试产品：
# 1. 纯黑色圆领T恤 (apparel)
# 2. 925纯银戒指 (jewelry)
# 3. 无线蓝牙耳机 (electronics)
# 4. 陶瓷削皮刀 (home-tools)
# 5. 猫咪脱毛梳 (pet-tools)

# 运行分类测试
python scripts/classify_product_category.py tests/five-products

# 查看结果
cat tests/five-products/*/category.json
```

详细测试说明见: `tests/five-products/README.md`

## 🔧 类目配置文件

v2 新增的类目定义文件位于 `references/` 目录：

- `category-home-tools.md` - 厨房/家居工具完整规范
- `category-pet-tools.md` - 宠物工具完整规范
- `category-jewelry.md` - 首饰独立规范（改造自 Accessories）
- `category-electronics.md` - 电子产品完整规范

每个文件包含：
- 审图维度定义
- 场景预设
- 负向增量词表
- Detail Actions 表格
- Character Sheet 适配说明
- 类目特定的交互规则

## 🎨 类目特定的提示词模板

### Apparel (服装)

使用 Virtual Try-On Video 的服装模板：

```
[Scene setup: casual indoor / cafe / street]
[Character: model wearing {product}]
[Camera: static medium shot → dolly in → detail close-up]
[Feature showcase: fabric texture, fit, movement]

7要素锁定: {主色/领口/肩线/袖型/腰线/衣长/面料}
Negative: phantom pockets, wrong color, material mismatch
```

### Jewelry (首饰)

使用改造后的首饰模板：

```
[Scene: jewelry on model, lifestyle context]
[Camera: close-up → extreme macro → rotation under light]
[Feature showcase: metal sheen, stone setting, clasp detail]

6维锁定: {材质色调/款式/尺寸/佩戴位置/扣合/功能}
佩戴位置锁定: ring on {finger} {above/below} knuckle
Negative: floating jewelry, plastic-looking metal, wrong finger size
```

### Electronics (电子产品)

使用 Higgsfield Recipe 3 改造版：

```
Camera: Dolly In from desk setup → close-up on product interaction zone

[Hero moment — {touch sensor lights up} OR {screen wakes} OR {LED pulses} — macro 0.5x slow motion]

8维锁定: {身份/轮廓/尺寸/材质/功能区/状态/交互/配件}
交互类型锁定: touchpad = flat surface (NO depression)
Negative: phantom cables, wrong port count, impossible button position
```

### Home Tools (厨房工具)

使用新建的工具模板：

```
Camera: Dolly In from kitchen counter → close-up on tool + food interaction

[Hero moment — {knife cutting through carrot with clean slice} OR {peeler removing apple ribbon} — macro 0.5x slow motion, physics-accurate]

7维Tools锁定: {类型/材质/功能部件/尺寸/手柄/功能/机械}
食材交互规则: peeler blade 15-30°, peel comes off in ribbon
Negative: impossible food physics, blade phasing through food
```

### Pet Tools (宠物工具)

使用新建的宠物工具模板：

```
Camera: Dolly In from pet setup → close-up on tool + pet interaction

[Hero moment — {brush gliding through fur removing loose hair} — pet calm, macro 0.5x slow motion]

7维Tools锁定 + 宠物舒适度
Pet comfort check: ears forward, eyes soft, body relaxed, NOT (ears back, trying to escape)
Negative: pet distress, unsafe grip, wrong species
```

## ⚙️ 高级用法

### 指定类目运行

如果自动分类不准确，可以手动指定类目：

```bash
# 强制指定为厨房工具
python scripts/analyze_materials.py product-ugc-output/01-product --category home-tools

# 强制指定为宠物工具
python scripts/generate_product_identity_lock.py product-ugc-output/02-product --category pet-tools
```

### 只处理特定类目

```bash
# 只处理服装类产品
python scripts/generate_ugc_prompts.py product-ugc-output --category apparel --count 10

# 只处理电子产品
python scripts/generate_videos_lk888.py product-ugc-output --category electronics --model veo3.1
```

### 批量处理多类目

```bash
# 对所有类目生成提示词
for cat in apparel jewelry electronics home-tools pet-tools; do
  python scripts/generate_ugc_prompts.py product-ugc-output --category $cat --count 5
done
```

## 🔍 QC 检查详解

### 双重一致性检查

v2 的 QC 检查分为两层：

**Layer 1: 产品身份一致性**
- 产品轮廓/尺寸/材质与 identity_lock 匹配
- 功能部件数量/位置正确
- 无幻觉零件

**Layer 2: 使用正确性**
- 交互类型匹配（触控/按压/削/梳等）
- 物理规律正确（食材/宠物/物体行为）
- 安全/舒适度达标（握持/宠物状态）

### 自动重试机制

```bash
# QC 失败自动重新生成
python scripts/qc_dual_consistency.py product-ugc-output --auto-retry-failed --max-retries 3

# 只检查不重试
python scripts/qc_dual_consistency.py product-ugc-output --no-retry

# 生成 QC 报告
python scripts/qc_dual_consistency.py product-ugc-output --report qc_report.json
```

## 📊 性能对比

### 与 v1 对比

| 维度 | v1 | v2 |
|-----|----|----|
| 覆盖类目 | 不明确 | 5大类明确定义 |
| 身份锁定 | 无 | 多视图 Character Sheet |
| QC 检查 | 通用 | 类目专项检查 |
| 翻车率 | ~40% | ~10% (预估) |

### 成本估算（每个产品）

| 阶段 | API 调用 | 预估成本 |
|------|---------|---------|
| 分类 | 0 | $0 |
| 视觉分析 | 1-3 | ~$0.20 |
| 身份锁定 | 3-6 | ~$0.60 |
| 姿态库 | 3-5 | ~$0.50 |
| 关键帧 | 2 | ~$0.40 |
| 视频生成 | 1-10 | ~$5-50 (视频模型) |
| **总计** | | **~$7-52/产品** |

## 🤝 贡献与反馈

### 依赖的开源 Skill

1. **Higgsfield AI Prompt Skill** (MIT)
   - GitHub: https://github.com/OSideMedia/higgsfield-ai-prompt-skill
   - 贡献: MCSLA 公式、Recipe 3 模板、权威分离语法

2. **蓝书 AI Video Kit** (MIT)
   - GitHub: https://github.com/cclank/lanshu-awesome-ai-video-kit
   - 贡献: 543 条 prompt 参考、model-selector、方法论 SOP

3. **Virtual Try-On Video** (Source-available EULA, 个人非商业)
   - GitHub: https://github.com/fsn021920-prog/virtual-try-on-video
   - 贡献: 服装 7要素、Character Sheet、Dual-Consistency QC

### 许可证

本项目 (Product UGC Pipeline v2) 采用 **MIT License**。

依赖的三个 skill 有各自的许可证：
- Higgsfield: MIT ✅ 可商用
- 蓝书: MIT ✅ 可商用
- Virtual Try-On: Source-available EULA ⚠️ 仅个人非商业使用

**如需商用，请：**
1. 只使用 Higgsfield + 蓝书（MIT）
2. 或联系 Virtual Try-On 作者获取商用授权

### 反馈与改进

欢迎提交 Issue 或 PR：
- 新增产品类目支持
- 改进类目定义规范
- 优化 QC 检查逻辑
- 补充测试用例

## 📚 相关文档

- [类目定义规范](./references/)
- [五类产品测试用例](./tests/five-products/README.md)
- [API 接口文档](./docs/API.md)
- [常见问题 FAQ](./docs/FAQ.md)

## 🔗 相关链接

- Seedance 2.0 官方: https://github.com/Emily2040/seedance-2.0
- Higgsfield 官网: https://higgsfield.ai
- 蓝书 Demo: https://lanshu-awesome-ai-video-kit.lank.workers.dev

---

**版本:** v2.0.0  
**更新日期:** 2026-09-04  
**作者:** Product UGC Pipeline Team

