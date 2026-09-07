#!/usr/bin/env python3
"""
五类产品完整测试用例

测试产品：
1. Apparel: 黑色圆领T恤
2. Jewelry: 银色戒指
3. Electronics: 无线蓝牙耳机
4. Home Tools: 陶瓷削皮刀
5. Pet Tools: 猫咪脱毛梳
"""

import json
from pathlib import Path


# 测试用例数据
TEST_PRODUCTS = {
    "01-black-tshirt": {
        "category": "apparel",
        "product_name": "纯黑色圆领短袖T恤 男女同款",
        "source_url": "https://example.com/tshirt",
        "expected_identity_views": 4,  # Character Sheet 4视图
        "expected_detail_actions": 3,
        "key_checks": [
            "7要素审图 (主色/领口/肩线/袖型/腰线/衣长/面料)",
            "布料动态行为 (垂坠/接缝/弹性)",
            "人脸8维一致性"
        ],
        "mock_manifest": {
            "product_name": "纯黑色圆领短袖T恤 男女同款",
            "source_url": "https://example.com/tshirt",
            "scraped_at": "2026-09-04T10:00:00Z",
            "images": ["image_0.jpg", "image_1.jpg", "image_2.jpg"],
            "price": "¥89",
            "description": "100%纯棉 舒适透气 圆领设计 宽松版型"
        },
        "mock_brief": {
            "product_name": "纯黑色圆领短袖T恤",
            "confidence": "high",
            "confirmed_identity": {
                "主色": "纯黑色",
                "领口": "圆领",
                "肩线": "落肩设计",
                "袖型": "短袖 袖长至上臂中部",
                "腰线": "直筒",
                "衣长": "中长款 覆盖腰部",
                "面料": "纯棉针织 表面光滑无起球"
            },
            "step_by_step_usage": [
                {"step": 1, "action": "展开T恤，展示正面版型", "evidence": "page_text"},
                {"step": 2, "action": "穿上T恤，展示肩线和袖长", "evidence": "image_analysis"},
                {"step": 3, "action": "转身展示背面和衣长", "evidence": "inference"}
            ],
            "hallucination_defense": {
                "phantom_parts": ["无口袋", "无图案", "无拉链", "无帽子"],
                "shape_preservation": "直筒版型 不能变成修身或oversize",
                "material_texture_lock": "纯棉针织 不能变成丝绸或牛仔",
                "action_bounds": "可以穿脱、展示、叠放；不能淋湿、剪裁、染色",
                "scale_anchor": "成人T恤 肩宽45-50cm"
            }
        }
    },
    
    "02-silver-ring": {
        "category": "jewelry",
        "product_name": "925纯银戒指 简约光面设计",
        "source_url": "https://example.com/ring",
        "expected_identity_views": 3,  # 3视图 + 特写
        "expected_detail_actions": 4,
        "key_checks": [
            "首饰6维审图 (材质色调/款式结构/尺寸规格/佩戴位置/扣合机制/功能细节)",
            "金属反光真实性",
            "戒圈与手指的比例精度"
        ],
        "mock_manifest": {
            "product_name": "925纯银戒指 简约光面设计",
            "source_url": "https://example.com/ring",
            "scraped_at": "2026-09-04T10:05:00Z",
            "images": ["ring_0.jpg", "ring_1.jpg"],
            "price": "¥199",
            "description": "925纯银 光面抛光 开口可调节 内径17mm"
        },
        "mock_brief": {
            "product_name": "925纯银戒指",
            "confidence": "high",
            "confirmed_identity": {
                "材质色调": "925纯银 抛光光面 银白色",
                "款式结构": "简约素圈 开口可调节设计",
                "尺寸规格": "内径17mm 宽度3mm 厚度1.5mm",
                "佩戴位置": "无名指或中指 戒圈位于指节上方",
                "扣合机制": "开口设计 可微调松紧",
                "功能细节": "可调节大小 适合16-18号指围"
            },
            "step_by_step_usage": [
                {"step": 1, "action": "展示戒指平铺状态，可见开口", "evidence": "page_text"},
                {"step": 2, "action": "慢慢戴入无名指，停在指节上方", "evidence": "image_analysis"},
                {"step": 3, "action": "旋转手部，展示金属反光", "evidence": "inference"},
                {"step": 4, "action": "特写开口处，展示可调节设计", "evidence": "page_text"}
            ],
            "hallucination_defense": {
                "phantom_parts": ["无宝石", "无雕刻", "无链条", "无品牌LOGO"],
                "shape_preservation": "圆环形 开口约2mm 不能闭合成完整圆",
                "material_texture_lock": "银白色金属 镜面抛光 有金属反光",
                "action_bounds": "可以戴上、取下、旋转；不能弯曲过度、不能变形",
                "scale_anchor": "内径17mm 相当于成人女性无名指尺寸"
            }
        }
    },
    
    "03-bluetooth-earbuds": {
        "category": "electronics",
        "product_name": "无线蓝牙耳机 半入耳式 触控操作",
        "source_url": "https://example.com/earbuds",
        "expected_identity_views": 6,  # 6视图参考
        "expected_detail_actions": 5,
        "key_checks": [
            "电子产品8维审图 (身份/轮廓/尺寸/材质/功能区/功能状态/交互类型/配件)",
            "触控操作 vs 按压按钮的区分",
            "充电盒与耳机的尺寸比例",
            "无幻觉零件（电线/按键/屏幕）"
        ],
        "mock_manifest": {
            "product_name": "无线蓝牙耳机 半入耳式 触控操作",
            "source_url": "https://example.com/earbuds",
            "scraped_at": "2026-09-04T10:10:00Z",
            "images": ["earbuds_0.jpg", "earbuds_1.jpg", "earbuds_2.jpg"],
            "price": "¥299",
            "description": "蓝牙5.3 触控操作 充电盒续航30小时 IPX4防水"
        },
        "mock_brief": {
            "product_name": "无线蓝牙耳机",
            "confidence": "high",
            "confirmed_identity": {
                "产品身份": "无线蓝牙耳机 半入耳式 左右独立",
                "外观轮廓": "卵形耳机头 细长柄 充电盒椭圆形",
                "尺寸规格": "耳机31mm×17mm×20mm 充电盒60mm×45mm×25mm",
                "材质表面": "哑光白色塑料外壳 硅胶耳帽",
                "功能区域": "触控面板在柄部上方 充电盒顶部有LED指示灯",
                "功能状态": "LED指示灯（白色=充满 红色=充电中）",
                "交互类型": "触控操作（轻触1次=播放/暂停 触2次=下一曲）",
                "配件组件": "充电盒 USB-C充电线"
            },
            "step_by_step_usage": [
                {"step": 1, "action": "打开充电盒盖，耳机在盒内", "evidence": "page_text"},
                {"step": 2, "action": "手指取出右耳机，握住耳机柄", "evidence": "image_analysis"},
                {"step": 3, "action": "轻触柄部触控区（平面无凹陷）", "evidence": "page_text"},
                {"step": 4, "action": "将耳机戴入耳朵，半入耳状态", "evidence": "inference"}
            ],
            "hallucination_defense": {
                "phantom_parts": ["无物理按键", "无电线", "无麦克风孔（内置）", "无品牌LOGO"],
                "shape_preservation": "卵形+细柄 充电盒椭圆形 不能变圆形或方形",
                "material_texture_lock": "哑光白色塑料 不能变金属或透明",
                "action_bounds": "可以取出、戴入、触控；不能按压（触控区是平面）",
                "context_contamination": "不能出现有线耳机线、头戴式耳机头梁",
                "scale_anchor": "耳机长31mm 相当于成人食指第一节长度"
            }
        }
    },
    
    "04-ceramic-peeler": {
        "category": "home-tools",
        "product_name": "陶瓷削皮刀 蓝色手柄 锋利耐用",
        "source_url": "https://example.com/peeler",
        "expected_identity_views": 5,  # 5视图 Tools
        "expected_detail_actions": 4,
        "key_checks": [
            "工具7维审图 (类型/材质/功能部件/尺寸/手柄/功能特征/机械结构)",
            "食材交互物理正确性（苹果削皮）",
            "刀片角度15-30度",
            "手部握持安全性"
        ],
        "mock_manifest": {
            "product_name": "陶瓷削皮刀 蓝色手柄 锋利耐用",
            "source_url": "https://example.com/peeler",
            "scraped_at": "2026-09-04T10:15:00Z",
            "images": ["peeler_0.jpg", "peeler_1.jpg"],
            "price": "¥39",
            "description": "黑色陶瓷刀片 人体工学手柄 适合削苹果土豆胡萝卜"
        },
        "mock_brief": {
            "product_name": "陶瓷削皮刀",
            "confidence": "high",
            "confirmed_identity": {
                "工具类型": "Y型削皮刀",
                "主体材质": "蓝色ABS塑料手柄 黑色陶瓷刀片",
                "功能部件": "Y型刀片宽4cm 刀刃锋利 两侧有削皮槽",
                "尺寸规格": "总长17cm 手柄长11cm 刀片宽4cm",
                "手柄设计": "人体工学弧形 表面磨砂防滑",
                "功能特征": "陶瓷刀片不生锈 削皮薄而均匀",
                "机械结构": "一体成型 无活动部件"
            },
            "step_by_step_usage": [
                {"step": 1, "action": "手握削皮刀手柄，刀片朝前", "evidence": "page_text"},
                {"step": 2, "action": "另一手固定苹果，削皮刀刀片贴近苹果表面", "evidence": "image_analysis"},
                {"step": 3, "action": "刀片角度20度左右，向下缓慢拉动，苹果皮呈带状脱落", "evidence": "inference"},
                {"step": 4, "action": "削皮完成，展示光滑苹果表面", "evidence": "inference"}
            ],
            "hallucination_defense": {
                "phantom_parts": ["无额外刀片", "无品牌文字", "无折叠结构"],
                "shape_preservation": "Y型结构 手柄直 刀片Y型开叉",
                "material_texture_lock": "蓝色塑料哑光 黑色陶瓷有轻微反光",
                "action_bounds": "可以削皮、展示、清洗；不能切硬物、不能弯曲刀片",
                "context_contamination": "不能出现金属菜刀、砧板上的切菜动作",
                "scale_anchor": "总长17cm 相当于成人手掌宽度+1个手指"
            }
        }
    },
    
    "05-pet-brush": {
        "category": "pet-tools",
        "product_name": "猫咪脱毛梳 蓝色手柄 不锈钢梳齿",
        "source_url": "https://example.com/pet-brush",
        "expected_identity_views": 5,  # 5视图 + 宠物参考
        "expected_detail_actions": 4,
        "key_checks": [
            "工具7维审图 (宠物工具特化)",
            "宠物舒适度检查（猫咪放松/享受/接受）",
            "梳毛方向顺毛",
            "无宠物痛苦表现"
        ],
        "mock_manifest": {
            "product_name": "猫咪脱毛梳 蓝色手柄 不锈钢梳齿",
            "source_url": "https://example.com/pet-brush",
            "scraped_at": "2026-09-04T10:20:00Z",
            "images": ["brush_0.jpg", "brush_1.jpg"],
            "price": "¥59",
            "description": "不锈钢梳齿 去除浮毛 一键清理按钮 适合长毛猫"
        },
        "mock_brief": {
            "product_name": "猫咪脱毛梳",
            "confidence": "high",
            "confirmed_identity": {
                "工具类型": "脱毛梳 针对长毛猫",
                "主体材质": "蓝色ABS塑料手柄 不锈钢梳齿",
                "功能部件": "梳齿密度中等 齿长15mm 梳头宽6cm",
                "尺寸规格": "总长15cm 梳头宽6cm 厚度2cm",
                "手柄设计": "人体工学握柄 防滑纹理",
                "宠物安全特征": "梳齿圆头 不刮伤皮肤",
                "机械结构": "一键清理按钮 可弹出收集的毛发"
            },
            "step_by_step_usage": [
                {"step": 1, "action": "猫咪坐在沙发上，身体放松", "evidence": "page_text"},
                {"step": 2, "action": "手握脱毛梳，梳齿朝下", "evidence": "image_analysis"},
                {"step": 3, "action": "从猫咪头部向尾部方向缓慢梳理，顺毛方向", "evidence": "inference"},
                {"step": 4, "action": "梳齿收集浮毛，按清理按钮弹出毛团", "evidence": "page_text"}
            ],
            "hallucination_defense": {
                "phantom_parts": ["无电动马达", "无品牌LOGO", "无额外刷头"],
                "shape_preservation": "长方形梳头 直柄 梳齿垂直向下",
                "material_texture_lock": "蓝色塑料哑光 不锈钢梳齿有金属光泽",
                "action_bounds": "可以梳毛、清理浮毛、按按钮；不能逆毛梳、不能戳猫",
                "context_contamination": "不能出现狗、小型宠物（仓鼠）、人类用的梳子",
                "scale_anchor": "总长15cm 适合单手握持"
            },
            "pet_comfort_requirements": {
                "target_pet": "长毛猫（橘猫/布偶/波斯等）",
                "acceptable_body_language": [
                    "坐姿放松，耳朵自然朝前",
                    "眼睛半闭或温和注视",
                    "身体微微前倾（享受）或保持静止（接受）",
                    "尾巴平放或缓慢摆动"
                ],
                "forbidden_body_language": [
                    "耳朵后贴",
                    "瞳孔放大、眼睛瞪圆",
                    "身体紧绷、试图逃跑",
                    "尾巴炸毛或快速甩动",
                    "发出嘶嘶声或低吼"
                ]
            }
        }
    }
}


