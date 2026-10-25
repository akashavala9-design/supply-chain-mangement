import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT / "data" / "curated" / "curated_shipments.csv"
LOG_FILE = PROJECT / "reports" / "assistant_logs.jsonl"
MAX_TOOL_CALLS = 3


def log_event(event):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": datetime.now(UTC).isoformat(), **event}
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def load_data():
    return pd.read_csv(DATA_FILE)


def query_shipments(filters=None):
    """Read curated shipments; optional origin, destination, status filters."""
    filters = filters or {}
    df = load_data()
    columns = {
        "origin": "origin_port",
        "destination": "destination_port",
        "status": "status",
    }
    for key, column in columns.items():
        value = filters.get(key)
        if value and column in df.columns:
            df = df[df[column].astype(str).str.upper() == str(value).upper()]
    result = {
        "total_matching": len(df),
        "returned": int(min(len(df), 10)),
        "items": df.head(10).where(pd.notna(df.head(10)), None).to_dict("records"),
    }
    log_event({"type": "tool_response", "tool": "query_shipments",
               "input": filters, "response": result})
    return result




def resolve_port_code(value):
    """Resolve a port name or code to its canonical port code."""
    ports_path = Path(__file__).resolve().parents[1] / "data" / "raw" / "ports.csv"
    ports = pd.read_csv(ports_path)

    value = str(value).strip()
    code_match = ports[
        ports["port_code"].astype(str).str.strip().str.casefold()
        == value.casefold()
    ]
    if not code_match.empty:
        return str(code_match.iloc[0]["port_code"]).strip()

    name_match = ports[
        ports["port_name"].astype(str).str.strip().str.casefold()
        == value.casefold()
    ]
    if not name_match.empty:
        return str(name_match.iloc[0]["port_code"]).strip()

    return value.upper()

def get_route_stats(origin, destination):
    """Aggregate shipment count, average delay hours, and on-time rate."""
    df = load_data()
    required = {"origin_port", "destination_port", "actual_delay_hours"}
    if not required.issubset(df.columns):
        raise ValueError(f"Curated data missing columns: {sorted(required - set(df.columns))}")

    origin_code = resolve_port_code(origin)
    destination_code = resolve_port_code(destination)

    route = df[
        df["origin_port"].astype(str).str.strip().str.upper().eq(origin_code)
        & df["destination_port"].astype(str).str.strip().str.upper().eq(destination_code)
    ].copy()

    delays = pd.to_numeric(route["actual_delay_hours"], errors="coerce")
    observed = delays.notna()
    result = {
        "origin": origin_code,
        "destination": destination_code,
        "shipment_count": len(route),
        "shipments_with_observed_delay": int(observed.sum()),
        "average_delay_hours": round(float(delays[observed].mean()), 2)
            if observed.any() else None,
        "on_time_rate_pct": round(float((delays[observed] <= 24).mean() * 100), 2)
            if observed.any() else None,
        "on_time_definition": "actual_delay_hours <= 24",
        "source_tool": "get_route_stats",
    }
    log_event({"type": "tool_response", "tool": "get_route_stats",
               "input": {"origin": origin, "destination": destination},
               "response": result})
    return result


