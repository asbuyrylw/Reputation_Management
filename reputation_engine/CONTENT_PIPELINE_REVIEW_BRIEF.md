# Scoped review brief — content pipeline (for `/code-review ultra`)

This branch (`feature/premium-ui-redesign`) closed every gap from the pipeline audit + grounded the
strategy in research. Run `/code-review ultra` on the branch and have it **trace the whole loop end to
end**, confirming each stage's data actually flows into the next and everything works together to improve
AEO / SEO / GEO + keyword rankings.

## Trace this path — does each stage feed the next?

1. **Gap analysis** (`ai_state_audit.build_gap_model` → `gap_models`) — the weak AI queries, missing owned
   content, competitor-defense, local gaps.
2. **Strategy** (`content_strategist.plan` → `strategy_generator.build_work_orders` → `tracking.sync_plan`
   → `strategy_view`). Verify: campaign counts/topics come from the gap model + keyword demand + clusters
   + measured lift; the strategist prompt now carries the **cited research** (`content_research.py`) and
   must justify amount/type/structure against it; `atomization.video_script` is honored; baseline
   rich-media is bound to a real campaign (no "Other" bucket); local emits a **pillar+spoke program**.
3. **Content needed to fill each gap** — every work order carries `gap_specifics` (source_query,
   campaign_id, content_type, role, publish_week). Verify identity flows unbroken via `_task_key`.
4. **Why each piece + what it does published** — `piece_brief` (`content_generator.py:474`): keywords
   (scoped to the piece query), a **research-cited word-count** (`word_count_basis`), structure,
   `closes_gap`, and grounding coverage. Verify the spec matches what's generated.
5. **How it's generated + the exact prompts** — `generate_for_wo`: `_gen_system` + `_gen_prompt`.
   Verify the prompt injects, in order: the client's **source material** (`grounding.client_material` from
   `source_material` + `grounding_retrieval.facts_block`), the **authoritative sources** (finance pack +
   the new universal pack), and the **cited GEO/AEO research** (`grounding.research`), and that
   `_asset_type_for` now selects the template from `gap_specifics.content_type`.
6. **What research/guide drove each decision** — `content_research.py`: confirm each length/type/structure/
   tactic decision is traceable to a cited entry (Google Search Central, the Princeton GEO paper
   arXiv:2311.09735, Ahrefs/HubSpot/Semrush). Flag any decision still tracing to an **uncited constant**.
7. **Scoring** (`content_quality.py`) — geo/aeo/on_page/serp/citation grades. Verify the score→plan loop:
   `content_strategist._type_performance` feeds each content_type's GEO grade back into the strategist so
   it biases the mix toward what's citable for this tenant; podcasts are now scored.
8. **Measurement** (`/gap-completion`) — verify cluster/local/recommended batches now earn credit.

## Specific things to verify (the changes)
- **Alignment**: hub "produce next" == Briefs "To Produce" (shared `contentToProduce`, `src/lib/content.ts`);
  the capability set is one shared constant + `/content-capabilities` endpoint (no more 4-way drift).
- **Thin-source banner** names each thin piece + what to add (`grounding_coverage.thin_topics` +
  `strategy_view` builds `ungrounded_pieces` for thin).
- **Recommended content** produces a pillar+spokes program (`content_batch.generate_cluster` via the
  targeted `content-clusters/generate` job), not one article.
- **Social** is a first-class To-Produce group + a "Create social posts" atomize action.

## What to challenge (author's self-flags)
- Word-count targets are **research-informed but moderated** (not the max), to avoid padding/AI-slop —
  confirm that's the right call vs. the study numbers (blogs 2,100-2,400; pillars ~4,000).
- Baseline rich-media is bound to the **single top campaign** — is spreading across the top-N better?
- "Recommended → program" generates immediately (cost) — should it instead materialize plan WOs first?
- A few research claims are lower-confidence (tier `editorial`, flagged in `content_research.py`).

## After the review
When satisfied, **re-plan business 1** (run the plan job / "re-plan") so the live plan regenerates against
the new code — that's what surfaces the local programs, the campaign-bound rich media, and the
research-grounded briefs, and retires the last stale plan artifacts.