def create_test_structure(output_root: Path):
    """创建仅用于分类和字段结构检查的合成夹具。"""
    output_root.mkdir(parents=True, exist_ok=True)
    
    for folder_name, data in TEST_PRODUCTS.items():
        folder = output_root / folder_name
        folder.mkdir(exist_ok=True)
        
        # 创建 images 子目录
        (folder / "images").mkdir(exist_ok=True)
        
        # 标记为合成夹具，生产脚本会拒绝把它当成真实商品资料。
        data["mock_manifest"]["fixture_only"] = True
        data["mock_manifest"]["images"] = []
        data["mock_manifest"]["fixture_notice"] = "No real product images; do not run paid generation."
        # 保存 product_manifest.json
        manifest_path = folder / "product_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data["mock_manifest"], f, ensure_ascii=False, indent=2)
        
        # 保存 product_brief.json
        brief_path = folder / "product_brief.json"
        with open(brief_path, "w", encoding="utf-8") as f:
            json.dump(data["mock_brief"], f, ensure_ascii=False, indent=2)

        category_path = folder / "category.json"
        with open(category_path, "w", encoding="utf-8") as f:
            json.dump({"category": data["category"], "confidence": 1.0,
                       "detected_from": "declared_test_fixture"}, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 创建测试用例: {folder_name} ({data['category']})")


def generate_test_readme(output_root: Path):
    """生成测试说明文档"""
    readme_content = """# 五类产品测试夹具

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
"""
    
    readme_path = output_root / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    print(f"✅ 创建测试说明: {readme_path}")


def main():
    import sys
    
    if len(sys.argv) < 2:
        output_root = Path("tests/five-products")
        print(f"使用默认输出路径: {output_root}")
    else:
        output_root = Path(sys.argv[1])
    
    print(f"\n创建五类产品测试用例: {output_root}\n")
    
    create_test_structure(output_root)
    generate_test_readme(output_root)
    
    print(f"\n✅ 测试用例创建完成！")
    print(f"\n下一步:")
    print(f"1. cd {output_root.parent.parent}")
    print(f"2. python scripts/classify_product_category.py {output_root}")
    print(f"3. 查看分类结果: cat {output_root}/*/category.json")


if __name__ == "__main__":
    main()
