from crewai import Crew
from agents import build_agents
from tasks import create_tasks
from search import search_web


def build_crew(topic: str):
    # --------------------------------------------
    # 1. Build Agents
    # --------------------------------------------
    research_agent, writer_agent, validator_agent = build_agents()

    # --------------------------------------------
    # 2. Fetch Search Context
    # Multi-source: Tavily + DuckDuckGo + Wikipedia
    # search_web() now returns 3 values:
    #   - context_string  → full numbered sources for researcher
    #   - quotes_only     → extracted quotes only for validator (Fix 1)
    #   - source_count    → for metrics
    # --------------------------------------------
    search_context, quotes_only, source_count = search_web(topic)

    # --------------------------------------------
    # 3. Build Tasks
    # researcher receives full search_context
    # validator receives quotes_only — not full context
    # this is Fix 1 — ~35% validator input token reduction
    # --------------------------------------------
    research_task, writer_task, validator_task = create_tasks(
        research_agent,
        writer_agent,
        validator_agent,
        topic,
        search_context,
        quotes_only,
    )

    # --------------------------------------------
    # 4. Create Crew
    # --------------------------------------------
    crew = Crew(
        agents=[research_agent, writer_agent, validator_agent],
        tasks=[research_task, writer_task, validator_task],
        verbose=True,
    )

    return crew, source_count