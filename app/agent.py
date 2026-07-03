import os
import re
from typing import Any
from google.adk.events import RequestInput
from google.adk import Workflow
from google.adk.apps import App
from .tools import get_weather

os.environ["GOOGLE_CLOUD_PROJECT"] = "demo-project"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

def redact_pii(text: str) -> str:
    text = re.sub(r"\d{10,}", "[PHONE REDACTED]", text)
    text = re.sub(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[EMAIL REDACTED]", text)
    return text


def _extract_user_text(ctx, _input: Any = None) -> str:
    """Extract user text from every possible ADK source.

    ADK Workflow passes user messages through multiple pathways depending on
    version and node position.  We try them all to guarantee extraction.
    """
    candidates: list[str] = []

    # 1. Try the _input parameter (may be str, dict, or event object)
    if _input is not None:
        if isinstance(_input, str):
            candidates.append(_input)
        elif isinstance(_input, dict):
            for key in ('text', 'message', 'content', 'query'):
                if key in _input:
                    candidates.append(str(_input[key]))
        else:
            # ADK event objects — try common attribute names
            for attr in ('text', 'message', 'content', 'query', 'data'):
                val = getattr(_input, attr, None)
                if val is not None:
                    candidates.append(str(val))
            # Last resort: stringify the whole object
            if not candidates:
                candidates.append(str(_input))

    # 2. Try ctx.user_content (ADK >=2.x stores the latest user turn here)
    user_content = getattr(ctx, 'user_content', None)
    if user_content is not None:
        if isinstance(user_content, str):
            candidates.append(user_content)
        else:
            for attr in ('text', 'message', 'content'):
                val = getattr(user_content, attr, None)
                if val is not None:
                    candidates.append(str(val))
            if not any(getattr(user_content, a, None) for a in ('text', 'message', 'content')):
                candidates.append(str(user_content))

    # 3. Try session state / metadata (displayName is set by the Dev UI)
    state_dict = ctx.state.to_dict() if hasattr(ctx.state, 'to_dict') else (ctx.state or {})
    meta = state_dict.get('__session_metadata__', {})
    if isinstance(meta, dict):
        display = meta.get('displayName', '')
        if display:
            candidates.append(str(display))

    # 4. Merge everything into one searchable string
    return ' '.join(candidates).strip()


def ingest_report(ctx, _input: Any = None) -> dict:
    state = ctx.state.to_dict() if hasattr(ctx.state, 'to_dict') else (ctx.state or {})

    raw_text = _extract_user_text(ctx, _input)
    text = raw_text.lower()
    clean_text = redact_pii(text)

    # Keyword matching
    animal = 'unknown'
    if 'elephant' in clean_text or 'tiger' in clean_text:
        animal = 'elephant'  # both are high risk
    elif 'snake' in clean_text or 'monkey' in clean_text:
        animal = 'snake'  # low risk

    return {**state, 'animal': animal, 'location': 'sector 9', 'is_safe': True}


def evaluate_report(ctx) -> dict:
    state = ctx.state.to_dict() if hasattr(ctx.state, 'to_dict') else (ctx.state or {})
    animal = state.get('animal', 'unknown')
    risk = 'HIGH_RISK' if animal in ['elephant', 'tiger'] else 'LOW_RISK'
    weather = get_weather(state.get('location', 'sector 9'))
    return {**state, 'risk_level': risk, 'weather': weather}


def route_risk(ctx) -> str:
    """Return the routing key.  MUST match the edge dictionary keys exactly."""
    state = ctx.state.to_dict() if hasattr(ctx.state, 'to_dict') else (ctx.state or {})
    return state.get('risk_level', 'LOW_RISK')


def auto_advise(ctx) -> dict:
    state = ctx.state.to_dict() if hasattr(ctx.state, 'to_dict') else (ctx.state or {})
    return {**state, 'recommended_action': f"Low risk alert. Weather: {state.get('weather')}"}


def review_agent(ctx):
    state = ctx.state.to_dict() if hasattr(ctx.state, 'to_dict') else (ctx.state or {})
    from .mcp_server import get_wildlife_advice
    advice = get_wildlife_advice(state.get('animal', 'elephant'))
    msg = f"HIGH-RISK ALERT: {state.get('animal')} spotted. Advice: {advice}"

    decision = yield RequestInput(message=msg, payload=state)
    return {**state, 'officer_decision': str(getattr(decision, 'content', decision))}


root_agent = Workflow(
    name="root_agent",
    edges=[
        ("START", ingest_report),
        (ingest_report, evaluate_report),
        (evaluate_report, route_risk, {
            "HIGH_RISK": review_agent,
            "LOW_RISK": auto_advise,
        }),
    ],
    tools=[get_weather],
)

app = App(root_agent=root_agent, name="app")