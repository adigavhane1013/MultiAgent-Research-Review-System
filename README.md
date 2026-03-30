# MultiAgent Research & Review System

A 3-agent CrewAI pipeline that takes a topic as input, searches the web across multiple sources, writes a fully cited technical document, and validates every single claim against real sources — automatically detecting and rejecting hallucinated output before anything gets saved.

Built entirely on free-tier AI models via OpenRouter. No paid API required beyond search tools.

---

## How It Works

```
You type a topic
        ↓
search.py — runs Tavily + DuckDuckGo + Wikipedia
        ↓
Returns: full source list, extracted quotes, source count
        ↓
Researcher Agent runs alone first (early exit optimization)
        ↓
Guard 1 — is the research output real? 
  FAIL → exit immediately, writer never runs, tokens saved
  PASS → continue
        ↓
Writer Agent + Validator Agent run
        ↓
Guard 2 → Guard 4 → Guard 3 checks in order
        ↓
PASS → document saved to output/
FAIL → saved to output/failed/ → retried once → if still FAIL → exit
        ↓
Stats logged to metrics/history_log.json
```

The researcher runs alone first intentionally. If it produces garbage, the writer and validator never run — saving tokens and time on every bad run.

---

## The 3 Agents

### Researcher
- Receives the full numbered source list from search.py
- Reads every source and extracts structured facts
- Output format: `[Category|SourceNum] "VERBATIM_QUOTE"`
- Categories: `General` / `Features` / `UseCases` / `Limitations`
- Rules: no training knowledge, every quote must be verbatim from a source, use cases must name a specific company or domain, max 4 limitation facts

### Writer
- Receives the researcher's compact fact list
- Converts each fact into a sentence with a `[CITE: "source quote"]` tag
- Produces a 4-section Markdown document: Overview, Key Concepts, Real-World Use Cases, Limitations
- Rules: start immediately with the title, every sentence has its own citation, no preamble or filler

### Validator
- Receives the writer's document + extracted quotes from search (not the full context — token optimization)
- Audits every claim in compact 2-line format:
  ```
  C: [claim text]
  Q: YES/NO | D: YES/NO | S: YES/NO | V: PASS/FAIL
  ```
  - `Q` = quote exists in real search results
  - `D` = duplicate evidence used
  - `S` = semantic match between quote and claim
  - `V` = per-claim verdict
- Ends with 4 score lines and a final Verdict

---

## Hallucination Detection — 6 Layers

| Layer | Where | What It Catches |
|---|---|---|
| **Guard 1** | `main.py` | Researcher returned filler or garbage — exits before writer runs |
| **Guard 2** | `main.py` | Writer returned filler, missing sections, or too few citations |
| **Guard 3** | `main.py` | Validator said PASS but its own audit shows failures — overrides to FAIL |
| **Guard 4** | `main.py` | Validator output truncated mid-audit by token limit |
| **QUOTE_IN_SOURCES** | Validator | Writer used a quote that doesn't exist in the real search results |
| **SEMANTIC_MATCH** | Validator | Writer used a positive quote to support a negative claim, or quote contradicts the claim |

Guard 3 is the most important. Free-tier models frequently say PASS at the bottom while their own line-by-line audit shows clear failures. Guard 3 reads the entire audit and overrides the stated verdict when it finds any `Q: NO`, `D: YES`, `S: NO`, or `V: FAIL` signals.

---

## Search Pipeline

Each search tool runs twice — once for the general topic, once specifically for limitations. Wikipedia runs once (it has a limitations section internally).

```
Tavily     × 2  (general + limitations)
DuckDuckGo × 2  (general + limitations)  
Wikipedia  × 1
─────────────────
5 searches total per run
```

**Filtering applied:**
- Duplicate URLs removed
- Low-quality domains blocked: reddit, quora, yahoo, pinterest, twitter, facebook, stackexchange, etc.
- Thin content filtered out (under 200 chars)
- Each source capped at 1500 chars (token optimization)
- Max 80 unique quotes extracted and passed to the validator

