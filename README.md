# MultiAgent Research & Review System

A 3-agent pipeline that takes a topic, searches the web, writes a cited technical document, and validates every claim against real sources — automatically rejecting hallucinated output.

---

## How It Works

```
User inputs topic
       ↓
Search (Tavily + DuckDuckGo + Wikipedia)
       ↓
Researcher Agent — extracts facts + source quotes
       ↓
Writer Agent — builds cited Markdown document
       ↓
Validator Agent — audits every claim vs real sources
       ↓
PASS → saved to output/
FAIL → saved to output/failed/
```

---

## Agents

**Researcher**
Reads search results and extracts structured facts. Every fact must include a verbatim quote from a real source. Cannot use training knowledge.

**Writer**
Converts facts into a Markdown document. Every sentence must end with `[CITE: "source quote"]`. No inference, no expansion beyond what sources provide.

**Validator**
Audits every claim one by one against the original search results. Checks citation presence, source grounding, duplicate evidence, and semantic match between claim and evidence.

---

## Hallucination Detection — 6 Layers

| Guard | What It Catches |
|---|---|
| Guard 1 | Researcher filler output — no real facts extracted |
| Guard 2 | Writer filler output — missing sections or citations |
| Guard 3 | Verdict override — catches failures even if validator says PASS |
| Guard 4 | Validator truncation — incomplete audit output |
| QUOTE_IN_SOURCES | Evidence quote doesn't exist in real search results |
| SEMANTIC_MATCH | Evidence quote contradicts what the claim says |

---

## File Structure

```
├── main.py              # runs everything, all guard logic, final verdict
├── tasks.py             # prompt instructions for all 3 agents
├── agents.py            # defines all 3 agents with roles and goals
├── crew_runner.py       # fetches search results, builds the crew
├── llms.py              # model setup, fallback chain
├── config.py            # settings — model names, flags, limits
├── search.py            # search logic — Tavily, DuckDuckGo, Wikipedia
├── batch_run.py         # run multiple topics automatically
├── clean_history.py     # fixes and cleans history_log.json
├── analyze_metrics.py   # generates full report from all runs
├── metrics.py           # saves per-run stats after each run
├── test_guards.py       # pytest tests for all guard logic
├── testmodels.py        # tests available models on OpenRouter
├── requirements.txt     # all dependencies with exact versions
└── history_log.json     # every run ever — topic, verdict, stats
```

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
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Mac/Linux
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Create `.env` file**
```
OPENROUTER_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
```

**5. Run**
```bash
python main.py
```

---

## Run Tests

```bash
pytest test_guards.py -v
```

---

## Stack

- **CrewAI** — multi-agent orchestration
- **OpenRouter** — LLM access (free tier)
- **Tavily** — primary search
- **DuckDuckGo** — secondary search
- **Wikipedia** — encyclopedic background facts
- **pytest** — guard logic testing
- **Python 3.11+**
