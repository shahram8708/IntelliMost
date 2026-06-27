import os
import json
import re

VALID_INDICES = [0, 1, 3, 6, 10, 16, 24, 32]

try:
    from google import genai
    from google.genai import types
    _client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY")) if os.environ.get("GEMINI_API_KEY") else None
except Exception:
    genai = None
    types = None
    _client = None


def _model_call(prompt):
    if not _client or not types:
        raise RuntimeError("Gemini client unavailable")
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])
    response = _client.models.generate_content(
        model="gemini-2.5-flash", contents=prompt, config=config
    )
    return response.text.strip()


def suggest_most_indices(element_name, element_description, timer_duration_sec=None):
    dur = f"Observed Duration: {timer_duration_sec:.1f} seconds" if timer_duration_sec else ""
    prompt = f"""You are an expert MOST (Maynard Operation Sequence Technique) industrial engineer.

Analyze this work element and suggest the appropriate MOST method and index values:

Element Name: {element_name}
Description: {element_description}
{dur}

MOST Methods:
1. General Move (A-B-G-A-B-P-A): freely moving objects through space
2. Controlled Move (A-B-G-M-X-I-A): moving objects while maintaining contact with a surface
3. Tool Use (A-B-G-A-B-P-A + tool): using tools/equipment

Index Values available: 0, 1, 3, 6, 10, 16, 24, 32

Return ONLY a valid JSON object (no markdown):
{{"method": "general_move|controlled_move|tool_use",
"index_values": {{"A1": int, "B1": int, "G1": int, "A2": int, "B2": int, "P1": int, "A3": int}},
"confidence": float_between_0_and_1, "reasoning": "brief explanation"}}

For controlled_move use: {{"A1": int, "B1": int, "G1": int, "M1": int, "X1": int, "I1": int, "A2": int}}"""
    try:
        text = _model_call(prompt)
        text = re.sub(r"```json\s*|\s*```", "", text)
        result = json.loads(text)
        for k, v in list(result.get("index_values", {}).items()):
            if v not in VALID_INDICES:
                result["index_values"][k] = min(VALID_INDICES, key=lambda x: abs(x - v))
        return result
    except Exception:
        return _rule_based_suggestion(element_name, element_description, timer_duration_sec)


def _rule_based_suggestion(name, description, duration_sec=None):
    combined = (name + " " + (description or "")).lower()
    controlled_kw = ["push", "turn", "rotate", "guide", "slide", "crank", "lever", "press", "feed"]
    tool_kw = ["tool", "wrench", "measure", "tighten", "screw", "cut", "drill", "instrument"]
    if any(k in combined for k in tool_kw):
        method = "tool_use"
    elif any(k in combined for k in controlled_kw):
        method = "controlled_move"
    else:
        method = "general_move"
    if duration_sec:
        per_param = (duration_sec / 0.036) / 7
        closest = min(VALID_INDICES, key=lambda x: abs(x - per_param))
    else:
        closest = 3
    if method == "general_move":
        idx = {"A1": 1, "B1": 0, "G1": closest, "A2": 1, "B2": 0, "P1": closest, "A3": 0}
    elif method == "controlled_move":
        idx = {"A1": 1, "B1": 0, "G1": 1, "M1": closest, "X1": 0, "I1": 0, "A2": 1}
    else:
        idx = {"A1": 1, "B1": 0, "G1": 1, "A2": 1, "B2": 0, "P1": closest, "A3": 0}
    return {"method": method, "index_values": idx,
            "confidence": 0.55 if duration_sec else 0.4,
            "reasoning": "Rule-based suggestion from keyword analysis"}


def generate_improvement_suggestion_text(opportunity_title, evidence_data):
    prompt = f"""You are an industrial engineering expert in pharmaceutical and process manufacturing.
Generate a concise improvement suggestion based on:
Opportunity: {opportunity_title}
Evidence: {evidence_data}
Write 2-3 sentences: what the data shows, the specific action, expected benefit. Under 100 words."""
    try:
        return _model_call(prompt)
    except Exception:
        return (f"Analysis indicates an opportunity for improvement in {opportunity_title}. "
                "Review the supporting data and assign a responsible industrial engineer for investigation.")


def analyze_root_cause_context(problem_statement, machine_type, deviation_type):
    prompt = f"""You are a pharmaceutical manufacturing quality expert assisting with root cause analysis.
Problem: {problem_statement}
Machine Type: {machine_type}
Deviation Type: {deviation_type}
Suggest 3 probable root cause hypotheses using the 6M framework.
Return ONLY a JSON array:
[{{"category": "Machine|Man|Method|Material|Measurement|Environment", "hypothesis": "text", "probability": "high|medium|low"}}]"""
    try:
        text = re.sub(r"```json\s*|\s*```", "", _model_call(prompt))
        return json.loads(text)
    except Exception:
        return [
            {"category": "Machine", "hypothesis": "Equipment malfunction or wear", "probability": "medium"},
            {"category": "Method", "hypothesis": "Process deviation from SOP", "probability": "medium"},
            {"category": "Man", "hypothesis": "Operator error or training gap", "probability": "low"},
        ]
