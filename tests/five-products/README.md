# 五类产品测试夹具

这些 JSON 用例验证五类字段结构和分类结果，不含真实商品图片，不能用于生图、视频生成或质量/成本评测。生产脚本会读取 `fixture_only` 并停止付费生成。

## 测试产品清单

| # | 产品名称 | 类目 | 测试重点 |
|---|---------|------|---------|
| 1 | 纯黑色圆领T恤 | apparel | 7要素、单张 2行×2列宫格 |
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

### 2. 离线契约测试

```bash
python3 -m unittest discover -s tests -p 'test_v2*.py' -v
```

真实端到端测试需要为每类另建产品目录，放入真实原图并依次运行视觉分析、简报、单张宫格、质检、首尾帧和视频。不要移除 fixture_only 后继续使用这里的虚构规格。

### 3. QC 检查维度

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
- [ ] Character Sheet 4视图生成
- [ ] 负向词包含"无口袋、无图案"
- [ ] 布料行为描述（垂坠、弹性）

### 戒指 (jewelry)
- [ ] 6维审图准确（材质/款式/尺寸/佩戴/扣合/功能）
- [ ] 3视图 + 特写生成
- [ ] 佩戴位置锁定表完整
- [ ] 金属反光规则清晰

### 耳机 (electronics)
- [ ] 8维审图完整
- [ ] 触控 vs 按压区分明确
- [ ] 6视图覆盖所有接口
- [ ] 无幻觉零件列表（无电线、无物理按键）

### 削皮刀 (home-tools)
- [ ] 7维Tools审图
- [ ] 食材交互规则（苹果削皮物理正确）
- [ ] 5视图包含in-use grip
- [ ] 安全使用说明

### 宠物梳 (pet-tools)
- [ ] 7维Tools审图（宠物特化）
- [ ] 宠物舒适度检查表
- [ ] 5视图 + 宠物参考
- [ ] 禁止表现列表（耳朵后贴、试图逃跑）

## 注意事项

1. **真实图片缺失：** 当前测试用例只包含JSON数据，没有真实产品图片。要运行完整流程，需要：
   - 从真实电商网站爬取这五类产品
   - 或手动准备对应类型的产品图片放入 images/ 目录

2. **不调用 API：** 这些夹具只用于分类和结构检查。

3. **类目定义文件：** 确保以下文件存在：
   - references/category-home-tools.md
   - references/category-pet-tools.md
   - references/category-jewelry.md
   - references/category-electronics.md
   - references/category-apparel.md
