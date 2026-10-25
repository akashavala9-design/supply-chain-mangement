import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]

from app import assistant


def test_query_shipments_returns_structured_result():
    result = assistant.query_shipments({})

    assert isinstance(result, dict)
    assert "total_matching" in result
    assert "items" in result
    assert isinstance(result["items"], list)
    assert result["total_matching"] >= 0


def test_get_route_stats_returns_structured_result():
    df = assistant.load_data()

    assert not df.empty, "Curated shipment dataset is empty."

    row = df.iloc[0]
    result = assistant.get_route_stats(
        str(row["origin_port"]),
        str(row["destination_port"]),
    )

    assert isinstance(result, dict)
    assert result["source_tool"] == "get_route_stats"
    assert result["origin"] == str(row["origin_port"])
    assert result["destination"] == str(row["destination_port"])
    assert result["shipment_count"] >= 0
    assert result["shipments_with_observed_delay"] >= 0
    assert "average_delay_hours" in result
    assert "on_time_rate_pct" in result
    assert result["on_time_definition"] == "actual_delay_hours <= 24"


def test_predict_delay_returns_prediction():
    result = assistant.predict_delay("SHP-00001")

    assert isinstance(result, dict)
    assert result.get("shipment_id") == "SHP-00001"


def test_off_topic_prompt_is_rejected():
    prompt = "Tell me a joke about cats"

    assert assistant.in_scope(prompt) is False


def test_assistant_logs_are_valid_json_lines():
    log_path = (
        PROJECT / "reports" / "assistant_logs.jsonl"
    )

    assert log_path.exists(), "Assistant log file does not exist."

    lines = [
        line for line in log_path.read_text().splitlines()
        if line.strip()
    ]
    assert lines, "Assistant log file is empty."

    for line in lines:
        event = json.loads(line)
        assert isinstance(event, dict)
        assert "type" in event
        assert "timestamp" in event
