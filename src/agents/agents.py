from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph

from agents.marketing_agent.marketing_agent import marketing_agent
from schema import AgentInfo

DEFAULT_AGENT = "marketing-agent"


@dataclass
class Agent:
    description: str
    graph: CompiledStateGraph


all_agents: dict[str, Agent] = {
    #ADD Agents HERE
   "marketing-agent": Agent(description="A marketing agent.", graph=marketing_agent),
}


def get_agent(agent_id: str) -> CompiledStateGraph:
    return all_agents[agent_id].graph


def get_all_agent_info() -> list[AgentInfo]:
    return [
        AgentInfo(key=agent_id, description=agent.description) for agent_id, agent in all_agents.items()
    ]
