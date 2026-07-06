# ruff: noqa
import os
import re
import sys
import json
import logging
import datetime
from pydantic import BaseModel, Field

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import AgentTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.adk.workflow import Workflow, START
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.genai import types

from .config import config

# Setup security audit logger
logger = logging.getLogger("security_audit")

def log_audit(event_type: str, severity: str, details: dict):
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "event_type": event_type,
        "severity": severity,
        "details": details
    }
    print(f"AUDIT_LOG: {json.dumps(log_entry)}")

# Pydantic models for structured outputs
class AdvisorOutput(BaseModel):
    advice: str = Field(description="The professional advice/recommendation provided by the expert.")
    citations: list[str] = Field(description="Any reference links or sources used.")

class OrchestratorOutput(BaseModel):
    selected_track: str = Field(description="The chosen expertise track: 'carbon', 'waste', 'goal', or 'direct'.")
    response: str = Field(description="Response back to the user, or goal suggestion.")

# MCP Server Connection Configuration
current_dir = os.path.dirname(os.path.abspath(__file__))
mcp_server_path = os.path.join(current_dir, "mcp_server.py")

mcp_connection = StdioConnectionParams(
    server_params=StdioServerParameters(
        command=sys.executable,
        args=[mcp_server_path]
    )
)

# Initialize MCP Toolsets for specialized agents
carbon_mcp_toolset = McpToolset(
    connection_params=mcp_connection,
    tool_filter=["estimate_appliance_emissions", "find_green_events"]
)

waste_mcp_toolset = McpToolset(
    connection_params=mcp_connection,
    tool_filter=["get_recycling_rules", "find_green_events"]
)

# Specialized Agents
carbon_expert = Agent(
    name="carbon_expert",
    model=Gemini(model=config.model),
    instruction="""You are a Carbon Footprint and Energy Expert.
Analyze the user request and use your estimate_appliance_emissions or find_green_events tools to provide precise estimates and recommendations.
Provide advice on reducing energy usage, home appliance carbon emissions, transport footprints, and green energy alternatives.
Be concise and structured. Use bullet points where appropriate.""",
    tools=[carbon_mcp_toolset],
    output_schema=AdvisorOutput,
)

waste_expert = Agent(
    name="waste_expert",
    model=Gemini(model=config.model),
    instruction="""You are a Waste Minimization and Recycling Expert.
Analyze the user request and use your get_recycling_rules or find_green_events tools to retrieve specific instructions.
Provide advice on recycling guidelines, composting, reducing single-use plastics, and zero-waste household strategies.
Be concise and structured. Use bullet points where appropriate.""",
    tools=[waste_mcp_toolset],
    output_schema=AdvisorOutput,
)

eco_orchestrator = Agent(
    name="eco_orchestrator",
    model=Gemini(model=config.model),
    instruction="""You are the Eco Advisor Orchestrator.
Your goal is to parse user requests and delegate them to the appropriate expert using the tools:
- carbon_expert: For energy, carbon footprints, appliance emissions, transport footprints, green home heating, solar, electric vehicles.
- waste_expert: For recycling, composting, zero waste, plastics, circular economy.

If the user wants to set a green/eco goal (e.g. "I want to set a goal", "setup weekly tracking"), select the 'goal' track and suggest a custom goal for them.
If the request is a general greeting or does not require specialist knowledge, answer it directly and set selected_track to 'direct'.

Always output the selected track in the selected_track field ('carbon', 'waste', 'goal', or 'direct').
""",
    tools=[AgentTool(carbon_expert), AgentTool(waste_expert)],
    output_schema=OrchestratorOutput,
)

