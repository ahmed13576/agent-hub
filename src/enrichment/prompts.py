"""
Agent Hub - Enrichment Prompt Templates & Versioning

Defines the production prompts used to instruct the LLM for AI strategy analysis.
Includes prompt versioning via SHA256 hash for regression tracking.

Prompt changes are tracked: if the prompt text changes, the version hash changes,
enabling regression evals to detect quality drift after prompt edits.
"""

import hashlib

from src.enrichment.schema import VALID_CATEGORIES, VALID_TAGS


# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert AI strategy analyst specializing in agentic AI coding tools, \
techniques, and workflows. Your job is to evaluate items discovered from GitHub \
repositories, Reddit discussions, and technical blog posts about AI-powered \
coding assistants (Claude Code, Cursor, Windsurf, Antigravity, GitHub Copilot, etc.).

You assess each item across these dimensions:
1. **Relevance**: How directly does this relate to agentic AI coding strategies, \
token optimization, prompt engineering, multi-agent workflows, or developer tooling?
2. **Effectiveness**: Based on community signals (stars, upvotes, discussion depth), \
documentation quality, and technical merit — how impactful is this strategy or tool?
3. **Maturity**: Is this battle-tested (widely adopted, proven track record), \
new/upcoming (recently published, gaining traction), or experimental (prototype stage, \
research-oriented, limited adoption)?

You MUST respond with valid JSON only. No markdown, no explanations outside the JSON object.\
"""

# ── User Prompt Template ─────────────────────────────────────────────────────

USER_PROMPT_TEMPLATE = """\
Analyze the following item and produce a JSON evaluation.

**Item Details:**
- Title: {title}
- Source: {source}
- Author: {author}
- Description: {description}
- Original Tags: {tags}
- Content (truncated):
{raw_content_truncated}

**Instructions:**
Return a JSON object with EXACTLY these fields:

{{
  "summary": "<2-3 sentence synopsis of what this item is about and why it matters for agentic AI coding>",
  "category": "<one of: {valid_categories}>",
  "effectiveness_score": <float 0.0-1.0, where 0=not useful, 1=extremely impactful>,
  "relevance_score": <float 0.0-1.0, where 0=completely unrelated to agentic AI, 1=directly about agentic AI coding>,
  "enriched_tags": [<list of applicable tags from: {valid_tags}>]
}}

**Scoring Guidelines:**
- relevance_score < 0.2: Not about AI coding agents at all (e.g., recipes, games, unrelated software)
- relevance_score 0.2-0.5: Tangentially related (general dev tools, generic AI content)
- relevance_score 0.5-0.8: Related to AI coding but not specifically agentic workflows
- relevance_score > 0.8: Directly about agentic AI coding strategies, tools, or optimization

- effectiveness_score < 0.3: Minimal practical value (incomplete, no evidence of use)
- effectiveness_score 0.3-0.6: Moderate value (some utility, limited adoption)
- effectiveness_score 0.6-0.8: High value (useful, evidence of adoption)
- effectiveness_score > 0.8: Exceptional value (widely adopted, proven impact)

- category "battle-tested": Established tools/techniques with significant adoption (1000+ stars, \
widely referenced, months/years of use)
- category "new-upcoming": Recently published (weeks/months), gaining traction, showing promise
- category "experimental": Prototype stage, research papers, alpha releases, limited real-world use

**Tags** — select ALL that apply from this list ONLY:
{valid_tags_list}

Respond with the JSON object only.\
"""


def build_prompt(item: dict, max_content_chars: int = 4000) -> str:
    """
    Build a user prompt from a scraped item dict.

    Truncates raw_content to max_content_chars to fit within model context limits.

    Args:
        item: Scraped item dict with the 10-field unified schema.
        max_content_chars: Maximum characters of raw_content to include.

    Returns:
        Formatted user prompt string ready for LLM submission.
    """
    raw_content = item.get("raw_content", "")
    if len(raw_content) > max_content_chars:
        raw_content = raw_content[:max_content_chars] + "\n... [truncated]"

    return USER_PROMPT_TEMPLATE.format(
        title=item.get("title", "Unknown"),
        source=item.get("source", "Unknown"),
        author=item.get("author", "Unknown"),
        description=item.get("description", "No description available"),
        tags=", ".join(item.get("tags", [])) or "None",
        raw_content_truncated=raw_content or "No content available",
        valid_categories=", ".join(sorted(VALID_CATEGORIES)),
        valid_tags=", ".join(sorted(VALID_TAGS)),
        valid_tags_list="\n".join(f"  - {t}" for t in sorted(VALID_TAGS)),
    )


def get_prompt_version() -> str:
    """
    Return a version hash of the current prompt templates.

    The version is the first 12 hex characters of the SHA256 hash of the
    combined system + user prompt text. If either prompt changes, the
    version changes — enabling regression tracking.

    Returns:
        12-character hex string (e.g., "a3f2b1c9d4e5").
    """
    combined = SYSTEM_PROMPT + USER_PROMPT_TEMPLATE
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:12]
