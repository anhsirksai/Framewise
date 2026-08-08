/**
 * Map raw backend/LLM error text to a short, user-friendly message.
 *
 * The backend surfaces provider errors (Anthropic/OpenAI/TwelveLabs) more or
 * less verbatim in `detail`, which can leak raw log/traceback text into the
 * UI. This helper recognizes the common failure classes and rewrites them.
 */

const CREDIT_PATTERNS = [
  /credit balance/i,
  /insufficient[_ ]quota/i,
  /exceeded your current quota/i,
  /billing/i,
  /payment required/i,
  /\b402\b/,
  /purchase more credits/i,
  /usage limit/i,
];

const RATE_LIMIT_PATTERNS = [/rate[_ ]limit/i, /\b429\b/, /too many requests/i, /overloaded/i];

const AUTH_PATTERNS = [/api key/i, /authentication/i, /\b401\b/, /unauthorized/i, /invalid[_ ]key/i];

/** True when the raw text looks like an out-of-credits / quota-exhausted error. */
export function isOutOfCredits(raw: string): boolean {
  return CREDIT_PATTERNS.some((p) => p.test(raw));
}

/** Rewrite a raw error string into something safe to show users. */
export function friendlyError(raw: string | null | undefined): string {
  const text = (raw ?? "").trim();

  if (isOutOfCredits(text)) {
    return "Sorry, out of credits! The AI provider account has run out of usage credits, so answers can't be generated right now. Please top up the account (or switch LLM_PROVIDER) and try again.";
  }
  if (RATE_LIMIT_PATTERNS.some((p) => p.test(text))) {
    return "We're being rate-limited by the AI provider. Give it a few seconds and try again.";
  }
  if (AUTH_PATTERNS.some((p) => p.test(text))) {
    return "The AI provider rejected our API key. Check the configured key on the backend and try again.";
  }
  if (!text) {
    return "Something went wrong. Please try again.";
  }
  // Raw tracebacks / long provider payloads: don't dump them on screen.
  if (text.length > 220 || /Traceback|Exception|\bat .+\.py\b|stack trace/i.test(text)) {
    return "Something went wrong on our side while answering. Please try again — if it keeps happening, check the backend logs.";
  }
  return text;
}
