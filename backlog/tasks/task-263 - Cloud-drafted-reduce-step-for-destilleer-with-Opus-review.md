---
id: TASK-263
title: Cloud-drafted reduce step for /destilleer with Opus review
status: In Progress
assignee: []
created_date: '2026-11-20T15:48:00Z'
updated_date: '2026-11-20T17:30:00Z'
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
- [x] #1 Anchoring and grouping run locally (Ollama embeddings) and need no toggle
- [x] #2 Cloud drafting is gated by distill_cloud_map and a fixed job snapshot file; existing wiki article text is sent only with that consent
- [x] #3 Each draft records decision, reason, additions with source stem and evidence quote, usage and cost; failures are logged and retried like distill-map
- [x] #4 Local grounding gate marks every addition whose evidence quote is not found verbatim in its stripped source transcript; ungrounded additions are never applied
- [x] #5 Every article written or updated from a draft was reviewed by a Claude Opus subagent first, and kb-lint is clean
- [x] #6 Pilot on one cluster shown to the user before scaling
- [x] #7 pytest suite for the new script green; regression tests shown red first
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Run 2026-11-20 (owner vault): plan = 2722 candidates -> 801 jobs (241 update, 560 new clusters, 469 singletons). Pilot 2 jobs: GLM drafted 6 additions, all passed the grounding gate, Opus accepted 0 unchanged (4 revised, 2 rejected: stale estimates, a wrong mechanism, off-topic). User chose top-30 update jobs; tail marked processed without wiki writes. Top-30: GLM draft $0.06; 3 Opus reviewers (~660k Claude tokens) -> 117 verdicts: 28 accept, 73 revise, 16 reject; 2 accepted items blocked by the grounding gate on purpose. Applied: 95 additions in 22 articles + 4 new articles; kb-lint clean 383->389, findings 27->25; 0 original lines lost (line-multiset check against the pre-apply backup in .claude/distill-reduce/_wiki-backup-2026-11-20). Pending 364 -> 2 (two unmapped sessions from today). Open: reviewer-flagged stale passages in 9 existing articles (issues in _verdicts_b*.json); the 2 pilot articles wait for the PR #186 merge. Bugs found and fixed during the run: CRLF rewrite of LF articles, provenance blank lines, ### subsections, model-supplied slug/title path traversal (security review).
<!-- SECTION:NOTES:END -->
