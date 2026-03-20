from crewai import Task
from config import STRICT_VERBATIM_MODE


# ===============================
# STRICT VERBATIM BLOCK
# ===============================

STRICT_MODE_TEXT = """
STRICT VERBATIM MODE ENABLED:

1. You MUST use the exact SOURCE_QUOTE text for every claim.
2. Do NOT shorten the quote.
3. Do NOT remove trailing clauses.
4. Do NOT paraphrase.
5. Do NOT summarize.
6. The documentation sentence must match SOURCE_QUOTE exactly.
7. If exact reuse is not possible, OMIT the claim entirely.
"""


def create_tasks(research_agent, writer_agent, validator_agent, topic, search_context):

    strict_block = STRICT_MODE_TEXT if STRICT_VERBATIM_MODE else ""

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
If a quote only supports one claim, extract only one fact from it.
Using the same quote twice = hallucination padding = REJECTED.

RULE 2 — LIMITATIONS CAP:
Extract a MAXIMUM of 4 limitation facts total.
Each limitation must have a completely different SOURCE_QUOTE.
Do NOT generate 10, 15, or 20 limitations — this is padding.
If you cannot find 4 distinct limitation quotes, extract fewer.

RULE 3 — NO PADDING:
If sources are thin on a category, extract fewer facts.
Never invent, infer, or generalize to fill gaps.
A fact with a weak or stretched quote is worse than no fact.

RULE 4 — NO TRAINING KNOWLEDGE:
Only include facts with DIRECT TEXTUAL SUPPORT in the search results above.
Do NOT use any knowledge from your training data.
Do NOT cite academic papers, author names, or journal references.
Do NOT hallucinate sources — only reference [SOURCE N] numbers from above.

RULE 5 — DEFINITION CAP (CRITICAL):
In the General category, extract MAXIMUM 1 definition sentence.
A definition sentence is any sentence that matches this pattern:
"[Topic] is a/an/the [type of thing] that/which/for..."
Examples of definition sentences — ONLY ONE ALLOWED:
  "Cybersecurity is the practice of protecting systems from attacks."
  "Kafka is an open-source distributed event streaming platform."
  "Docker is a containerization platform."
After extracting 1 definition, STOP extracting definitions.
The remaining General facts MUST be about:
- Who created it and when (origin story)
- Specific version numbers or release dates
- Named technical components or architecture
- Adoption statistics, usage numbers, named companies using it
- Standardization bodies or protocols it follows
NOT more reworded definitions.

RULE 6 — SPECIFICITY OVER GENERALITY:
Always prefer facts that contain:
- Specific numbers, percentages, benchmarks (e.g. "processes 1 trillion messages/day")
- Named companies, tools, or products (e.g. "used by Netflix, LinkedIn, Uber")
- Specific technical mechanisms (e.g. "uses SHA-256 hashing")
- Concrete named examples (e.g. "RFC 6455 standardized WebSockets in 2011")
Over vague generic sentences like:
- "It is used by many companies"
- "It provides many benefits"
- "It is widely adopted"
These vague sentences = low quality = REJECTED in favor of specific ones.

RULE 7 — USE CASES MUST BE SPECIFIC:
Each use case fact must name a specific domain, industry, company, or product.
REJECTED (too vague): "Used by companies for data processing"
ACCEPTED (specific): "Used by Netflix for real-time event streaming at scale"
REJECTED (too vague): "Used in healthcare applications"
ACCEPTED (specific): "Used in healthcare for securing patient records and EHR systems"
If no specific use case quote exists in sources, extract fewer use cases.

For the Limitations category specifically:
- Look for phrases like: "limitation", "drawback", "weakness", "problem", "issue",
  "criticism", "disadvantage", "slow", "difficult", "not suitable", "lacks", "poor"
- The SOURCE_QUOTE for a limitation MUST be negative in meaning — a quote that
  praises or compliments the technology is NOT a valid limitation quote.
- If a quote says something is "doing well" or "works great" — it is NOT a limitation.
- ONLY write "NO LIMITATIONS FOUND IN SOURCES" if you found ZERO limitation facts.
- If you found ANY limitation facts above, do NOT write this line at all.

For every fact provide:
- FACT
- SOURCE_QUOTE (verbatim from the search results above ONLY)
- SOURCE_NUM (must match a [SOURCE N] from the search results above)
- CATEGORY (General / Features / UseCases / Limitations)
""",
        expected_output="""Structured fact list with FACT, SOURCE_QUOTE, SOURCE_NUM, and CATEGORY for each entry.
