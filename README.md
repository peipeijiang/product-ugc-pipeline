# Product UGC Pipeline

面向电商商品的 UGC 视频生产链路：完整抓取商品素材、逐图视觉分析、商品认知、身份锁、创意风险路由、时间顺序故事板、Omni Flash 全参考视频与 QC。

## 唯一默认视频路径

- 模型：`omni-flash`（可选 `omni_flash-10s`）
- 提供方：LK888/upDrama
- 参考模式：固定 `omni-reference`
- 参考顺序：时间顺序故事板 → 商品身份宫格 → 可选且已过 QC 的操作宫格
- 画幅：默认 `9:16`
- 市场语言：必须显式声明（`--market Japan` 或 `--voice-locale ja-JP`），未声明或无法解析会直接失败，不再静默回落英语

参考图都是全用途参考，不承担时间端点角色。每个版本只生成一张 `generated_images/variant-XX-storyboard.png` 作为完整 0–10 秒时间线的视觉指导。

## 标准流程

```bash
python scripts/scrape_products.py urls.txt --out product-ugc-output
LAOZHANG_API_KEY=sk-... python scripts/analyze_materials.py product-ugc-output --limit-images 0
LAOZHANG_API_KEY=sk-... python scripts/build_product_brief.py product-ugc-output
python scripts/classify_product_category.py product-ugc-output
LK888_API_KEY=sk-... python scripts/generate_product_identity_lock.py product-ugc-output
python scripts/generate_usage_pose_sheet.py product-ugc-output
LAOZHANG_API_KEY=sk-... python scripts/qc_dual_consistency.py product-ugc-output --stage identity
LAOZHANG_API_KEY=sk-... python scripts/generate_ugc_prompts.py product-ugc-output --count 10 --target-video-model omni-flash --market Japan
LK888_API_KEY=sk-... python scripts/generate_images.py product-ugc-output --variants 1-10 --storyboards
LK888_API_KEY=sk-... python scripts/generate_videos_lk888.py product-ugc-output --variants 1-10 --model omni-flash --base-url https://api.lk888.ai --status-endpoint /v1/media/status --reference-mode omni-reference
```

新批次使用 `scripts/run_fresh_batch.py`，它会沿同一条固定路径追加历史感知提示词、生成故事板并提交视频。

完整规则见 `SKILL.md`。

故事板默认 6 宫格（3 列 × 2 行），紧凑情节使用 9 宫格（3 × 3）。单格比例跟随视频，整板比例单独计算。故事板和视频共用 `storyboard_10s`；修改分镜后必须重新生成并质检。
