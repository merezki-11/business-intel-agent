from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator
import os

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
search = DuckDuckGoSearchRun()


class AgentState(TypedDict):
    topic: str
    plan: str
    research: str
    brief: str
    messages: Annotated[list, operator.add]


def planner_agent(state: AgentState) -> AgentState:
    print("--- Planner Agent Running ---")
    response = llm.invoke([
        SystemMessage(content="""You are a business intelligence planner. 
        Given a company or market topic, create a structured research plan with 5 specific questions to investigate.
        Format your output as a numbered list of questions only."""),
        HumanMessage(content=f"Create a research plan for: {state['topic']}")
    ])
    return {"plan": response.content, "messages": [response]}


def research_agent(state: AgentState) -> AgentState:
    print("--- Research Agent Running ---")
    questions = state["plan"].strip().split("\n")
    all_research = []
    for question in questions:
        if question.strip():
            try:
                result = search.run(question.strip())
                all_research.append(f"Q: {question.strip()}\nFindings: {result}\n")
            except Exception as e:
                all_research.append(f"Q: {question.strip()}\nFindings: Could not retrieve data.\n")
    research_compiled = "\n".join(all_research)
    return {"research": research_compiled, "messages": [HumanMessage(content=research_compiled)]}


def writer_agent(state: AgentState) -> AgentState:
    print("--- Writer Agent Running ---")
    response = llm.invoke([
        SystemMessage(content="""You are a professional business intelligence analyst.
        Using the research provided, write a comprehensive business intelligence brief.
        Structure it with these sections:
        1. Executive Summary
        2. Market Overview
        3. Key Players & Competition
        4. Recent Developments
        5. Opportunities
        6. Risks & Challenges
        7. Conclusion
        Write in a professional, clear, and concise style."""),
        HumanMessage(content=f"Topic: {state['topic']}\n\nResearch Data:\n{state['research']}")
    ])
    return {"brief": response.content, "messages": [response]}


workflow = StateGraph(AgentState)
workflow.add_node("planner", planner_agent)
workflow.add_node("researcher", research_agent)
workflow.add_node("writer", writer_agent)
workflow.set_entry_point("planner")
workflow.add_edge("planner", "researcher")
workflow.add_edge("researcher", "writer")
workflow.add_edge("writer", END)
graph = workflow.compile()


class ResearchRequest(BaseModel):
    topic: str


@app.get("/")
def root():
    return {"message": "Business Intelligence Agent API is running!"}


@app.post("/research")
async def run_research(request: ResearchRequest):
    if not request.topic.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    initial_state = {
        "topic": request.topic,
        "plan": "",
        "research": "",
        "brief": "",
        "messages": []
    }

    result = graph.invoke(initial_state)

    return {
        "topic": request.topic,
        "plan": result["plan"],
        "brief": result["brief"]
    }