**Average sources per run: 16**

---

## Model Setup

Primary model with 4 automatic fallbacks — all free tier via OpenRouter:

```
Primary:    arcee-ai/trinity-large-preview:free
Fallback 1: meta-llama/llama-3.3-70b-instruct:free
Fallback 2: mistralai/mistral-small-3.1-24b-instruct:free
Fallback 3: google/gemma-3-27b-it:free
Fallback 4: nousresearch/hermes-3-llama-3.1-405b:free
```

If all 5 fail, the run exits with a RuntimeError. A 2-second delay runs between each fallback attempt to avoid rate limit cascades.

---

## File Structure

```
├── main.py              — runs everything: guard functions, early exit, retry logic, final verdict
├── tasks.py             — prompt instructions for all 3 agents
├── agents.py            — agent definitions: roles, goals, backstories, LLM assignments
├── crew_runner.py       — calls search_web(), unpacks results, builds tasks and crew
├── llms.py              — model setup, 5-model fallback chain
├── config.py            — all settings: model names, token limits, delay values, flags
├── search.py            — Tavily + DuckDuckGo + Wikipedia pipeline, quote extraction
├── batch_run.py         — run multiple topics sequentially from a list
├── clean_history.py     — fixes and cleans history_log.json
├── analyze_metrics.py   — generates a full report from all historical runs
├── metrics.py           — saves per-run stats after each run completes
├── test_guards.py       — 57 pytest tests covering all 6 guard layers
├── testmodels.py        — tests which models are available and responding on OpenRouter
├── requirements.txt     — all dependencies with exact versions
├── history_log.json     — log of every run: topic, verdict, verification rate, duration
└── utils/
    └── file_utils.py    — save_report() and save_failed_report() helpers
```

---

## CI/CD

GitHub Actions runs the full test suite on every push to `main`.

- **Platform:** ubuntu-latest, Python 3.10
- **What runs:** `pytest test_guards.py -v --maxfail=2 --tb=short`
- **Dummy keys injected** for all API dependencies so imports don't fail
- **Current status:** 57/57 passing ✅

---

## Run Metrics (60 runs)

| Metric | Value |
|---|---|
| Total runs | 60 |
| Passed | 46 (76.7%) |
| Failed | 14 |
| Unique topics researched | 58 |
| Total claims evaluated | 658 |
| Verified claims | 653 |
| Fabricated quotes that passed through | **0** |
| Retries used | 12 (20% of runs) |
| Avg verification rate | 81% |
| Avg sources per run | 16 |
| Avg run duration | 2.9 mins |

---

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/adigavhane1013/MultiAgent-Research-Review-System.git
cd MultiAgent-Research-Review-System
```

**2. Create virtual environment**
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Mac/Linux
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Create `.env` file in the project root**
```
OPENROUTER_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
```

Get your keys here:
- OpenRouter: https://openrouter.ai — free account, no credit card needed
- Tavily: https://tavily.com — free tier available

**5. Run**
```bash
python main.py
```

Type a topic when prompted. The pipeline runs automatically and saves the result to `output/`.

---

## Run Tests

```bash
pytest test_guards.py -v
```

57 tests covering all 6 guard layers including:
- Legacy and compact researcher output formats (Guard 1)
- All 4 document sections and citation checks (Guard 2)
- Verdict override scenarios including self-contradicting validator output (Guard 3)
- Truncated and filler validator output (Guard 4)
- Compact `Q:/D:/S:/V:` signal detection (Guards 3 and 4)

---

## Stack

| Tool | Purpose |
|---|---|
| **Python 3.10+** | Runtime |
| **CrewAI** | Multi-agent orchestration |
| **OpenRouter** | Free-tier LLM access (5-model fallback chain) |
| **Tavily** | Primary web search |
| **DuckDuckGo** | Secondary web search |
| **Wikipedia** | Encyclopedic background facts |
| **pytest** | Guard logic test suite |
| **GitHub Actions** | CI — runs tests on every push |
| **python-dotenv** | API key management via `.env` |