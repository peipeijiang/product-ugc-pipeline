# Product UGC Pipeline v2

从商品资料到带货视频：先用真实产品图生成身份宫格；若商品需要折叠、组装、安装或伸缩，再自动生成一张有证据约束的状态转换宫格。随后生成正常单画面的场景首尾帧，最后交给原有 VEO 3.1 / Omni Flash 视频接口。

三个 v2 核心脚本现已实现并接入现有流程。软件回归测试使用模拟 API；尚未完成五类商品的真实付费视频质量评测，不能据此宣称降低多少翻车率。

## 核心流程

| 环节 | 做什么 | 实际输出 / 模型 |
|---|---|---|
| 产品认知 | 分析原图、核对外观和操作依据 | image_analysis.json、product_brief.json；沿用原视觉/文本模型 |
| 身份参考 | 将同一商品多个角度和使用关系放入一张图 | identity_lock/reference_sheet.png；GPT-Image-2 |
| 状态与使用 | 记录有依据的动作；变形商品另生成端点/转换宫格 | usage_poses/manifest.json；静态商品默认无额外调用 |
| 宫格质检 | 对比真实原图检查身份、比例、接触位置 | qc/identity.json；可配置视觉模型，默认 gpt-5.2 |
| 场景首尾帧 | 原图和宫格指导单画面生图；尾帧另参考首帧 | generated_images/variant-XX-start/end.png；GPT-Image-2 |
| 帧质检与视频 | 检查当前参考链和首尾帧，通过后提交视频 | 原有 VEO 3.1 / Omni Flash |
| 成片质检 | 抽帧检查外观、比例、动作顺序和类目细节 | qc/videos.json；视觉模型，需 ffmpeg/ffprobe |

“权威分离”是明确说明各类资料负责什么：真实商品图负责外观，有依据的说明负责尺寸/功能，场景首帧负责人物/环境连续性。它不是视频接口的数值权重。生成宫格仍可能画错，必须与原图对照质检。

## 内置类目与图片数量

内置 6 个类目。若商品确实不属于任何一个，按 [SKILL.md](SKILL.md) 的“Adding a
product category that does not exist yet”自行补充类目，不要硬塞进最接近的类目。

| 类目 | 默认新增参考图 | 专项检查 |
|---|---|---|
| 服装 apparel | 1 张，2 行 × 2 列 | 颜色、领口、肩线、袖型、腰线、衣长、面料和穿着贴合 |
| 首饰 jewelry | 1 张，1 行 × 3 列 | 材质、款式、尺寸关系、佩戴位置、扣合、细节 |
| 电子产品 electronics | 1 张，2 行 × 3 列 | 外形、接口/按键、交互方式、支撑位置、功能状态 |
| 厨房/家居工具 home-tools | 1 张，上 3 下 2 | 握持、刃口/工作部件、食材接触、重力和比例 |
| 宠物工具 pet-tools | 1 张，上 3 下 2 | 接触位置、毛发/皮肤关系、宠物体型、姿态 |
| 家具 furniture | 1 张，上 3 下 2 | 结构、铰链与调节机构、重力与承重路径、人与家具的接触位置和比例 |

静态商品默认只新增 1 张身份宫格，三个广告共用。需要折叠、组装、安装、伸缩或开合的商品必须在 `product_brief.json` 中提供 `state_change_contract`，流程会自动再生成 1 张状态转换宫格；只有端点图证据时只画端点并强制硬切，不能臆造中间动作。静态商品仅在显式传入 `--separate-sheet` 时新增使用姿态宫格。每个视频仍需要自己的场景首尾帧。

## 安装与运行

Python 3.10+；成片抽帧另需 ffmpeg 和 ffprobe。生图与视频通过云 API，运行脚本不要求本地 GPU。

```bash
git clone --branch v2-five-categories https://github.com/peipeijiang/product-ugc-pipeline.git
cd product-ugc-pipeline
pip install -r requirements.txt
export LAOZHANG_API_KEY="your-key"
export LK888_API_KEY="your-key"
```

先按 [SKILL.md](SKILL.md) 完成爬取、视觉分析和产品简报。需要真实原图以及每个动作的 evidence；来源不明或写着 inference 的动作会停止生成。脚本不能自动保证资料本身真实，请核对商品型号、规格和使用方式。

