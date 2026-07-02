import os
import json
import re
from typing import Any
from typing_extensions import TypedDict
from google.adk.events import RequestInput
from google.adk import Workflow
from google.adk.apps import App
from .tools import get_weather

# GCP Auth configuration
os.environ["GOOGLE_CLOUD_PROJECT"] = "demo-project"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"


class RiskState(TypedDict, total=False):
    animal: str
    location: str
    risk_level: str
    risk_trend: str
    previous_reports: int
    recommended_action: str
    officer_decision: str
    weather: str
    is_safe: bool


# ---------------------------------------------------------------------------
# Node functions — bulletproof state handling via ctx (ADK Context)
# ---------------------------------------------------------------------------
# ADK FunctionNode parameter binding rules (state mode):
#   - A parameter named "ctx" receives the ADK Context object.
#   - A parameter named "node_input" receives the actual user/node input.
#   - All other parameters are looked up BY NAME in ctx.state.
# ctx.state is an ADK State object (not a plain dict). Use .get() / .to_dict()
# to read, and return a plain dict to merge updates back into state.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Security helpers — Pre-LLM screening layer (Day 6)
# ---------------------------------------------------------------------------

# Keywords that indicate a prompt-injection or fraudulent report
_INJECTION_KEYWORDS = [
    "ignore previous instructions",
    "prank",
    "fake",
    "hack",
    "disregard",
    "override",
    "bypass",
]


def redact_pii(text: str) -> str:
    """Scrub PII from free-text input before it enters the pipeline.

    Redacts:
      - Phone numbers  (10+ consecutive digits, with optional separators)
      - Email addresses
      - 12-digit Aadhaar-style national IDs
      - GPS coordinate pairs  (e.g. 12.9716, 77.5946)
    """
    # GPS coordinates — match lat/long pairs like  12.9716, 77.5946
    text = re.sub(
        r"-?\d{1,3}\.\d{3,},\s*-?\d{1,3}\.\d{3,}",
        "[GPS REDACTED]",
        text,
    )

    # Email addresses
    text = re.sub(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        "[EMAIL REDACTED]",
        text,
    )

    # 12-digit Aadhaar-style IDs (with optional spaces/dashes between groups)
    text = re.sub(
        r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",
        "[ID REDACTED]",
        text,
    )

    # Phone numbers — 10 or more digits (may contain spaces, dashes, dots)
    text = re.sub(
        r"(?:\+?\d[\d\s\-\.]{8,}\d)",
        "[PHONE REDACTED]",
        text,
    )

    return text


def _contains_injection(text: str) -> bool:
    """Return True if *text* contains any prompt-injection keyword."""
    lowered = text.lower()
    return any(kw in lowered for kw in _INJECTION_KEYWORDS)


def ingest_report(ctx, node_input: Any = None) -> RiskState:
    """Parse incoming report data with security screening.

    Acts as the first line of defense:
      1. Extract the raw string payload from node_input.
      2. Prompt-injection check — flag and short-circuit if suspicious.
      3. PII redaction — scrub sensitive data before it enters state.
      4. Parse animal / location from the *redacted* text.
    """
    state = ctx.state

    # --- Extract raw payload ------------------------------------------------
    raw = node_input
    if raw is not None:
        raw = getattr(raw, "content", raw)

    # Build a flat string representation for security scanning
    raw_text = ""
    if isinstance(raw, dict):
        raw_text = json.dumps(raw)
    elif isinstance(raw, str):
        raw_text = raw

    # --- 1. Prompt-injection check ------------------------------------------
    if raw_text and _contains_injection(raw_text):
        base = state.to_dict() if hasattr(state, "to_dict") else {}
        return {
            **base,
            "animal": "blocked",
            "location": "blocked",
            "is_safe": False,
            "recommended_action": "Report blocked — suspected prompt injection.",
        }

    # --- 2. PII redaction ---------------------------------------------------
    if raw_text:
        raw_text = redact_pii(raw_text)

    # --- 3. Parse structured data from the (now-redacted) payload -----------
    parsed_data = {}
    if isinstance(raw, dict):
        # Re-parse from redacted JSON so PII is scrubbed in stored values
        try:
            parsed_data = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed_data = raw  # fall back to original dict
    elif isinstance(raw, str):
        try:
            parsed_data = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed_data = {}

    # Fallback: if nothing was parsed from node_input, try extracting from state
    if not parsed_data:
        parsed_data = state.to_dict() if hasattr(state, "to_dict") else {}

    # Safely extract with safe defaults — never return None or empty values
    parsed_animal = str(parsed_data.get("animal", "") or "").strip().lower()
    parsed_location = str(parsed_data.get("location", "") or "").strip().lower()

    if not parsed_animal:
        parsed_animal = "elephant"
    if not parsed_location:
        parsed_location = "sector 9"

    # Return merged state dict — ADK merges this back into ctx.state
    base = state.to_dict() if hasattr(state, "to_dict") else {}
    return {**base, "animal": parsed_animal, "location": parsed_location, "is_safe": True}


