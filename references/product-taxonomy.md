# Product taxonomy for UGC production

The pipeline separates commerce meaning from production behavior. A store category answers what the item is; a production family and its traits answer which views, contacts, states and failure modes the image/video workflow must control.

## Four-layer classification

1. `catalog_taxonomy`: a broad vertical, a specific semantic path and the product's main function.
2. `visual_family`: one reusable identity-sheet/QC family such as apparel, electronics, furniture, bags-containers, sports-outdoor or general-merchandise.
3. `physical_traits`: cross-category properties such as inflatable, suspended-load, articulated, cabled, transparent or multi-part.
4. `interaction_modes`: actions such as wear, body-support, contain-store, mount-install, fold-deploy or inflate-deflate.

The same product can have one catalog path, one primary visual family and several traits/interactions. A camping hammock is not a dedicated hard-coded family: it can be `sporting-goods > outdoor recreation > camping hammocks`, use the `sports-outdoor` production family, and add `flexible-textile`, `suspended-load`, `multi-part`, `suspend-anchor` and `body-support`. An air bed can use the same broad family with `inflatable`, `deformable`, `inflate-deflate` and `body-support`.

## Classification route

Use the full manifest and all image-analysis records to build `product_brief.json`. The brief model returns both taxonomy layers with evidence. Run `classify_product_category.py` after the brief; it writes the normalized profile to `category.json`. Title keywords are only a compatibility fallback when no brief exists, and that result remains marked for review. Unknown families fall back to `general-merchandise` and remain reviewable instead of being forced into an unrelated checklist.

The production profile also feeds the risk router. Traits such as `inflatable` and interactions such as `mount-install`, `suspend-anchor`, `fold-deploy` or `inflate-deflate` can raise the state-change risk even when the selling-point prose does not use the expected keyword.

## Research basis

- [Shopify Standard Product Taxonomy](https://github.com/Shopify/product-taxonomy) provides an open, versioned hierarchy spanning more than 25 commerce verticals, with category-specific attributes, values, localization and mappings. It supports a semantic catalog path but is too fine-grained to become one video QC template per leaf.
- [GS1 Global Product Classification](https://www.gs1.org/standards/gpc/how-gpc-works) uses Segment, Family, Class and Brick, then adds brick attributes. Its brick rule groups products by common purpose, form, material and use; this directly motivates the separate production family and trait layers.
- [Google product categories](https://support.google.com/merchants/answer/6324436) favor the most specific category based on the main function, combine automatic assignment with an explicit override, and retain a merchant-defined product type when no predefined category fits.
- [MEP-3M](https://github.com/ChenDelong1999/MEP-3M) represents more than three million Chinese ecommerce products with image-text pairs and hierarchical labels. It supports using both title/text and images rather than a title-only keyword table.
- [Amazon Berkeley Objects](https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/index.html) keeps product type, hierarchy, material, dimensions, weight, shape and multiple views as separate metadata. This supports keeping physical evidence outside the category label.
- [SCHEMA](https://github.com/nudge/schema) maps complete taxonomy paths rather than comparing isolated leaf names. The pipeline likewise validates a path and a production profile instead of relying on one flat label.
- [Open-world product classification](https://par.nsf.gov/biblio/10120466-open-world-learning-application-product-classification) treats rejection of unseen products and incremental expansion as core requirements. The pipeline therefore preserves manual review and a general family rather than returning false certainty.

No external training data, model weights or heavy classification runtime is included. These projects inform the schema and decision rules; the existing product-brief vision/language pass performs the actual evidence-grounded classification.
