import subprocess
import sys
from typing import Annotated, Sequence, TypeVar, List
from typing_extensions import TypedDict
from langgraph.graph import Graph, StateGraph
from agents.llmtools import get_llm
from agents.marketing_agent.marketing_schema import Competitor, MarketingInput, MarketingPlanState, Persona
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from agents.tools.searchweb import scrape_web, scrape_web_agent, search_web, search_web_with_query, use_browser
from agents.tools.wikisearch import search_wikipedia_with_query

class PersonaList(BaseModel):
    personas: List[Persona]

class CompetitorList(BaseModel):
    competitors: List[Competitor]

class SiteInfo(BaseModel):
    appName: str
    description: str
    keyfeatures: List[str]
    value_proposition: str

class MarketingStrategiesList(BaseModel):
    strategies: List[str]

class KeywordList(BaseModel):
    keywords: List[str]

class SubredditList(BaseModel):
    subreddits: List[str]

def create_marketing_graph() -> CompiledStateGraph:
    
    # Define state type
    workflow_state = TypeVar("workflow_state", bound=MarketingPlanState)

    # Needed for Langgraph studio to work
    # try:
    #     subprocess.run([sys.executable, "-m", "playwright", "install-deps"], check=True)
    #     subprocess.run([sys.executable, "-m", "playwright", "install"], check=True) 
    #     print("Playwright browsers installed successfully!")
    # except subprocess.CalledProcessError as e:
    #     print(f"Error installing Playwright browsers: {e}", file=sys.stderr)
    #     sys.exit(1)

    # Create personas node
    def create_personas(state: workflow_state) -> workflow_state:
        prompt = f"""
        Create {state['max_personas']} buyer personas for {state['appName']}.
        App description: {state['appDescription']}
        Key features: {state['keyfeatures']}
        Value proposition: {state['value_proposition']}

        Focus on their key characteristics, needs, and pain points.
        
        Return a list of personas, each with a name and description.
        """
        
        llm = get_llm()
        structured_llm = llm.with_structured_output(PersonaList)
        response = structured_llm.invoke(prompt)
        
        # Take only up to max_personas
        max_personas = int(state['max_personas'])  # Ensure integer type
        #print("max_personas ", max_personas)
        #print("len personas ", len(response.personas))
        return {"personas": response.personas[:max_personas]}
    
    async def search_web_for_competitors(state: workflow_state):
        results = search_web(f"Find website with a similar value proposition: {state['value_proposition']}")
        #print("SEARCH RESULTS", results)
        return {"search_results": results}
    
    async def search_web_for_competitors_by_hint(state: workflow_state):
        if state['competitor_hint']:
            results = search_web_with_query(f"Find website similar to {state['competitor_hint']}")
            #print("SEARCH RESULTS", results)
            return {"search_results": results}
        else:
            return {}

    # Research competitors node using web scraping 
    async def analyze_site(state: workflow_state) -> workflow_state:
        url = state["appUrl"]
        print("ANALYZING SITE", url)
        final_result = await scrape_web_agent(url,
            f"- App name\n"
            f"- Description\n"
            f"- Key features (as a list)\n"
            f"- Value proposition\n",
            SiteInfo
        )
        
        # Convert the final_result to JSON string if it's an object
        if not isinstance(final_result, (str, bytes, bytearray)):
            final_result = final_result.model_dump_json()
        
        parsed = SiteInfo.model_validate_json(final_result)
        return {"appDescription": parsed.description, "keyfeatures": parsed.keyfeatures, "value_proposition": parsed.value_proposition, "appName": parsed.appName}


    # Research competitors node using Browser Use
    async def analyze_site2(state: workflow_state) -> workflow_state:
        results = []

        final_result = await use_browser(f"""Visit website {state['appUrl']} focusing on:
             what the website is about, what it does, and what it offers.
             Visit 1 to 3 pages and extract the following information:
             - Description of the website
             - Key features of the website
             - Value proposition of the website
             - app name
            """, SiteInfo,6) #Max steps is 6

        if final_result:
            parsed = SiteInfo.model_validate_json(final_result)
            return {"appDescription": parsed.description, "keyfeatures": parsed.keyfeatures, "value_proposition": parsed.value_proposition, "appName": parsed.appName}
        else:
            return {}

    async def extract_keywords(state: workflow_state) -> workflow_state:
        prompt = f"""
        Thinking like a social media manager what are some keywords you would monitor for {state['appName']} whose value proposition is: {state['value_proposition']}

        The personas are: {state['personas']}
        
        Return a list of 5 keywords or phrases to search for to find posts to monitor and respond to.  Do not respond with more than 10 phrases.  
        Order the key words in order of relevance to {state['appName']} with the most relevant first.
        """
        llm = get_llm()
        structured_llm = llm.with_structured_output(KeywordList)
        response = structured_llm.invoke(prompt)
        return {"keywords": response.keywords}
    
    # Get human feedback node
    def get_feedback(state: workflow_state) -> workflow_state:
        # Here you could implement actual user interaction
        # For now we'll just store it in state
        return {"human_feedback": "Feedback received"}

    # End node to properly signal completion
    def end(state: workflow_state) -> workflow_state:
        # You can add any final state cleanup or validation here
        #print("Marketing analysis completed:", state)
        return {}

    async def finalize_competitors(state: workflow_state) -> workflow_state:
        """
        Analyze search results to create a final list of competitors.
        Uses browser to visit each site and extract relevant information.
        """
        llm = get_llm()

        results = []
        for search_result in state["search_results"]:
            try:
                doc = await scrape_web(search_result.link)
                prompt = f"""Extract the following information from this web page content:
                - All links to top level domains that appear to be competitors to Product Hunt
                - For each competitor also map their name and a brief description if available.
                
                Content:
                {doc.page_content}
                """
                
                structured_llm = llm.with_structured_output(CompetitorList)
                competitors = structured_llm.invoke(prompt)
                results.extend(competitors.competitors)
            except Exception as e:
                print(f"Error processing {search_result.link}: {str(e)}")
                continue

        # Update state with competitors
        prompt2 = f"""Given the list of competitors below determine which are the most relevant competitors, select no more than 10, to {state['appName']} an app that {state['appDescription']}:
        Order the list with the most relevant competitors first.
        Potential competitors:
        {results}
        """
        structured_llm = llm.with_structured_output(CompetitorList)
        response = structured_llm.invoke(prompt2)

        return {"competitors": response.competitors}

    async def get_marketing_suggestions(state: workflow_state):
        prompt = f"""
        Given the following information about {state['appName']} and its competitors, suggest 5 specific marketing strategies to promote {state['appName']}. 
        The strategy should be specific and provide actions to take and details someone can act

        App description: {state['appDescription']}
        Key features: {state['keyfeatures']}
        Value proposition: {state['value_proposition']}
        Competitors: {state['competitors']}
        """
        llm = get_llm()
        structured_llm = llm.with_structured_output(MarketingStrategiesList)
        response = structured_llm.invoke(prompt)
        # THIS CAUSES langgraph.errors.InvalidUpdateError when get_subreddits does it as well
        #state["marketing_suggestions"] = response.strategies
        #return state

        #print("MARKETING SUGGESTIONS", response.strategies)
        return {"marketing_suggestions": response.strategies}
    
    async def get_subreddits(state: workflow_state):
        #print("#####GET SUBREDDITS#########")
        prompt = f"""
        Given the following information about {state['appName']} and its competitors, suggest 5 subreddits to monitor or post on for {state['appName']}.
            App description: {state['appDescription']}
            Key features: {state['keyfeatures']}
            Value proposition: {state['value_proposition']}
            Competitors: {state['competitors']}
        """
        llm = get_llm()
        structured_llm = llm.with_structured_output(SubredditList)
        response = structured_llm.invoke(prompt)
        #state["subreddits"] = response.subreddits
        #return state
        #print(f"##### Found {len(response.subreddits)} subreddits")
        return {"subreddits": response.subreddits}

    # Create the graph
    workflow = StateGraph(MarketingPlanState,input=MarketingInput)

    # Add nodes
    workflow.add_node("analyze_site", analyze_site)
    workflow.add_node("create_personas", create_personas)
    workflow.add_node("extract_keywords", extract_keywords)
    #workflow.add_node("search_web_for_competitors", search_web_for_competitors)
    workflow.add_node("search_web_for_competitors_by_hint", search_web_for_competitors_by_hint)
    workflow.add_node("finalize_competitors", finalize_competitors)
    #workflow.add_node("get_feedback", get_feedback)
    workflow.add_node("get_marketing_suggestions", get_marketing_suggestions)
    workflow.add_node("get_subreddits", get_subreddits)
    workflow.add_node("__END__", end)


    # Create edges
    workflow.add_edge("analyze_site", "create_personas")
    workflow.add_edge("create_personas", "extract_keywords")
    workflow.add_edge("extract_keywords", "search_web_for_competitors_by_hint")
    workflow.add_edge("search_web_for_competitors_by_hint", "finalize_competitors")
    workflow.add_edge("finalize_competitors", "get_marketing_suggestions")
    workflow.add_edge("finalize_competitors", "get_subreddits")
    workflow.add_edge("get_subreddits", "__END__")
    workflow.add_edge("get_marketing_suggestions", "__END__")
    # Set entry point
    workflow.set_entry_point("analyze_site")

    # Compile graph
    graph =  workflow.compile(checkpointer=MemorySaver())
    #graph_image = graph.get_graph(xray=True).draw_mermaid_png()
    #with open("marketing_agent_graph.png", "wb") as f:
    #     f.write(graph_image)
    return graph

#define the graph
marketing_agent = create_marketing_graph()





# Helper function to run the graph
async def run_marketing_analysis(
    app_name: str,
    max_personas: int = 3
) -> MarketingPlanState:
    
    # Initialize state
    initial_state: MarketingPlanState = {
        "appName": app_name,
        "max_personas": max_personas,
        "human_feedback": "",
        "personas": []
    }
    
    # Create and run graph
    graph = create_marketing_graph()
    final_state = await graph.arun(initial_state)
    
    return final_state


# async def main():
#     llm = ChatOpenAI(model="gpt-4")
    
#     result = await run_marketing_analysis(
#         app_name="My Cool App",
#         llm=llm,
#         max_personas=3
#     )
    
#     # Access results
#     print("Personas:")
#     for persona in result["analysts"]:
#         print(persona.persona)
        
#     print("\nCompetitor Analysis:")
#     for analysis in result["competitor_analysis"]:
#         print(analysis)