def predict_delay(shipment_id):
    """Call the project's ML prediction API endpoint."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/predict-delay", json={"shipment_id": shipment_id}
        )
    result = {"http_status": response.status_code, "response": response.json()}
    log_event({"type": "tool_response", "tool": "predict_delay",
               "input": {"shipment_id": shipment_id}, "response": result})
    if response.status_code != 200:
        raise ValueError(json.dumps(result, default=str))
    return result["response"]


def top_delayed_routes(start_date, end_date):
    """Rank routes by average observed delay within an arrival-date window."""
    df = load_data()
    required = {
        "origin_port", "destination_port", "actual_delay_hours", "actual_arrival"
    }
    if not required.issubset(df.columns):
        raise ValueError(f"Curated data missing columns: {sorted(required - set(df.columns))}")

    df["actual_arrival"] = pd.to_datetime(df["actual_arrival"], errors="coerce")
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    window = df[
        df["actual_arrival"].ge(start)
        & df["actual_arrival"].lt(end + pd.Timedelta(days=1))
    ].copy()
    window["actual_delay_hours"] = pd.to_numeric(
        window["actual_delay_hours"], errors="coerce"
    )
    window = window.dropna(subset=["actual_delay_hours"])
    grouped = window.groupby(["origin_port", "destination_port"]).agg(
        shipment_count=("actual_delay_hours", "size"),
        average_delay_hours=("actual_delay_hours", "mean"),
        on_time_rate_pct=("actual_delay_hours", lambda s: (s <= 24).mean() * 100),
    ).reset_index().sort_values("average_delay_hours", ascending=False).head(10)

    result = {
        "date_window": {"start": start_date, "end": end_date},
        "ranking_basis": "average observed actual_delay_hours; only rows with actual arrival",
        "routes": grouped.round(2).to_dict("records"),
        "source_tool": "top_delayed_routes",
    }
    log_event({"type": "tool_response", "tool": "top_delayed_routes",
               "input": {"start_date": start_date, "end_date": end_date},
               "response": result})
    return result


TOOLS = {
    "query_shipments": query_shipments,
    "get_route_stats": get_route_stats,
    "predict_delay": predict_delay,
    "top_delayed_routes": top_delayed_routes,
}


def in_scope(prompt):
    terms = {
        "shipment", "shipments", "route", "routes", "delay", "late",
        "arrival", "port", "status", "origin", "destination", "predict",
        "prediction", "on-time", "ontime", "cargo", "supply", "delivery",
        "quarter", "quarterly", "risk"
    }
    words = set("".join(c.lower() if c.isalnum() else " " for c in prompt).split())
    return bool(words & terms)


def local_answer(prompt):
    """Deterministic, no-key tool demo; this is not an LLM."""
    log_event({"type": "user_prompt", "mode": "local", "prompt": prompt})
    if not in_scope(prompt):
        answer = "I can only answer supply-chain shipment, route, port, and delay questions."
        log_event({"type": "final_output", "mode": "local", "answer": answer})
        return answer

    # This local demo uses simple patterns. Real tool selection is done by the LLM mode.
    words = prompt.replace("?", "").replace(",", " ").split()
    upper = [w.upper() for w in words]
    try:
        if "PREDICT" in upper or "RISK" in upper:
            sid = next((w for w in words if w.upper().startswith("SHP-")), None)
            log_event({
                "type": "tool_call",
                "mode": "local",
                "tool": "predict_delay",
                "input": {"shipment_id": sid},
            })
            if not sid:
                answer = "Please include a shipment ID, for example SHP-00421."
            else:
                answer = json.dumps(predict_delay(sid), indent=2, default=str)
        elif "ROUTE" in upper and ("SHANGHAI" in upper or "ROTTERDAM" in upper):
            origin = "SHANGHAI" if "SHANGHAI" in upper else None
            destination = "ROTTERDAM" if "ROTTERDAM" in upper else None
            log_event({
                "type": "tool_call",
                "mode": "local",
                "tool": "get_route_stats",
                "input": {"origin": origin, "destination": destination},
            })
            answer = json.dumps(get_route_stats(origin, destination), indent=2) if origin and destination else "Please provide both port codes."
        elif "QUARTER" in upper or "QUARTERLY" in upper or "HIGHEST" in upper:
            now = pd.Timestamp.now().normalize()
            quarter_start_month = ((now.month - 1) // 3) * 3 + 1
            start = pd.Timestamp(year=now.year, month=quarter_start_month, day=1)
            tool_input = {
                "start_date": start.date().isoformat(),
                "end_date": now.date().isoformat(),
            }
            log_event({
                "type": "tool_call",
                "mode": "local",
                "tool": "top_delayed_routes",
                "input": tool_input,
            })
            answer = json.dumps(
                top_delayed_routes(**tool_input),
                indent=2,
                default=str,
            )
        else:
            filters = {}
            for key in ("origin", "destination", "status"):
                if key.upper() in upper:
                    idx = upper.index(key.upper())
                    if idx + 1 < len(words):
                        filters[key] = words[idx + 1]
            log_event({
                "type": "tool_call",
                "mode": "local",
                "tool": "query_shipments",
                "input": filters,
            })
            answer = json.dumps(query_shipments(filters), indent=2, default=str)

        log_event({"type": "final_output", "mode": "local",
                   "answer": answer, "evidence": "tool response"})
        return answer
    except Exception as exc:  # noqa: BLE001
        log_event({"type": "assistant_error", "mode": "local", "error": str(exc)})
        return f"Tool error: {exc}"


def openai_answer(prompt):
    """Real LLM tool calling. Requires OPENAI_API_KEY and optional openai package."""
    if not os.getenv("OPENAI_API_KEY"):
        return "LLM mode unavailable: OPENAI_API_KEY is not set. Use local_answer() to test tools."

    try:
        from openai import OpenAI
    except ImportError:
        return "LLM mode unavailable: install the optional 'openai' package."

    log_event({"type": "user_prompt", "mode": "openai", "prompt": prompt})
    if not in_scope(prompt):
        answer = "I can only answer supply-chain shipment, route, port, and delay questions."
        log_event({"type": "final_output", "mode": "openai", "answer": answer})
        return answer

    definitions = [
        ("query_shipments", "Query curated shipments with optional filters.",
         {"type": "object", "properties": {"filters": {"type": "object",
          "properties": {"origin": {"type": "string"}, "destination": {"type": "string"},
                         "status": {"type": "string"}}, "additionalProperties": False}},
          "required": ["filters"], "additionalProperties": False}),
        ("get_route_stats", "Get delay and on-time metrics for an origin/destination route.",
         {"type": "object", "properties": {"origin": {"type": "string"},
          "destination": {"type": "string"}}, "required": ["origin", "destination"],
          "additionalProperties": False}),
        ("predict_delay", "Call the ML endpoint for a shipment delay prediction.",
         {"type": "object", "properties": {"shipment_id": {"type": "string"}},
          "required": ["shipment_id"], "additionalProperties": False}),
        ("top_delayed_routes", "Rank routes by average observed delay in a date window.",
         {"type": "object", "properties": {"start_date": {"type": "string"},
          "end_date": {"type": "string"}}, "required": ["start_date", "end_date"],
          "additionalProperties": False}),
    ]
    tools = [{"type": "function", "function": {
        "name": name, "description": description, "parameters": schema
    }} for name, description, schema in definitions]

    from openai import OpenAI
    client = OpenAI()
    messages = [
        {"role": "system", "content":
         "You are a supply-chain assistant. Use tools for factual shipment data. "
         "Never invent metrics. Cite the tool name for factual claims. "
         "For quarter questions, determine the current calendar quarter dates and call "
         "top_delayed_routes. Predictions are estimates, not guarantees."},
        {"role": "user", "content": prompt},
    ]

    tool_calls_used = 0
    for _ in range(MAX_TOOL_CALLS + 1):
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=messages, tools=tools, tool_choice="auto"
        )
        msg = response.choices[0].message
        log_event({"type": "llm_response", "mode": "openai",
                   "tool_calls": [c.model_dump() for c in (msg.tool_calls or [])],
                   "content": msg.content})
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            answer = msg.content or "No answer returned."
            log_event({"type": "final_output", "mode": "openai", "answer": answer})
            return answer

        for call in msg.tool_calls:
            if tool_calls_used >= MAX_TOOL_CALLS:
                answer = "Tool-call limit reached. Please narrow your question."
                log_event({"type": "final_output", "mode": "openai", "answer": answer})
                return answer
            tool_calls_used += 1
            name = call.function.name
            try:
                args = json.loads(call.function.arguments)
                log_event({"type": "tool_call", "tool": name, "input": args})
                if name not in TOOLS:
                    raise ValueError("Unknown tool")
                result = TOOLS[name](**args)
                content = json.dumps(result, default=str)
                log_event({
                    "type": "tool_response",
                    "mode": "openai",
                    "tool": name,
                    "input": args,
                    "response": result,
                })
            except Exception as exc:  # noqa: BLE001
                content = json.dumps({"error": str(exc)})
                log_event({
                    "type": "tool_response",
                    "mode": "openai",
                    "tool": name,
                    "input": locals().get("args", {}),
                    "error": str(exc),
                })
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})

    answer = "Tool-call limit reached. Please narrow your question."
    log_event({"type": "final_output", "mode": "openai", "answer": answer})
    return answer


if __name__ == "__main__":
    print("Supply Chain Assistant (local mode; no API key needed).")
    print("Try: predict shipment SHP-00421")
    print("Type exit to quit.")
    while True:
        prompt = input("\\nYou: ").strip()
        if prompt.lower() in {"exit", "quit"}:
            break
        print(local_answer(prompt))
