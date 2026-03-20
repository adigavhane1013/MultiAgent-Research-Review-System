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
    # search_web() returns (context_string, source_count)
    # --------------------------------------------
    search_context, source_count = search_web(topic)

    # --------------------------------------------
    # 3. Build Tasks (Inject Search Context)
    # search_context passed to BOTH research and
    # validator tasks — validator uses it to cross-check
    # that writer citations came from real sources
    # --------------------------------------------
    research_task, writer_task, validator_task = create_tasks(
        research_agent,
        writer_agent,
        validator_agent,
        topic,
        search_context,
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