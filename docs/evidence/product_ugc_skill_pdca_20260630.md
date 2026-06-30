# Product UGC Pipeline Skill — PDCA 实践总结

## Plan

搭建一套 AI 驱动的电商商品 UGC 短视频生产 Skill，实现：从商品 URL 自动抓取商品页与图片素材，通过视觉模型理解产品外观与用法，合成产品认知与核心卖点，生成 10 个差异化 UGC 口播分镜与首尾帧 prompt，调用 GPT-Image-2 生成首尾帧，再通过 LK888 VEO 3.1 生成 8 秒竖屏带货视频。全程强制产品外观保真、幻觉防御、卖点梯子和口播长度约束。

## Do

用 Python 构建了 8 个生产脚本（scrape → analyze → brief → prompt → image → video → batch），接入 LaoZhang GPT-Image-2 做首尾帧生成，LK888 VEO 3.1（veo3.1）做视频生成，GPT-4o / MiniMax-M3 做视觉分析，GPT-5.2 或 Codex 直写做 prompt 生成。核心实现了：benefit_ladder 卖点梯子（core_selling_claim → buyer_problem → product_intervention → buyer_result → proof_moment），6 类通用幻觉防御自动注入（phantom_parts / shape_preservation / material_texture_lock / action_bounds / context_contamination / scale_anchor），8 秒口播约束（14-18 词，硬上限 20 词，问题→介入→结果三段式），首尾帧连续性（尾帧基于首帧 + 商品参考图生成，同场景同人物），Fail-Fast 生产契约（认知链路任何一步失败不跑付费视频），canonical 文件管理（videos/variant-XX.mp4 递增编号 + ugc_prompts.json 统一追加）。

## Check

VEO 视频中产品外观偶有漂移——花朵形洗碗刷变成普通圆刷、宠物项圈卡扣变金属扣、戒指形状变形。8 秒口播经常在结尾被截断，台词没说完。首尾帧有时场景/人物/灯光完全不同，导致视频中途画面突变。6 月中旬 omni-flash 试验期间视频质量不稳定，且 VEO 失败时脚本静默切换到 Seedance/即梦等非 VEO 模型，产出质量不可控。部分 prompt 只描述产品部件（buckle、slider、soft fabric）而不讲买家为什么买，视频好看但没抓住核心卖点。多轮追加视频时新建目录满天飞，prompt 文件和视频散落各处难以追溯。

## Act

在 `build_product_brief.py` 中为每个产品自动生成 6 类幻觉防御字段，`generate_ugc_prompts.py` 自动注入所有 prompt。将 8 秒口播硬约束写入 `VOICEOVER_TARGET_WORDS=14-18`、`VOICEOVER_HARD_MAX_WORDS=20`，并按 benefit_ladder 顺序（buyer problem → product intervention → buyer result）禁止无卖点台词如"here is how it works"。尾帧生成改为基于首帧 + 商品参考图，`SKILL.md` 中强制要求同一房间/人物/光线/机位。在 `SKILL.md` 和脚本中硬编码 VEO-first 规则，禁止静默切换到 Seedance/Kling/Omni，失败时报告具体状态和错误而非静默降级。新增 `build_benefit_ladder()` 函数，所有 variant 在写口播和分镜之前必须先确定 core_selling_claim 和 buyer_problem。统一输出为 canonical 递增编号 + `runs/` 批次历史，支持先产几条后续继续追加。
## 流程总览

```mermaid
flowchart TD
    A["📦 商品 URL 列表"] --> B["scrape_products.py<br/>抓取商品页与图片"]
    B --> C["product_manifest.json<br/>商品资料 + 卖点"]
    B --> D["images/<br/>商品原始图"]

    C --> E["analyze_materials.py<br/>视觉模型分析商品图"]
    D --> E
    E --> F["image_analysis.json<br/>每张图的外观 / 用法 / 风险"]

    C --> G["build_product_brief.py<br/>商品认知合成"]
    F --> G
    G --> H["product_brief.json<br/>身份 · 用法 · 卖点 · 误用风险 · 幻觉防御"]

    H --> I["generate_ugc_prompts.py<br/>卖点梯子 + UGC 分镜"]
    F --> I
    I --> J["ugc_prompts.json<br/>口播 · 分镜 · 图片 prompt · VEO prompt"]

    J --> K["generate_images.py<br/>GPT-Image-2 生成首尾帧"]
    D --> K
    K --> L["generated_images/<br/>variant-XX-start/end.png"]

    J --> M["generate_videos_lk888.py<br/>LK888 VEO 3.1 生成视频"]
    L --> M
    M --> N["videos/variant-XX.mp4<br/>8s 竖屏带货视频"]
    M --> O["video_generation_results.json<br/>状态 / 成本 / 模型 / 输出路径"]
```

## 认知建模五层

```mermaid
flowchart LR
    subgraph 认知建模
        L1["Layer 1<br/>Product Identity<br/>外观 / 材质 / 机构 / SKU<br/>—— 锁定不变形"]
        L2["Layer 2<br/>Commercial Promise<br/>标题 / 卖点<br/>—— 买家为什么买"]
        L3["Layer 3<br/>Product Function<br/>用法 / 分步操作<br/>—— 产品怎么用"]
        L4["Layer 4<br/>Buyer-Visible Effect<br/>使用后的改善结果<br/>—— 效果可见"]
        L5["Layer 5<br/>Scene Imagination<br/>真实生活场景<br/>—— 场景不局限于原图"]
    end

    L1 --> L2 --> L3 --> L4 --> L5
```

## 单条视频生成链路

```mermaid
flowchart TD
    S["benefit_ladder<br/>核心卖点 · 买家痛点 · 产品介入 · 买家结果 · 证明镜头"]
    S --> V["voiceover_script_8s<br/>14-18 词 / 8s / 三段式"]
    S --> B["storyboard_8s<br/>time · visual · spoken · overlay"]
    B --> SF["start_frame_prompt<br/>描绘第一帧：问题 / 场景"]
    B --> EF["end_frame_prompt<br/>描绘最后一帧：结果 / 证明"]
    SF --> G["GPT-Image-2 → start.png"]
    EF --> G2["GPT-Image-2 → end.png<br/>基于首帧 + 商品参考图"]
    V --> P["VEO Prompt<br/>正样本注入 + 负样本排除 + 幻觉防御"]
    B --> P
    G --> P
    G2 --> P
    P --> VEO["LK888 VEO 3.1<br/>variant-XX.mp4"]
```

## 幻觉防御六层

```mermaid
flowchart LR
    subgraph 自动注入
        D1["phantom_parts<br/>防凭空线缆/按钮/盖子"]
        D2["shape_preservation<br/>防外形漂移"]
        D3["material_texture_lock<br/>防材质/颜色变化"]
        D4["action_bounds<br/>防不存在的功能"]
        D5["context_contamination<br/>防错误配件/场景"]
        D6["scale_anchor<br/>防尺寸错乱"]
    end

    PB["product_brief.json"] --> D1 & D2 & D3 & D4 & D5 & D6
    D1 & D2 & D3 & D4 & D5 & D6 --> IP["所有 image_prompt"]
    D1 & D2 & D3 & D4 & D5 & D6 --> VP["所有 video_prompt"]
```
