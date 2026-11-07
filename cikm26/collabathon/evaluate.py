#!/usr/bin/env python3
"""Score predictions for the UniAgent collabathon data against the ground truth.

    python evaluate.py travel-request/dev/ground-truth.jsonl predictions.jsonl
    python evaluate.py expense-claim/test/ground-truth.jsonl predictions.jsonl --details

The scenario (travel-request, expense-claim, teaching) is recognised from the ground truth.
Prints one JSON object with the scores; --details adds every wrong value per case. A case
without a prediction counts as wrong in every field. Standard library only.
"""
import argparse
import json
import re
import sys
import unicodedata

STOP = {"a", "an", "and", "at", "for", "in", "of", "on", "the", "to"}
ALIAS = {"munchen": "munich", "koln": "cologne"}
FORM = {"traveler_name": "text", "position": "text", "trip_type": "exact",
        "destination_city": "text", "destination_country": "text", "purpose": "text",
        "departure_date": "exact", "return_date": "exact", "transport": "exact",
        "cost_centre": "code", "private_stay_start": "exact", "private_stay_end": "exact",
        "third_party": "set", "cost_transport": "money", "cost_accommodation": "money",
        "cost_registration": "money", "cost_total": "money"}
CLAIM = ("transport", "accommodation", "registration", "per_diem", "other", "total")


def load(path):
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return {r["case_id"]: r for r in rows}


def empty(v):
    return v is None or v == "" or v == []


def words(v):
    v = unicodedata.normalize("NFKD", str(v).casefold().replace("ß", "ss"))
    v = "".join(ch for ch in v if not unicodedata.combining(ch))
    return {ALIAS.get(w, w) for w in re.findall(r"\w+", v) if w not in STOP}


def same(kind, gold, pred):
    """Is pred right? text: every word of the gold value occurs in pred; money: to the cent;
    code: equal ignoring spaces and punctuation; set: equal as sets; exact: equal ignoring case."""
    if empty(gold):
        return empty(pred)
    if empty(pred):
        return False
    if kind == "text":
        return words(gold) <= words(pred)
    if kind == "money":
        try:
            return abs(float(pred) - float(gold)) <= 0.0101
        except (TypeError, ValueError):
            return False
    if kind == "code":
        return re.sub(r"\W", "", str(pred)) == re.sub(r"\W", "", str(gold))
    if kind == "set":
        return isinstance(pred, list) and {str(x).strip().lower() for x in pred} == set(gold)
    return str(pred).strip().casefold() == str(gold).strip().casefold()


def share(hits):
    return round(sum(hits) / len(hits), 4) if hits else None


def score(gold, pred, details):
    first = next(iter(gold.values()))
    scenario = ("travel-request" if "form" in first else
                "expense-claim" if "per_diem" in first else "teaching")
    out = {"scenario": scenario, "cases": len(gold), "predicted": len(set(pred) & set(gold)),
           "unknown_case_ids": sorted(set(pred) - set(gold))}
    wrong = {}

    def check(cid, field, kind, g, p, bucket):
        ok = same(kind, g, p)
        bucket.setdefault(field, []).append(ok)
        if not ok:
            wrong.setdefault(cid, {})[field] = {"gold": g, "predicted": p}
        return ok

    fields = {}
    if scenario == "travel-request":
        tp = fp = fn = 0
        decision, rule = [], []
        for cid, g in gold.items():
            p = pred.get(cid, {})
            form = p.get("form") or {}
            for field, kind in FORM.items():
                check(cid, field, kind, g["form"][field], form.get(field), fields)
            gm = set(g["missing"])
            pm = {str(x).strip().lower() for x in p.get("missing") or []}
            tp, fp, fn = tp + len(gm & pm), fp + len(pm - gm), fn + len(gm - pm)
            if gm != pm:
                wrong.setdefault(cid, {})["missing"] = {"gold": sorted(gm), "predicted": sorted(pm)}
            decision.append(check(cid, "decision", "exact", g["decision"], p.get("decision"), {}))
            if g["decision"] == "reject":
                rule.append(check(cid, "rule", "exact", g["rule"], p.get("rule"), {}))
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        out.update(form_accuracy=share([x for v in fields.values() for x in v]),
                   missing_precision=round(precision, 4), missing_recall=round(recall, 4),
                   missing_f1=round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
                   decision_accuracy=share(decision), rule_accuracy_on_rejected=share(rule))
    elif scenario == "expense-claim":
        errors = []
        for cid, g in gold.items():
            p = pred.get(cid, {})
            for field in CLAIM:
                check(cid, field, "money", g[field], p.get(field), fields)
            try:
                errors.append(abs(float(p.get("total")) - g["total"]))
            except (TypeError, ValueError):
                errors.append(g["total"])
        out.update(amount_accuracy=share([x for v in fields.values() for x in v]),
                   claims_fully_correct=share([cid not in wrong for cid in gold]),
                   total_mean_absolute_error=round(sum(errors) / len(errors), 2))
    else:
        keyed = {}
        for cid, g in gold.items():
            p = pred.get(cid, {})
            check(cid, "request_type", "exact", g["request_type"], p.get("request_type"), fields)
            check(cid, "decision", "exact", g["decision"], p.get("decision"), fields)
            if g["key_field"]:
                check(cid, "key_value", "exact", g["key_value"], p.get("key_value"), keyed)
        fields.update(keyed)
        out.update(request_type_accuracy=share(fields["request_type"]),
                   decision_accuracy=share(fields["decision"]),
                   key_value_accuracy=share(keyed.get("key_value", [])))
    out["field_accuracy"] = {k: share(v) for k, v in fields.items()}
    if details:
        out["wrong"] = wrong
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("truth", help="ground-truth.jsonl of one scenario and split")
    ap.add_argument("predictions", help="your predictions.jsonl, one JSON object per case")
    ap.add_argument("--details", action="store_true", help="list every wrong value per case")
    args = ap.parse_args()
    result = score(load(args.truth), load(args.predictions), args.details)
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
