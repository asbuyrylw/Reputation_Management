import type { WorkOrder } from "@/lib/types";

// Producible-content capabilities — the single FE definition of "what counts as content to produce".
// MUST mirror strategy_generator.CONTENT_CAPABILITIES (backend source of truth). P1-6 replaces this
// with a value fetched from the backend (via useContentCapabilities) so FE and BE can never drift again;
// until then this is the ONE copy the hub, Briefs, calendar, and work-orders pages all import.
export const CONTENT_CAPS = new Set<string>([
  "content_writing", "video_creation", "explainer_video", "deep_content",
  "podcast_creation", "slide_deck", "research_brief", "local_content_creation",
]);

// The pieces we draft IN-APP (content_writing + all rich-media route through generate_for_wo →
// rich_media_generator). local_content_creation is a multi-piece PROGRAM, produced separately.
export const DRAFTABLE = new Set<string>([
  "content_writing", "video_creation", "explainer_video", "deep_content",
  "podcast_creation", "slide_deck", "research_brief",
]);

export const CAP_LABEL: Record<string, string> = {
  content_writing: "Article / web page",
  video_creation: "Video",
  explainer_video: "Explainer video",
  deep_content: "Blog series + long-form",
  podcast_creation: "Podcast",
  slide_deck: "Slide deck",
  research_brief: "Research brief",
  local_content_creation: "Local / geo page",
  review_generation: "Reviews",
  schema_markup: "Website code (schema)",
  technical_seo: "Website fix",
};

// The single definition of "what content is left to produce": non-superseded, non-skipped content
// work orders, highest predicted AI impact first. BOTH the Content hub and the Briefs page call this,
// so the "produce next" list / KPI tile and the canonical "To Produce" set can never disagree.
export function contentToProduce(workOrders: WorkOrder[] | undefined): WorkOrder[] {
  return (workOrders ?? [])
    .filter((w) => CONTENT_CAPS.has(w.capability ?? "") && !w.superseded && w.status !== "skipped")
    .sort((a, b) => (b.predicted_ai_points ?? -1) - (a.predicted_ai_points ?? -1));
}
