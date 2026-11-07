#!/usr/bin/env python3
"""Trivial baseline: shows the input layout and the prediction format, nothing more.

    python baseline.py travel-request/dev > predictions.jsonl
    python evaluate.py travel-request/dev/ground-truth.jsonl predictions.jsonl

Travel requests: takes the traveller's name from the message header, leaves every other field
empty, asks for nothing, approves. Expense claims: refunds nothing. Teaching: grants a withdrawal.
"""
import json
import os
import re
import sys

folder = sys.argv[1].rstrip("/")
scenario = os.path.basename(os.path.dirname(folder))
inputs = os.path.join(folder, "inputs")
for case in sorted(os.listdir(inputs)):
    if scenario == "travel-request":
        with open(os.path.join(inputs, case, "message.txt"), encoding="utf-8") as fh:
            name = re.match(r"From: (.*?) <", fh.read()).group(1)
        form = {"traveler_name": name, "third_party": []}
        row = {"case_id": case, "form": form, "missing": [], "decision": "approve", "rule": None}
    elif scenario == "expense-claim":
        row = {"case_id": case, "transport": 0, "accommodation": 0, "registration": 0,
               "per_diem": 0, "other": 0, "total": 0}
    else:
        row = {"case_id": case, "request_type": "exam_withdrawal", "decision": "grant", "key_value": None}
    print(json.dumps(row, ensure_ascii=False))
