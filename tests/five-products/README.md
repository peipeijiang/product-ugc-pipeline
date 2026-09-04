# 五类产品完整测试用例

## 测试产品清单

| # | 产品名称 | 类目 | 测试重点 |
|---|---------|------|---------|
| 1 | 纯黑色圆领T恤 | apparel | 7要素审图、布料行为、单张 2×2 宫格 |
| 2 | 925纯银戒指 | jewelry | 6维审图、金属反光、佩戴位置精度 |
| 3 | 无线蓝牙耳机 | electronics | 8维审图、触控 vs 按压、无幻觉零件 |
| 4 | 陶瓷削皮刀 | home-tools | 7维Tools、食材交互物理、安全握持 |
| 5 | 猫咪脱毛梳 | pet-tools | 7维Tools、宠物舒适度、顺毛梳理 |

## 测试流程

### 1. 分类测试

```bash
python scripts/classify_product_category.py tests/five-products
```

**预期结果：**
- 01-black-tshirt → apparel
- 02-silver-ring → jewelry
- 03-bluetooth-earbuds → electronics
- 04-ceramic-peeler → home-tools
- 05-pet-brush → pet-tools

### 2. 视觉分析测试（需要 API Key）

```bash
# 注意：这需要真实图片，测试用例中只有占位符
# 如果要完整测试，需要先爬取真实产品或手动准备图片

LAOZHANG_API_KEY=sk-xxx python scripts/analyze_materials.py tests/five-products --category apparel
LAOZHANG_API_KEY=sk-xxx python scripts/analyze_materials.py tests/five-products --category jewelry
# ... 依此类推
```

### 3. 生成身份锁定测试（需要 API Key）

```bash
# Apparel: 单张 2×2 宫格
LAOZHANG_API_KEY=sk-xxx python scripts/generate_product_identity_lock.py tests/five-products/01-black-tshirt

# Jewelry: 单张 1×3 宫格
LAOZHANG_API_KEY=sk-xxx python scripts/generate_product_identity_lock.py tests/five-products/02-silver-ring

# Electronics: 单张 2×3 宫格
LAOZHANG_API_KEY=sk-xxx python scripts/generate_product_identity_lock.py tests/five-products/03-bluetooth-earbuds

# Home Tools: 单张宫格 3+2
LAOZHANG_API_KEY=sk-xxx python scripts/generate_product_identity_lock.py tests/five-products/04-ceramic-peeler

# Pet Tools: 单张宫格 3+2 + 宠物参考
LAOZHANG_API_KEY=sk-xxx python scripts/generate_product_identity_lock.py tests/five-products/05-pet-brush
```

### 4. QC 检查测试

每个类目有专属的检查项：

| 类目 | 专属检查项 |
|------|-----------|
| apparel | 布料行为、版型保持、人脸8维 |
| jewelry | 金属反光、佩戴位置、尺寸精度 |
| electronics | 功能状态、交互类型、无幻觉零件 |
| home-tools | 食材交互物理、功能几何、安全握持 |
| pet-tools | 宠物舒适度、物种匹配、安全使用 |

## 关键验证点

### T恤 (apparel)
- [ ] 7要素全部识别正确
- [ ] 单张 2×2 宫格生成
- [ ] 负向词包含"无口袋、无图案"
- [ ] 布料行为描述（垂坠、弹性）

### 戒指 (jewelry)
- [ ] 6维审图准确（材质/款式/尺寸/佩戴/扣合/功能）
- [ ] 单张 1×3 宫格生成
- [ ] 佩戴位置锁定表完整
- [ ] 金属反光规则清晰

### 耳机 (electronics)
- [ ] 8维审图完整
- [ ] 触控 vs 按压区分明确
- [ ] 单张 2×3 宫格覆盖所有接口
- [ ] 无幻觉零件列表（无电线、无物理按键）

### 削皮刀 (home-tools)
- [ ] 7维Tools审图
- [ ] 食材交互规则（苹果削皮物理正确）
- [ ] 单张宫格含 in-use grip 格
- [ ] 安全使用说明

### 宠物梳 (pet-tools)
- [ ] 7维Tools审图（宠物特化）
- [ ] 宠物舒适度检查表
- [ ] 单张宫格 + 宠物参考格
- [ ] 禁止表现列表（耳朵后贴、试图逃跑）

## 预期输出文件

每个产品文件夹应包含：

```
01-black-tshirt/
├── product_manifest.json
├── category.json              # category: apparel
├── product_brief.json
├── identity_lock/             # 单张多宫格参考图
│   ├── manifest.json
│   ├── reference_sheet.png          # 单张多宫格（替代原多张单图）
├── usage_poses/               # 3个 Detail Actions
│   ├── manifest.json
│   ├── panel_0_unfold.png
│   ├── panel_1_wear.png
│   └── panel_2_turn.png
└── ugc_prompts.json
```

## 注意事项

1. **真实图片缺失：** 当前测试用例只包含JSON数据，没有真实产品图片。要运行完整流程，需要：
   - 从真实电商网站爬取这五类产品
   - 或手动准备对应类型的产品图片放入 images/ 目录

2. **API Key 需求：** 视觉分析和身份锁定生成需要 LaoZhang API Key

3. **类目定义文件：** 确保以下文件存在：
   - references/category-home-tools.md
   - references/category-pet-tools.md
   - references/category-jewelry.md
   - references/category-electronics.md

4. **Virtual Try-On 依赖：** Apparel 类目依赖 Virtual Try-On Video skill 的服装类目文件
