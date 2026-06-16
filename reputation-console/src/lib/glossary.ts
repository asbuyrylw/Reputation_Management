// One shared plain-English glossary for every jargon term in the app. Surfaced via the
// <Term> tooltip and the /glossary page so a non-technical owner is never left guessing.

export interface GlossaryEntry {
  plain: string; // plain-English definition
  why: string; // why it matters to the owner
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  "reputation score": {
    plain:
      "How favorably AI assistants talk about you, on a 0–100 scale. 50 = neutral or they don't know you; below 50 leans unfavorable, above 50 leans favorable.",
    why: "It's your single headline number — how AI engines portray your business today.",
  },
  "owned content": {
    plain: "How often AI answers cite YOUR own website or pages (vs. other sites).",
    why: "Higher is good — it means AI is repeating your accurate version of the story, which you control.",
  },
  contested: {
    plain:
      "AI answers that bring up a dispute, complaint, scam/ripoff claim, or negative topic about you.",
    why: "These work against your reputation; lower is better.",
  },
  grounded: {
    plain: "The AI answered using a live web search instead of its memory.",
    why: "Grounded answers are current and change when you publish new content; memory-based ones are stickier.",
  },
  "recognition gap": {
    plain:
      "How often AI doesn't correctly know your business — either it has no information, or it confuses you with a different company that shares your name.",
    why: "This is the FASTER problem to fix: publish clear, accurate content and the gap closes.",
  },
  "awareness gap": {
    plain: "AI doesn't know your business well yet — an information void to fill.",
    why: "The faster problem to fix — give the engines accurate content to cite.",
  },
  "negative narrative": {
    plain: "AI knows you but says unfavorable things.",
    why: "The slower problem — needs accurate content to outweigh and rebut the negative.",
  },
  "entity confusion": {
    plain: "AI is mixing you up with a different business that shares your name.",
    why: "A concrete, high-priority error that can attach someone else's reputation to you.",
  },
  schema: {
    plain:
      "Hidden labels in your website's code that spell out your official name, reviews, and FAQs so AI reads them correctly.",
    why: "Without them AI guesses your details and may use wrong or third-party info. '0 of 5' means none exist.",
  },
  "semantic readiness": {
    plain: "How easily AI can read your pages and quote a clear answer about you (0–100).",
    why: "If AI can't pull a clean answer from your site, it answers from forums and reviews you don't control. Healthy sites score 60+.",
  },
  "share of voice": {
    plain:
      "Of every website AI quotes about you, what slice is yours (Owned) vs. neutral vs. critical (Contested).",
    why: "Tells you whether AI is mostly repeating accurate sources or critical ones — the heart of your AI reputation.",
  },
  cites: {
    plain: "How many times AI quoted a given website when answering about you.",
    why: "More cites = more influence that source has over what AI says about you.",
  },
  share: {
    plain: "A single website's slice of all the citations AI made about you.",
    why: "Shows which sources dominate your AI story.",
  },
  classification: {
    plain:
      "The TYPE of source AI cited: your own site (Owned), an independent third party (Neutral), or a complaint/critical site (Contested).",
    why: "You want AI quoting Owned and Neutral sources; Contested ones spread the bad narrative.",
  },
  "missing topics": {
    plain: "Subjects AI expects a business like yours to cover, that your site barely mentions.",
    why: "When you don't cover a topic AI expects, AI fills the gap from outside sources and you lose control of that part of your story.",
  },
  "thin corroboration": {
    plain: "Claims you make that no outside source backs up yet — so AI stays vague about them.",
    why: "AI trusts third-party proof, not self-claims; you need outside sources to confirm them.",
  },
  "work order": {
    plain: "A task — a specific job to improve your reputation that you or the Koob team will do.",
    why: "This is the action unit that ties a problem to a concrete, trackable next step.",
  },
  confidence: {
    plain: "How sure we are of the projected date — it sharpens after each audit.",
    why: "Low just means we'll firm it up after your next audit, not that anything is wrong.",
  },
  "dominance target": {
    plain: "The finish line — the point where AI mostly says accurate, positive things about you (a 0–100 goal).",
    why: "The score you're aiming to reach.",
  },
  relevance: {
    plain: "How sure we are a mention is actually about your business.",
    why: "Lets you dismiss noise and focus on mentions that are really about you.",
  },
  grounding: {
    plain: "Whether the AI looked at the live web to answer, instead of relying on memory.",
    why: "Live-web answers respond to new content you publish; memory answers change more slowly.",
  },
};

export function glossaryLookup(term: string): GlossaryEntry | undefined {
  return GLOSSARY[term.toLowerCase()];
}
