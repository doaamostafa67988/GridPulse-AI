export function riskLevel(score: number): "low" | "mid" | "high" {
  if (score >= 60) return "high";
  if (score >= 40) return "mid";
  return "low";
}

export function riskColor(score: number): string {
  const level = riskLevel(score);
  if (level === "high") return "#dc2626";
  if (level === "mid") return "#f59e0b";
  return "#16a34a";
}

export function riskBg(score: number): string {
  const level = riskLevel(score);
  if (level === "high") return "bg-red-50 text-red-700 border-red-200";
  if (level === "mid") return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-green-50 text-green-700 border-green-200";
}

export function formatCurrency(n: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

export function actionLabel(action: string): string {
  return action
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

/**
 * The LLM explanation (backend/llm_explain.py) comes back as one long
 * string - the model writes 2-5 sentences with no line breaks between
 * them, and the only literal "\n" in the whole text is the one the
 * template/fallback path inserts right before its bracketed
 * "[reason...]" note. Rendering that raw with CSS white-space: pre-wrap
 * just wraps the single run of text at the container edge - it never
 * produces real paragraph breaks, because there aren't any newlines to
 * break on.
 *
 * This splits the prose into sentences and regroups them into short
 * paragraphs, and always breaks out a trailing "[...]" guardrail/fallback
 * note as its own paragraph so it's visually distinct from the actual
 * explanation. sentencesPerParagraph=2 keeps paragraphs short enough to
 * read as separate thoughts without over-fragmenting a 3-sentence answer
 * into three one-line paragraphs.
 */
export function splitIntoParagraphs(text: string, sentencesPerParagraph: number = 2): string[] {
  if (!text) return [];

  // Defense-in-depth: backend/llm_explain.py's guardrail (validate_explanation)
  // now rejects markdown and retries, so this should be rare - but strip any
  // leftover **bold**/*italic*/# header/- bullet markers rather than showing
  // literal asterisks, in case an older cached response or a stubborn model
  // slips through.
  const plain = text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/(?<!\*)\*(?!\*)(.+?)\*(?!\*)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^[-*]\s+/gm, "");

  // Pull off a trailing bracketed note (the template/fallback's
  // "[reason - showing evidence-based summary instead.]" line) so it
  // never gets merged into the sentence-grouping below.
  const bracketMatch = plain.match(/\s*(\[[^\]]*\])\s*$/);
  const bracketNote = bracketMatch ? bracketMatch[1] : null;
  const body = bracketMatch ? plain.slice(0, bracketMatch.index).trim() : plain.trim();

  // Split on sentence-ending punctuation followed by whitespace and a
  // capital letter/quote/digit - keeps "e.g." or "$50,000." from
  // splitting mid-figure while still catching normal sentence boundaries,
  // and also splits on any existing newlines the source text already has.
  const sentences = body
    .split(/\n+|(?<=[.!?])\s+(?=[A-Z0-9"'])/)
    .map((s) => s.trim())
    .filter(Boolean);

  const paragraphs: string[] = [];
  for (let i = 0; i < sentences.length; i += sentencesPerParagraph) {
    paragraphs.push(sentences.slice(i, i + sentencesPerParagraph).join(" "));
  }
  if (bracketNote) paragraphs.push(bracketNote);
  return paragraphs.length ? paragraphs : [plain.trim()];
}
