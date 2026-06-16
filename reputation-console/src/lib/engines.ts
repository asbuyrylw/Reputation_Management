// One place to humanize the engine keys the API returns. Raw keys like "openai_search"
// look like a bug to a non-technical owner; always show the product name.

export const ENGINE_LABELS: Record<string, string> = {
  openai_search: "ChatGPT",
  anthropic: "Claude",
  perplexity: "Perplexity",
  gemini: "Gemini",
};

export function engineLabel(key: string): string {
  return ENGINE_LABELS[key] ?? key;
}

// A one-word plain state for an engine's challenge profile (used in the per-engine strip).
export function engineState(profile: string | undefined): string {
  switch (profile) {
    case "awareness_gap":
      return "Doesn't know you";
    case "negative_narrative":
      return "Unfavorable";
    case "mixed":
      return "Mixed";
    case "established_positive":
      return "Favorable";
    default:
      return "—";
  }
}
