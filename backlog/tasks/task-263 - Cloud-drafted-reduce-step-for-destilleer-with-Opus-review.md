---
id: TASK-263
title: Cloud-drafted reduce step for /destilleer with Opus review
status: In Progress
assignee: []
created_date: '2026-11-20T15:48:00Z'
updated_date: '2026-11-20T15:48:00Z'
labels:
  - destilleer
  - llm
dependencies:
  - TASK-262
ordinal: 196600
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After distill-map, thousands of candidates must be reduced into the wiki. Add scripts/distill-reduce.py: anchor each candidate to its nearest wiki article with local embeddings, group them into jobs (update an existing article, or a new-article cluster), and let one explicitly chosen OpenRouter model (default z-ai/glm-5.3-flash, reasoning low, data_collection deny) draft per job: skip, an addition to the article, or a new article. Drafts land in <vault>/.claude/distill-reduce/, never in the wiki. A local gate checks that every drafted claim cites an evidence quote that occurs verbatim in the source transcript. An independent Claude Opus reviewer subagent judges each draft before the session writes it into 02-wiki and kb-lint must be clean. Same cloud toggle and per-run consent rule as distill-map; the consent explicitly covers sending existing wiki articles.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Anchoring and grouping run locally (Ollama embeddings) and need no toggle
- [ ] #2 Cloud drafting is gated by distill_cloud_map and a fixed job snapshot file; existing wiki article text is sent only with that consent
- [ ] #3 Each draft records decision, reason, additions with source stem and evidence quote, usage and cost; failures are logged and retried like distill-map
- [ ] #4 Local grounding gate marks every addition whose evidence quote is not found verbatim in its stripped source transcript; ungrounded additions are never applied
- [ ] #5 Every article written or updated from a draft was reviewed by a Claude Opus subagent first, and kb-lint is clean
- [ ] #6 Pilot on one cluster shown to the user before scaling
- [ ] #7 pytest suite for the new script green; regression tests shown red first
<!-- AC:END -->