def evaluate_report(ctx) -> RiskState:
    """Evaluate risk level based on animal type and fetch weather.

    If the ingest stage flagged the report as unsafe (is_safe == False),
    the report is immediately routed to a Blocked / Low-risk state so
    it never reaches the high-risk review path.
    """
    state = ctx.state

    # Security gate — block unsafe reports from proceeding
    if state.get("is_safe") is False:
        base = state.to_dict() if hasattr(state, "to_dict") else {}
        return {
            **base,
            "risk_level": "Blocked",
            "weather": "N/A",
            "recommended_action": state.get(
                "recommended_action",
                "Report blocked by security screen.",
            ),
        }

    animal = state.get("animal", "elephant").lower().strip()
    risk = "High" if "elephant" in animal or "tiger" in animal else "Low"
    weather = get_weather(state.get("location", "sector 9"))
    base = state.to_dict() if hasattr(state, "to_dict") else {}
    return {**base, "risk_level": risk, "weather": weather}


def route_risk(ctx) -> str:
    """Route to HIGH_RISK or LOW_RISK based on the evaluated risk level."""
    state = ctx.state
    return "HIGH_RISK" if state.get("risk_level") == "High" else "LOW_RISK"


def auto_advise(ctx) -> RiskState:
    """Generate an automatic advisory for low-risk encounters."""
    state = ctx.state
    recommended_action = f"Low risk alert. Weather: {state.get('weather', 'N/A')}. Stay safe."
    base = state.to_dict() if hasattr(state, "to_dict") else {}
    return {**base, "recommended_action": recommended_action}


def review_agent(ctx):
    """High-risk path: fetch wildlife advice, then pause for human review."""
    state = ctx.state
    animal = state.get("animal", "unknown")
    location = state.get("location", "unknown")
    weather = state.get("weather", "unknown")

    # Call the MCP server tool function directly (non-blocking, sync call)
    from .mcp_server import get_wildlife_advice
    try:
        advice = get_wildlife_advice(animal)
    except Exception:
        advice = "No advice available"

    msg = (
        f"HIGH-RISK ALERT: {animal} spotted at {location}. "
        f"Weather: {weather}. Advice: {advice}"
    )

    # Pause for human approval — Forest Officer reviews the enriched message
    base = state.to_dict() if hasattr(state, "to_dict") else {}
    decision = yield RequestInput(message=msg, payload=base)

    new_state = {**base, "recommended_action": f"Review Required. Advice: {advice}"}
    if decision:
        new_state["officer_decision"] = str(
            getattr(decision, "content", decision)
        )

    return new_state


# ---------------------------------------------------------------------------
# Workflow — dict-based conditional routing
# ---------------------------------------------------------------------------
root_agent = Workflow(
    name="root_agent",
    edges=[
        ("START", ingest_report),
        (ingest_report, evaluate_report),
        (evaluate_report, route_risk, {
            "LOW_RISK": auto_advise,
            "HIGH_RISK": review_agent,
        }),
    ],
    tools=[get_weather],
)

app = App(root_agent=root_agent, name="app")