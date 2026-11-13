import json
import os
import sys

from pathlib import Path

TRACKER_PATH = Path(__file__).resolve().parent.parent / ".pii_review_tracker.json"

def load_tracker():
    with open(TRACKER_PATH, "r") as f:
        return json.load(f)

def save_tracker(data):
    with open(TRACKER_PATH, "w") as f:
        json.dump(data, f, indent=2)

def get_next_batch(count=10):
    data = load_tracker()
    files = data["files"]
    pending = [path for path, info in files.items() if info["status"] == "pending"]
    return pending[:count]

def mark_in_progress(file_path, agent_id):
    data = load_tracker()
    if file_path in data["files"]:
        data["files"][file_path]["status"] = "in_progress"
        data["files"][file_path]["agent_id"] = agent_id
        save_tracker(data)

def update_file_result(file_path, pii_found, findings):
    data = load_tracker()
    if file_path in data["files"]:
        data["files"][file_path]["status"] = "completed"
        data["files"][file_path]["pii_found"] = pii_found
        data["files"][file_path]["findings"] = findings
        data["completed_count"] = sum(1 for f in data["files"].values() if f["status"] == "completed")
        data["pii_count"] = sum(1 for f in data["files"].values() if f.get("pii_found", False))
        save_tracker(data)

def get_summary():
    data = load_tracker()
    total = data["total"]
    completed = data["completed_count"]
    pii_count = data["pii_count"]
    in_progress = sum(1 for f in data["files"].values() if f["status"] == "in_progress")
    pending = sum(1 for f in data["files"].values() if f["status"] == "pending")
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "pii_count": pii_count
    }

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "next":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        print(json.dumps(get_next_batch(n)))
    elif cmd == "summary":
        print(json.dumps(get_summary(), indent=2))
