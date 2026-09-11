#!/usr/bin/env python3
"""
Product Category Classifier for UGC Pipeline v2

Automatically classifies products into one of 6 categories, or stops as unclassified:
- apparel (服装): tops, pants, dresses, etc.
- jewelry (首饰): rings, necklaces, earrings, etc.
- electronics (电子产品/玩具): earbuds, speakers, toy blocks, etc.
- home-tools (厨房/家居工具): knife, peeler, spatula, etc.
- pet-tools (宠物工具): brush, leash, collar, etc.
- furniture (家具): chairs, loungers, cots, stools, tables
"""

import json
import re
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def classify_by_keywords(title: str) -> tuple[str | None, float]:
    """Classify by keyword matching"""
    title_lower = title.lower()

    def matches(keywords: list[str]) -> bool:
        for keyword in keywords:
            if keyword.isascii():
                if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", title_lower):
                    return True
            elif keyword in title_lower:
                return True
        return False
    
    # 服装关键词
    apparel_keywords = [
        "shirt", "dress", "pants", "jacket", "coat", "skirt", "sweater", "hoodie",
        "t-shirt", "jeans", "blazer", "vest", "shorts", "leggings", "swimsuit",
        "衬衫", "连衣裙", "裤子", "外套", "裙子", "毛衣", "卫衣", "牛仔裤", "tshirt", "t恤"
    ]
    
    # 首饰关键词
    jewelry_keywords = [
        "ring", "necklace", "earring", "bracelet", "watch", "pendant", "brooch",
        "戒指", "项链", "耳环", "手链", "手表", "吊坠", "胸针"
    ]
    
    # 电子产品关键词
    electronics_keywords = [
        "earbuds", "speaker", "charger", "mouse", "keyboard", "power bank",
        "headphone", "airpods", "smartwatch", "cable", "adapter", "usb",
        "耳机", "音箱", "充电", "键盘", "鼠标", "充电宝", "数据线", "蓝牙"
    ]
    
    # 积木玩具关键词（归入 electronics）
    toy_keywords = [
        "blocks", "lego", "building", "toy", "puzzle", "积木", "拼装", "玩具"
    ]
    
    # 厨房/家居工具关键词
    home_tools_keywords = [
        "knife", "peeler", "grater", "strainer", "spatula", "whisk", 
        "measuring cup", "scissors", "opener", "cutting board", "utensil",
        "菜刀", "削皮刀", "刨丝器", "滤网", "锅铲", "打蛋器", "量杯", "剪刀", "厨具", "削皮"
    ]
    
    # 宠物工具关键词
    pet_tools_keywords = [
        "pet brush", "pet comb", "nail clipper", "dog leash", "cat collar",
        "pet bowl", "pet toy", "grooming", "de-shedding", "cat", "dog",
        "宠物梳", "宠物指甲剪", "牵引绳", "宠物项圈", "宠物碗", "宠物玩具", "猫", "狗", "猫咪", "脱毛"
    ]

    furniture_keywords = [
        "folding chair", "foldable chair", "reclining chair", "lounge chair", "camp chair", "moon chair",
        "camping cot", "folding cot", "camp cot", "stool", "folding table", "recliner", "折叠椅", "折りたたみチェア",
        "リクライニングチェア", "躺椅", "月亮椅", "行军床", "折叠桌",
    ]
    
    # 检查匹配
    if matches(apparel_keywords):
        return "apparel", 0.95
    elif matches(jewelry_keywords):
        return "jewelry", 0.95
    elif matches(furniture_keywords):
        return "furniture", 0.95
    elif matches(electronics_keywords + toy_keywords):
        return "electronics", 0.95
    elif matches(home_tools_keywords):
        return "home-tools", 0.95
    elif matches(pet_tools_keywords):
        return "pet-tools", 0.95
    
    return None, 0.0


def classify_by_image_features(product_folder: Path) -> tuple[str | None, float]:
    """
    Fallback: classify by image analysis features
    
    This is a simple heuristic. In production, you might use a vision model.
    """
    image_analysis_path = product_folder / "image_analysis.json"
    
    if not image_analysis_path.exists():
        return None, 0.0
    
    analysis = load_json(image_analysis_path)
    
    # 简单启发式：根据材质和形状猜测
    materials = str(analysis.get("materials", "")).lower()
    
    # Generic fabric and generic plastic are not category evidence: sleeping bags,
    # tents, chairs and cases would otherwise become apparel/electronics.
    if "metal" in materials and ("ring" in materials or "chain" in materials):
        return "jewelry", 0.70
    elif "stainless steel" in materials and ("blade" in materials or "handle" in materials):
        return "home-tools", 0.70
    
    # Unknown is safer than routing a sleeping bag, tent, pole or other unsupported
    # product through an electronics checklist and paying for the wrong identity grid.
    return None, 0.0


def classify_product(product_folder: Path, force: bool = False) -> dict:
    """Main classification logic"""
    
    category_file = product_folder / "category.json"
    
    # 如果已经分类过且不强制重新分类，直接返回
    if category_file.exists() and not force:
        existing = load_json(category_file)
        print(f"  已分类: {existing['category']} (confidence: {existing['confidence']:.2f})")
        return existing
    
    # 加载产品清单
    manifest_path = product_folder / "product_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"product_manifest.json not found in {product_folder}")
    
    manifest = load_json(manifest_path)
    title = manifest.get("product_name", "")
    
    # 1. 尝试关键词分类
    category, confidence = classify_by_keywords(title)
    detected_from = "title_keywords"
    
    # 2. 如果关键词失败，使用图像特征
    if category is None:
        category, confidence = classify_by_image_features(product_folder)
        detected_from = "image_features"
    
    # 保存结果
    result = {
        "category": category or "unclassified",
        "detected_from": detected_from,
        "confidence": confidence,
        "product_name": title,
        "requires_manual_category": category is None,
    }
    
    save_json(category_file, result)
    
    if category is None:
        print("  未匹配现有类目：请显式选择或新增真实类目，身份图生成会保持阻断")
    else:
        print(f"  分类为: {category} (confidence: {confidence:.2f}, from: {detected_from})")
    
    return result


def main():
    if len(sys.argv) < 2:
        print("用法: python classify_product_category.py <product_output_folder> [--force]")
        print("示例: python classify_product_category.py product-ugc-output")
        sys.exit(1)
    
    output_root = Path(sys.argv[1])
    force = "--force" in sys.argv
    
    if not output_root.exists():
        print(f"错误: 目录不存在: {output_root}")
        sys.exit(1)
    
    # 遍历所有产品文件夹
    product_folders = sorted([d for d in output_root.iterdir() if d.is_dir()])
    
    if not product_folders:
        print(f"未找到产品文件夹: {output_root}")
        sys.exit(1)
    
    print(f"\n开始分类 {len(product_folders)} 个产品...\n")
    
    results = {}
    for folder in product_folders:
        print(f"处理: {folder.name}")
        try:
            result = classify_product(folder, force=force)
            results[folder.name] = result["category"]
        except Exception as e:
            print(f"  错误: {e}")
            results[folder.name] = "error"
    
    # 统计
    print(f"\n分类统计:")
    from collections import Counter
    counts = Counter(results.values())
    for cat, count in sorted(counts.items()):
        print(f"  {cat}: {count}")
    
    print(f"\n完成！")


if __name__ == "__main__":
    main()
