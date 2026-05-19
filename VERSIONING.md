# product-ugc-pipeline Skill Versioning

This Git repo tracks the installed Codex skill itself:

- `SKILL.md`
- `scripts/`
- `references/`
- `agents/`
- versioning notes and small config files

Generated product outputs, images, videos, logs, and API artifacts should not be committed here.

## Commit Rhythm

Create a commit whenever the skill behavior changes meaningfully, for example:

- `skill: improve canonical reference selection`
- `skill: add native veo voiceover prompts`
- `skill: refine image2 product identity lock`
- `skill: add 1688 product-function cognition rules`

## Recommended Flow

1. Edit the skill files.
2. Run a small one-product real-model prompt test when possible.
3. Inspect `git diff`.
4. Commit the skill change before paid image/video generation.
