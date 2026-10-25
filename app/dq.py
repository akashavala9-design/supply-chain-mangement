from pathlib import Path
import json
import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
RAW = PROJECT / "data" / "raw"
REPORT_PATH = PROJECT / "reports" / "data_quality_report.json"

def run_checks():
    shipments = pd.read_csv(RAW / "shipments.csv")
    ports = pd.read_csv(RAW / "ports.csv")
    events = pd.read_csv(RAW / "port_events.csv")
    issues = []

    def add(dataset, name, affected, total, severity, action):
        affected, total = int(affected), int(total)
        issues.append({
            "dataset": dataset,
            "issue": name,
            "rows_affected": affected,
            "percent_total": round(100 * affected / total, 2) if total else 0,
            "severity": severity,
            "recommended_action": action
        })

    def missing(df, col):
        return int(df[col].isna().sum()) if col in df else len(df)

    def nonpositive(df, col):
        if col not in df:
            return 0
        x = pd.to_numeric(df[col], errors="coerce")
        return int((x.notna() & (x <= 0)).sum())

    n = len(shipments)
    if "shipment_id" in shipments:
        add("shipments", "Missing shipment ID", missing(shipments, "shipment_id"),
            n, "critical", "Quarantine records without a shipment ID.")
        add("shipments", "Duplicate shipment IDs",
            shipments["shipment_id"].duplicated(keep=False).sum(),
            n, "warning", "Compare duplicate records; merge compatible rows and quarantine conflicts.")
    else:
        add("shipments", "Shipment ID column missing", n, n, "critical",
            "Verify the source schema.")

    for col in ["origin_port", "destination_port", "planned_arrival",
                "actual_arrival", "weight_tons", "container_count", "status"]:
        severity = "warning" if col in ["actual_arrival", "status"] else "critical"
        add("shipments", f"Missing {col}", missing(shipments, col), n, severity,
            f"Investigate missing {col}; do not silently invent values.")

    for col in ["weight_tons", "container_count"]:
        add("shipments", f"Non-positive {col}", nonpositive(shipments, col), n,
            "critical", f"Quarantine records where {col} is zero or negative.")

    if "status" in shipments:
        allowed = {"DELIVERED", "DELAYED", "CANCELLED", "COMPLETED"}
        status = shipments["status"].astype("string").str.strip().str.upper()
        bad = status.notna() & ~status.isin(allowed)
        add("shipments", "Unknown or non-standard shipment status", bad.sum(), n,
            "warning", "Normalize approved status values and investigate unexpected values.")

    if "port_code" in ports:
        known = set(ports["port_code"].dropna().astype(str).str.strip())
        for col in ["origin_port", "destination_port"]:
            if col in shipments:
                values = shipments[col].astype("string").str.strip()
                bad = values.notna() & ~values.isin(known)
                add("shipments", f"Unknown {col} code", bad.sum(), n, "critical",
                    "Check the source code against the authoritative port reference.")
    else:
        add("ports", "Port code column missing", len(ports), len(ports), "critical",
            "Verify the port reference schema.")

    if {"planned_arrival", "actual_arrival"}.issubset(shipments.columns):
        planned = pd.to_datetime(shipments["planned_arrival"], errors="coerce", utc=True)
        actual = pd.to_datetime(shipments["actual_arrival"], errors="coerce", utc=True)
        # Anomaly only: early arrival is not automatically invalid.
        early = planned.notna() & actual.notna() & (actual < planned)
        add("shipments", "Actual arrival earlier than planned arrival",
            early.sum(), n, "info",
            "Review as an early-arrival anomaly; do not automatically quarantine.")

    p = len(ports)
    if "port_code" in ports:
        add("ports", "Missing port code", missing(ports, "port_code"), p, "critical",
            "Repair or quarantine reference records without a code.")
        add("ports", "Duplicate port codes",
            ports["port_code"].duplicated(keep=False).sum(), p, "warning",
            "Resolve duplicate reference keys before joining.")
    add("ports", "Missing country", missing(ports, "country"), p, "warning",
        "Complete country from an authoritative reference source.")

    e = len(events)
    for col in ["event_type", "notes"]:
        add("port_events", f"Missing {col}", missing(events, col), e, "warning",
            f"Check whether {col} is required; quarantine only if required by the contract.")

    for col in ["event_id", "port_event_id"]:
        if col in events:
            add("port_events", f"Duplicate {col}",
                events[col].duplicated(keep=False).sum(), e, "warning",
                "Investigate repeated IDs and make ingestion idempotent.")
            break

    report = {
        "report_name": "Supply Chain Data Quality Report",
        "version": "1.0.0",
        "datasets": {
            "shipments": {"rows_checked": len(shipments)},
            "ports": {"rows_checked": len(ports)},
            "port_events": {"rows_checked": len(events)}
        },
        "total_checks": len(issues),
        "issues": issues
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    return report

if __name__ == "__main__":
    result = run_checks()
    print(f"Data-quality checks completed: {result['total_checks']} checks")
    print(f"JSON report saved to: {REPORT_PATH}")
    print(json.dumps(result, indent=2))