All facts must come directly from the provided search results only.
Every SOURCE_QUOTE must be unique — no quote reused across multiple facts.
Maximum 1 definition sentence in General category — remaining General facts must be
about origin, creator, version, adoption stats, or named technical components.
Use case facts must name specific domains, industries, companies, or products.
Prefer facts with numbers, benchmarks, named entities over vague generic sentences.
Maximum 4 limitation facts, each with a distinct negative SOURCE_QUOTE.
No academic paper citations. No invented sources.
Only write 'NO LIMITATIONS FOUND IN SOURCES' if zero limitation facts were found.""",
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

STRICT RULES:
1. Every sentence MUST be traceable to a SOURCE_QUOTE from the research output.
2. After EACH sentence add: [CITE: "exact SOURCE_QUOTE"]
3. Write ONLY supported facts. If a claim cannot use exact SOURCE_QUOTE, omit it.
4. No inference. No summarization. No expansion beyond what sources say.
5. Output pure Markdown only.
6. In the Overview section, each sentence MUST be on its own line with its own
   [CITE: "..."] tag. Never combine two sentences into one paragraph with only
   one citation — every sentence needs its own citation.

CRITICAL — CITATION RULES:
- ONLY reference [SOURCE N] numbers that exist in the search results.
- Do NOT invent, generate, or reference academic papers, author names, or journals.
- Do NOT add a References or Bibliography section.
- Do NOT cite anything that was not in the provided search results.
- If no source supports a claim, OMIT the claim entirely.

OVERVIEW WRITING RULES:
- Write exactly 2-4 sentences in Overview.
- Sentence 1: the single best definition from CATEGORY=General facts.
- Sentence 2-4: origin, creator, adoption stats, or named technical detail.
- Do NOT repeat similar definition sentences — each Overview sentence must add
  new information beyond what the previous sentence said.
- NEVER write 3-4 sentences that all say "[Topic] is a practice of protecting X"
  in different words — this is repetition padding and is REJECTED.

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
- Use CATEGORY=Limitations facts from the research output.
- Include a MAXIMUM of 4 limitation bullets.
- If the researcher found real limitations, include them as bullets with citations.
- ONLY write "Insufficient source data for this section." if the researcher
  explicitly stated "NO LIMITATIONS FOUND IN SOURCES".
- Do NOT use a positive/feature quote as a limitation bullet — they are opposites.
- Do NOT repeat the same citation quote across multiple limitation bullets.
""",
        expected_output=f"""Markdown document starting immediately with # {topic.upper()}.
Contains exactly: ## Overview, ## Key Concepts, ## Real-World Use Cases, ## Limitations.
Every sentence has its own [CITE: "..."] tag — no sentence shares a citation.
Overview has 2-4 sentences each on their own line — first sentence is definition,
remaining sentences add new information (origin, stats, named components).
No repeated or near-identical sentences in Overview.
Maximum 4 limitation bullets, each with a distinct negative citation.
No preamble. No filler phrases. No academic references. No References section.
Limitations section only contains actual drawbacks — never positive feature quotes.""",
        agent=writer_agent,
    )

    # ===============================
    # VALIDATOR TASK
    # ===============================
    # search_context is injected here so the validator can cross-check
    # every EVIDENCE quote against the actual search results.
    # This catches the circular citation hallucination where the writer
    # invents a quote and cites itself — CLAIM == EVIDENCE but neither
    # came from real sources.

    validator_task = Task(
        description=f"""
You are a Fact-Check Auditor. Your job is to audit the document produced by the writer.

You also have access to the ORIGINAL SEARCH RESULTS that were used to produce this document:

--- ORIGINAL SEARCH RESULTS START ---
{search_context}
--- ORIGINAL SEARCH RESULTS END ---

STEP 1 — STRUCTURAL CHECK:
Verify the document contains ALL of these sections:
- # Title
- ## Overview
- ## Key Concepts
- ## Real-World Use Cases
- ## Limitations

If any section is missing → Verdict: FAIL immediately.

STEP 2 — HALLUCINATION CHECK:
Scan the entire document for these RED FLAGS:
- Academic paper citations (e.g. "Jacobs et al.", "Smith et al.")
- Author names used as sources (e.g. "According to Bengio...")
- Journal or conference references (IEEE, ICML, NeurIPS, ACL, ICLR, arXiv, etc.)
- A References or Bibliography section with paper citations
- Any [N] footnote-style citations pointing to papers

If ANY red flag is found → Verdict: FAIL immediately.
Do not continue auditing. State which red flag was found.

STEP 3 — WRITER FILLER CHECK:
Check if the document contains filler phrases like:
- "I now can give a great answer"
- "Here is the document"
- "As requested"
- Any introductory sentence that is not part of the actual document content

If ANY filler phrase is found → Verdict: FAIL immediately.

STEP 4 — REPETITION CHECK:
Check the Overview section for repeated or near-identical sentences.
If 2 or more Overview sentences convey the same meaning in different words
(e.g. multiple sentences all saying "[Topic] is a practice of protecting X")
→ mark REPETITION_FAIL: YES and set Verdict: FAIL.

STEP 5 — CLAIM AUDIT:
For EVERY sentence in the document that makes a factual claim,
output EXACTLY this format with no deviation:

CLAIM: [the sentence being audited]
CITE_TAG_PRESENT: YES or NO
EVIDENCE: [the exact quote used as evidence, or NOT FOUND]
QUOTE_IN_SOURCES: YES or NO
DUPLICATE_EVIDENCE: YES or NO
SEMANTIC_MATCH: YES or NO
VERIFIED: YES or NO
VERDICT: PASS or FAIL

Rules:
- CITE_TAG_PRESENT: YES only if a [CITE: "..."] tag is present on that sentence
- EVIDENCE: copy the exact text from inside the [CITE: "..."] tag
- QUOTE_IN_SOURCES: YES only if the EVIDENCE quote appears (even partially) in the
  ORIGINAL SEARCH RESULTS above. NO if the quote cannot be found anywhere in
  the search results — this means the writer invented it from training knowledge.
- DUPLICATE_EVIDENCE: YES if the same EVIDENCE quote was already used for a previous claim
- VERIFIED: YES only if ALL of these are true:
    * CITE_TAG_PRESENT is YES
    * QUOTE_IN_SOURCES is YES
    * DUPLICATE_EVIDENCE is NO
    * The quote actually supports the claim's meaning (SEMANTIC MATCH)
    * Not a Limitations bullet using a positive/feature quote

- SEMANTIC MATCH CHECK (critical):
    Ask yourself: does the EVIDENCE quote actually support what the CLAIM is saying?
    Examples of semantic mismatch → VERIFIED: NO:
    * CLAIM says something is a weakness/limitation, but EVIDENCE quote is positive/praising
    * CLAIM says something is fast, but EVIDENCE quote says it is slow
    * CLAIM says something is widely adopted, but EVIDENCE says it is niche
    * CLAIM implies a negative outcome, but EVIDENCE describes a benefit
    If the quote's meaning contradicts or does not support the claim → VERIFIED: NO
    Add a new field SEMANTIC_MATCH: YES or NO before VERIFIED

- VERIFIED: NO if ANY of the above conditions fail
- VERDICT: FAIL if VERIFIED is NO for any reason

IMPORTANT: Do NOT skip any claim. Audit every single sentence.
IMPORTANT: Track all EVIDENCE quotes you have seen — if the same quote appears
again for a different claim, mark DUPLICATE_EVIDENCE: YES.

STEP 6 — FINAL SCORING:
Count your results carefully:
- If ANY claim has VERIFIED: NO → Verdict: FAIL — NO EXCEPTIONS
- If ANY claim has CITE_TAG_PRESENT: NO → Verdict: FAIL — NO EXCEPTIONS
- If ANY claim has QUOTE_IN_SOURCES: NO → Verdict: FAIL — NO EXCEPTIONS
- If ANY claim has DUPLICATE_EVIDENCE: YES → Verdict: FAIL — NO EXCEPTIONS
- If ANY claim has SEMANTIC_MATCH: NO → Verdict: FAIL — NO EXCEPTIONS
- If REPETITION_FAIL: YES → Verdict: FAIL — NO EXCEPTIONS
- If hallucination red flags found → Verdict: FAIL
- If filler phrases found → Verdict: FAIL
- If any required section missing → Verdict: FAIL
- Only if ALL claims pass → Verdict: PASS

YOUR FINAL VERDICT MUST MATCH YOUR PER-CLAIM AUDIT.
If you marked any claim VERDICT: FAIL above, the final Verdict must be FAIL.
Do not write Verdict: PASS if any individual claim failed.

End your response EXACTLY with these 4 lines and nothing after:

Structure Score: X/10
Clarity Score: X/10
Factual Confidence: X/10
Verdict: PASS or FAIL
""",
        expected_output="""Complete claim-by-claim audit using
CLAIM/CITE_TAG_PRESENT/EVIDENCE/QUOTE_IN_SOURCES/DUPLICATE_EVIDENCE/SEMANTIC_MATCH/VERIFIED/VERDICT format.
Ends exactly with Structure Score, Clarity Score, Factual Confidence, and Verdict lines.
FAIL if any claim unverified, citation missing, quote not found in search results,
duplicate evidence used, semantic mismatch between claim and evidence,
repeated/near-identical Overview sentences, hallucinated references, filler phrases,
or positive quote used as limitation evidence.
Final Verdict must always match per-claim audit results — no contradictions.""",
        agent=validator_agent,
    )

    return research_task, writer_task, validator_task