```bash
python scripts/classify_product_category.py output
python scripts/analyze_materials.py output
python scripts/build_product_brief.py output

python scripts/generate_product_identity_lock.py output
python scripts/generate_usage_pose_sheet.py output
python scripts/qc_dual_consistency.py output --stage identity
python scripts/qc_dual_consistency.py output --stage usage  # 仅当生成了独立使用/状态宫格

python scripts/generate_ugc_prompts.py output --count 3
python scripts/generate_images.py output --variants 1-3 --keyframes
python scripts/qc_dual_consistency.py output --stage keyframes --variants 1-3

python scripts/generate_videos_lk888.py output --variants 1-3 --model veo3.1
python scripts/qc_dual_consistency.py output --stage videos --variants 1-3
```

图像默认走 upDrama 的 `tt-image-2.5` 媒体任务通道（`LK888_API_KEY` / `UPDRAMA_API_KEY`），失败时自动依次退到 `tt-image-2` 和 LaoZhang 的 GPT-Image-2 `/images/edits`。每张图的 `image_provider` 和 `provider_fallbacks` 记录在 `generated_images/image_generation_results.json`。需要强制单通道时：

```bash
python scripts/generate_images.py output --variants 1-3 --keyframes \
  --image-provider laozhang-image2 --image-fallback none --model gpt-image-2-vip --size 1024x1536
```

Omni Flash 是显式选择，沿用原接口：

```bash
python scripts/generate_videos_lk888.py output --variants 1-3 --model omni-flash --base-url https://api.lk888.ai --status-endpoint /v1/media/status --reference-mode first-last
```

`omni-flash` 在本技能中默认生成 10 秒视频，支持 4/6/8/10 秒。`--reference-mode first-last` 使用已生成并通过 QC 的首帧和尾帧；`--reference-mode omni-reference` 至少使用 Image2 时序故事板 + 当前产品身份宫格。若该商品生成了状态转换宫格，适配器会在其通过 usage QC 后自动作为第 3 张参考图。真实主图仍是上游商品真值。提示词会自动压缩到 Updrama 的 4,000 字符上限内。

新脚本均可传入批次目录或单个商品目录；`--products 01,03` 选择批次内商品。新身份脚本支持 `--category electronics` 显式指定类目。旧分类器是关键词/启发式规则，confidence 不是统计准确率。

## 失败如何处理

质检输出 pass / fail / needs_review / error；任意必需检查失败或看不清都不会作为通过。修正资料或提示词后，用对应生图脚本的 `--force` 重生成，再重新质检。没有实现自动付费重拍；旧文档的 `--auto-retry-failed`、`--max-retries` 说明已撤回。

原始资料、宫格、场景参考或质检上下文发生变化时，文件摘要会使旧结果失效。没有 v2 宫格目录的旧项目继续使用原流程；启用 v2 后，旧版无引用记录的帧须重新生成。

抽帧 QC 不是完整视频理解，也不检查音频；它可能漏掉帧间短暂错误。未知尺寸不能靠手掌或提示词变成精确毫米。最终成片仍需要人工观看。

## 验证与文档

```bash
python3 -m unittest discover -s tests -p 'test_v2*.py' -v
```

[实现与字段说明](README_V2.md) · [状态转换商品规范](references/state-change-products.md) · [五类产品测试用例](tests/five-products/README.md) · [Skill 规范](SKILL.md)

## 来源与许可

方案参考 [Higgsfield AI Prompt Skill](https://github.com/OSideMedia/higgsfield-ai-prompt-skill)、[蓝书 AI Video Kit](https://github.com/cclank/lanshu-awesome-ai-video-kit) 和 [Virtual Try-On Video](https://github.com/fsn021920-prog/virtual-try-on-video) 的提示词、参考图和质检思路。这些不是三个自动运行的后端；本仓库使用自己的脚本与已有供应商接口，未新增模型服务。

本仓库代码见 [LICENSE](LICENSE)。外部项目的文件与使用条款由各自仓库管理；Virtual Try-On 的个人非商业限制不因本仓库许可证而改变。
