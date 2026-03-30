from crewai import Task
from config import STRICT_VERBATIM_MODE


def create_tasks(research_agent, writer_agent, validator_agent, topic, search_context, quotes_only=""):

    # Fix 7 — strict block only defined and injected when enabled
    # Reduced from 7 lines to 3 lines
    if STRICT_VERBATIM_MODE:
        strict_block = """
STRICT VERBATIM MODE: Use exact SOURCE_QUOTE text. No shortening. No paraphrasing.
Omit claim entirely if exact reuse is not possible.
"""
    else:
        strict_block = ""

    # ===============================
    # RESEARCH TASK
    # ===============================

    research_task = Task(
        description=f"""
You are a Grounded Research Analyst.

You are given the following SEARCH RESULTS:

{search_context}

Collect structured facts about: {topic}

You MUST collect facts across ALL of these categories:
1. General facts (origin, creator, year, version, adoption stats, named components)
2. Key features and capabilities
3. Real-world use cases and applications
4. LIMITATIONS, DRAWBACKS, CRITICISMS, or WEAKNESSES

STRICT EXTRACTION RULES — READ CAREFULLY:

RULE 1 — SOURCE_QUOTE UNIQUENESS (CRITICAL):
Each SOURCE_QUOTE must be unique across ALL facts.
NEVER use the same SOURCE_QUOTE for two different facts.
Using the same quote twice = hallucination padding = REJECTED.

RULE 2 — LIMITATIONS CAP:
Extract a MAXIMUM of 4 limitation facts total.
Each limitation must have a completely different SOURCE_QUOTE.
If you cannot find 4 distinct limitation quotes, extract fewer.

RULE 3 — NO PADDING:
If sources are thin on a category, extract fewer facts.
Never invent, infer, or generalize to fill gaps.

RULE 4 — NO TRAINING KNOWLEDGE:
Only include facts with DIRECT TEXTUAL SUPPORT in the search results above.
Do NOT use any knowledge from your training data.
Do NOT cite academic papers, author names, or journal references.
Do NOT hallucinate sources — only reference [SOURCE N] numbers from above.

RULE 5 — DEFINITION CAP (CRITICAL):
In the General category, extract MAXIMUM 1 definition sentence.
After extracting 1 definition, STOP extracting definitions.
The remaining General facts MUST be about:
- Who created it and when (origin story)
- Specific version numbers or release dates
- Named technical components or architecture
- Adoption statistics, usage numbers, named companies using it

RULE 6 — SPECIFICITY OVER GENERALITY:
Always prefer facts with specific numbers, named companies, benchmarks, or technical mechanisms.
Vague sentences like "used by many companies" or "provides many benefits" = REJECTED.

RULE 7 — USE CASES MUST BE SPECIFIC:
Each use case must name a specific domain, industry, company, or product.
REJECTED: "Used by companies for data processing"
ACCEPTED: "Used by Netflix for real-time event streaming at scale"

For Limitations:
- SOURCE_QUOTE MUST be negative in meaning.
- Positive quotes are NOT valid limitation quotes.
- ONLY write "NO LIMITATIONS FOUND IN SOURCES" if zero limitation facts found.

OUTPUT FORMAT — Fix 3 — compact 1-line per fact:
Output each fact on a single line in this exact format:
[CATEGORY|SOURCE_NUM] "SOURCE_QUOTE"

Examples:
[General|2] "Redis was created by Salvatore Sanfilippo in 2009."
[Features|3] "Redis can perform 100,000 read operations per second."
[UseCases|9] "Twitter uses Redis for real-time timeline caching."
[Limitations|7] "Redis is limited by available memory since it stores all data in RAM."

IMPORTANT:
- CATEGORY must be one of: General / Features / UseCases / Limitations
- SOURCE_NUM must match a [SOURCE N] number from the search results above
- SOURCE_QUOTE must be verbatim from the search results — no paraphrasing
- One line per fact — no multi-line format
""",
        # Fix 2 — expected_output one line only
        expected_output="Compact fact list in [CATEGORY|SOURCE_NUM] format per rules above. All facts from provided sources only.",
        agent=research_agent,
    )

    # ===============================
    # WRITER TASK
    # ===============================

    writer_task = Task(
        description=f"""
You are a Citation-Grounded Technical Writer.
{strict_block}
IMPORTANT: Do NOT write any preamble, introduction, or filler phrases.
Do NOT write things like "I now can give a great answer" or "Here is the document".
Begin your response IMMEDIATELY with the title line: # {topic.upper()}
Your entire response must be the Markdown document and nothing else.

The researcher output is in compact format: [CATEGORY|SOURCE_NUM] "SOURCE_QUOTE"
Use the SOURCE_QUOTE from each fact as the [CITE: "..."] tag for that sentence.

STRICT RULES:
1. Every sentence MUST be traceable to a SOURCE_QUOTE from the research output.
2. After EACH sentence add: [CITE: "exact SOURCE_QUOTE"]
3. Write ONLY supported facts. If a claim has no SOURCE_QUOTE, omit it.
4. No inference. No summarization. No expansion beyond what sources say.
5. Output pure Markdown only.
6. In the Overview section, each sentence MUST be on its own line with its own [CITE: "..."] tag.

CITATION RULES:
- Do NOT invent, generate, or reference academic papers, author names, or journals.
- Do NOT add a References or Bibliography section.
- If no source supports a claim, OMIT the claim entirely.

OVERVIEW WRITING RULES:
- Write exactly 2-4 sentences in Overview.
- Sentence 1: the single best definition from CATEGORY=General facts.
- Sentence 2-4: origin, creator, adoption stats, or named technical detail.
- Do NOT repeat similar definition sentences — each sentence must add new information.

REQUIRED STRUCTURE — output exactly these sections, no more, no less:

# {topic.upper()}

## Overview
(2-4 sentences, EACH on its own line, each ending with its own [CITE: "..."])

## Key Concepts
- Bullet point [CITE: "..."]

## Real-World Use Cases
- Bullet point [CITE: "..."]

## Limitations
- Bullet point [CITE: "..."]

IMPORTANT FOR LIMITATIONS:
- Use CATEGORY=Limitations facts from the research output only.
- Include a MAXIMUM of 4 limitation bullets.
- ONLY write "Insufficient source data for this section." if the researcher
  explicitly stated "NO LIMITATIONS FOUND IN SOURCES".
- Do NOT use a positive/feature quote as a limitation bullet.
- Do NOT repeat the same citation quote across multiple limitation bullets.
""",
        # Fix 2 — expected_output one line only
        expected_output=f"Markdown document starting with # {topic.upper()} containing exactly 4 sections per rules above.",
        agent=writer_agent,
    )

    # ===============================
    # VALIDATOR TASK
    # ===============================
    # quotes_only replaces full search_context — major token saving (Fix 1)
    # Compact 2-line audit format per claim — token saving (Fix 5)
    # Guard 3 in main.py handles verdict override as safety net

    validator_task = Task(
        description=f"""
You are a Fact-Check Auditor. Audit the document produced by the writer.

You have access to VERIFIED SOURCE QUOTES extracted from the original search results:

--- VERIFIED SOURCE QUOTES START ---
{quotes_only}
--- VERIFIED SOURCE QUOTES END ---

STEP 1 — STRUCTURAL CHECK:
Verify the document contains ALL of these sections:
- # Title
- ## Overview
- ## Key Concepts
- ## Real-World Use Cases
- ## Limitations
If any section is missing → Verdict: FAIL immediately.

STEP 2 — HALLUCINATION CHECK:
Scan for RED FLAGS:
- Academic paper citations (e.g. "Jacobs et al.", "Smith et al.")
- Author names as sources (e.g. "According to Bengio...")
- Journal references (IEEE, ICML, NeurIPS, ACL, ICLR, arXiv, etc.)
- References or Bibliography section
If ANY red flag found → Verdict: FAIL immediately.

STEP 3 — FILLER CHECK:
Check for filler phrases like "I now can give a great answer", "Here is the document", "As requested".
If ANY found → Verdict: FAIL immediately.

STEP 4 — REPETITION CHECK:
Check Overview for repeated or near-identical sentences.
If 2 or more Overview sentences convey the same meaning → REPETITION_FAIL: YES → Verdict: FAIL.

STEP 5 — CLAIM AUDIT — Fix 5 — compact 2-line format per claim:
For EVERY factual sentence output EXACTLY 2 lines:

C: [claim text]
Q: YES/NO | D: YES/NO | S: YES/NO | V: PASS/FAIL

Where:
Q = QUOTE_IN_SOURCES  — does the CITE quote appear in VERIFIED SOURCE QUOTES above?
D = DUPLICATE_EVIDENCE — was this exact quote already used for a previous claim?
S = SEMANTIC_MATCH    — does the quote meaning actually support the claim meaning?
V = VERDICT           — PASS only if Q=YES, D=NO, S=YES. FAIL if any are wrong.

Rules:
- Q=NO means the writer invented the quote from training knowledge → V=FAIL
- D=YES means same quote used twice → V=FAIL
- S=NO means positive quote used as limitation or quote contradicts claim → V=FAIL
- Audit EVERY sentence — do not skip any claim
- Track all quotes seen — flag duplicates immediately

STEP 6 — FINAL SCORING:
Any V=FAIL → Verdict: FAIL. Any Q=NO → Verdict: FAIL. Any D=YES → Verdict: FAIL.
Any S=NO → Verdict: FAIL. REPETITION_FAIL: YES → Verdict: FAIL.
Red flags → FAIL. Filler → FAIL. Missing section → FAIL.
Only if ALL claims pass → Verdict: PASS.

Final verdict MUST match per-claim audit. No contradictions.

End your response EXACTLY with these 4 lines and nothing after:

Structure Score: X/10
Clarity Score: X/10
Factual Confidence: X/10
Verdict: PASS or FAIL
""",
        # Fix 2 — expected_output one line only
        expected_output="Compact 2-line claim audit ending with Structure Score, Clarity Score, Factual Confidence, and Verdict.",
        agent=validator_agent,
    )

    return research_task, writer_task, validator_task