# Workflow Function Nodes
def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    user_text = ""
    if node_input.parts:
        user_text = "".join(part.text for part in node_input.parts if part.text)

    # 1. PII Scrubbing
    pii_patterns = {
        "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"
    }
    
    scrubbed_text = user_text
    pii_detected = False
    for pii_type, pattern in pii_patterns.items():
        matches = re.findall(pattern, scrubbed_text)
        if matches:
            pii_detected = True
            scrubbed_text = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", scrubbed_text)
            log_audit("pii_scrubbed", "INFO", {"pii_type": pii_type, "count": len(matches)})

    # 2. Prompt Injection Check
    injection_keywords = ["ignore previous instructions", "system prompt", "override rules", "you are now", "dan mode"]
    injection_detected = False
    lower_text = scrubbed_text.lower()
    for kw in injection_keywords:
        if kw in lower_text:
            injection_detected = True
            log_audit("prompt_injection_attempt", "CRITICAL", {"keyword": kw, "input": user_text})
            break

    if injection_detected:
        return Event(
            output="Security check failed: Prompt injection attempt detected.",
            route="security_fail"
        )

    # 3. Domain-Specific check (Eco Relevance)
    eco_keywords = [
        "recycle", "co2", "carbon", "waste", "energy", "compost", "eco", "green", 
        "solar", "electric", "planet", "environment", "sustain", "pollution", 
        "conservation", "climate", "water", "plastic", "paper", "cardboard", 
        "aluminum", "glass", "appliances", "emission", "goal", "hello", "hi"
    ]
    is_eco_related = any(kw in lower_text for kw in eco_keywords)
    if not is_eco_related:
        log_audit("off_topic_warning", "WARNING", {"input": user_text})

    return Event(
        output=scrubbed_text,
        route="clear",
        state={"user_message": scrubbed_text, "pii_was_scrubbed": pii_detected}
    )

def routing_node(ctx: Context, node_input: dict) -> Event:
    selected_track = node_input.get("selected_track", "direct")
    response = node_input.get("response", "")
    
    ctx.state["orchestrator_response"] = response
    
    if selected_track == "goal":
        ctx.state["pending_goal"] = response
        return Event(output=response, route="needs_confirmation")
    
    return Event(output=response, route="direct_response")

async def human_confirmation_node(ctx: Context, node_input: str):
    if not ctx.resume_inputs or "confirm_goal" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="confirm_goal", 
            message=f"I suggested this goal: '{node_input}'. Do you want to confirm and track this goal? (yes/no)"
        )
        return
        
    user_confirm = ctx.resume_inputs["confirm_goal"].strip().lower()
    if user_confirm in ("yes", "y", "confirm"):
        ctx.state["confirmed_goal"] = ctx.state.get("pending_goal")
        result = f"Goal confirmed! We are now tracking your goal: '{ctx.state.get('confirmed_goal')}'"
    else:
        result = "Goal setup cancelled."
        
    yield Event(output=result)

def final_response_node(ctx: Context, node_input: str) -> Event:
    content = types.Content(
        role="model",
        parts=[types.Part.from_text(text=node_input)]
    )
    return Event(content=content, output=node_input)

# Workflow Graph Definition
from google.adk.workflow import Edge, FunctionNode

# Wrap plain functions as FunctionNodes
fn_security = FunctionNode(func=security_checkpoint, name="security_checkpoint")
fn_routing = FunctionNode(func=routing_node, name="routing_node")
fn_hitl = FunctionNode(func=human_confirmation_node, name="human_confirmation_node", rerun_on_resume=True)
fn_final = FunctionNode(func=final_response_node, name="final_response_node")

eco_advisor_workflow = Workflow(
    name="eco_advisor_workflow",
    edges=[
        Edge(from_node=START, to_node=fn_security),
        Edge(from_node=fn_security, to_node=eco_orchestrator, route="clear"),
        Edge(from_node=fn_security, to_node=fn_final, route="security_fail"),
        Edge(from_node=eco_orchestrator, to_node=fn_routing),
        Edge(from_node=fn_routing, to_node=fn_hitl, route="needs_confirmation"),
        Edge(from_node=fn_routing, to_node=fn_final, route="direct_response"),
        Edge(from_node=fn_hitl, to_node=fn_final),
    ]
)

app = App(
    root_agent=eco_advisor_workflow,
    name="app",
)
