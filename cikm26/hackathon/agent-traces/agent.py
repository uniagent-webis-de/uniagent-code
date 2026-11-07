#!/usr/bin/env python3
"""A tool-calling agent for the hackathon data, with one trace file per case.

    python agent-traces/agent.py travel-request/dev --model gpt-oss:20b \
        --base-url http://localhost:11434/v1 --out agent-traces/gpt-oss-20b

The model works on one case at a time with four tools (list_files, read_file, read_rules,
calculate) and answers with final_answer in the format of evaluate.py. It sees only its case
folder and the scenario's rule sheet, never the ground truth. Writes
<out>/<scenario>/<split>/traces/<case>.jsonl, predictions.jsonl, and scores.json; cases with a
trace are skipped on a restart. Needs smolagents and an OpenAI-compatible endpoint; the key comes
from OPENAI_API_KEY (any text for Ollama).
"""
import argparse
import ast
import json
import operator
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from smolagents import OpenAIServerModel, Tool, ToolCallingAgent
from smolagents.memory import ActionStep, TaskStep
from smolagents.monitoring import LogLevel

PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG))
import evaluate  # noqa: E402

EMPTY = "final answer without values (for example after the step limit)"
RULES = {"travel-request": "travel-rules.md", "expense-claim": "travel-rules.md",
         "teaching": "examination-regulations.md"}
TASKS = {
    "travel-request": """You work in the travel office of the University of Wernstadt. A traveller has sent a business trip request (case {case}). Read the message and every attachment, read the rule sheet, and fill in the request form.

Call final_answer with one JSON object with exactly these keys:
- "form": an object with traveler_name, position, trip_type ("domestic" or "abroad"), destination_city, destination_country, purpose, departure_date, return_date (ISO dates), transport ("train", "bus", "plane", "private_car", or "service_car"), cost_centre, private_stay_start, private_stay_end (ISO dates or null), third_party (a list of "accommodation", "transport", "registration", "meals"), cost_transport, cost_accommodation, cost_registration, cost_total (numbers in EUR or null). Section 3 of the rule sheet defines every field.
- "missing": the names of the fields you could not fill, plus "invitation", "hotel_justification", or "flight_price_comparison" when the rules require them and they are absent.
- "decision": "approve" or "reject"; "rule": "R1" to "R5" for a refused trip, else null.
Use null for every value the documents do not give; never guess.""",
    "expense-claim": """You work in the travel office of the University of Wernstadt. A traveller has submitted an expense claim for an approved domestic business trip (case {case}). Read the note and every attachment, read the rule sheet, and compute the refund by its Section 4. Use the calculate tool for the arithmetic.

Call final_answer with one JSON object with exactly these keys, all amounts in EUR: "transport", "accommodation", "registration", "per_diem", "other", "total".""",
    "teaching": """You work in the examination office of the University of Wernstadt. A student has sent a request (case {case}). Read the message and every attachment, read the examination regulations, and decide the request.

Call final_answer with one JSON object with exactly these keys:
- "request_type": "exam_withdrawal", "illness", "thesis_extension", "credit_recognition", "late_registration", or "repeat_attempt".
- "decision": "grant" or "deny".
- "key_value": for a thesis extension the new submission deadline (ISO date, null if denied); for a credit recognition the number of recognised credits; for a repeat attempt the attempts left after the decision (the attempt asked for counts as left); null for all other types.""",
}


class CaseTool(Tool):
    """A tool bound to one case; records every call with its timing for the trace."""
    output_type = "string"

    def __init__(self, case, log):
        self.case, self.log = case, log
        super().__init__()

    def __call__(self, *args, **kwargs):
        start = time.time()
        try:
            result = super().__call__(*args, **kwargs)
        except Exception as error:
            self.log.append({"tool": self.name, "start": start, "end": time.time(), "error": str(error)})
            raise
        self.log.append({"tool": self.name, "start": start, "end": time.time(), "output": result})
        return result


class ListFiles(CaseTool):
    name = "list_files"
    description = "Lists the files of the case: the message or note, and one .txt file per attached document."
    inputs = {}

    def forward(self):
        return "\n".join(sorted(p.name for p in self.case.glob("*.txt")))


class ReadFile(CaseTool):
    name = "read_file"
    description = "Returns the full text of one file of the case."
    inputs = {"name": {"type": "string", "description": "A file name from list_files, such as message.txt."}}

    def forward(self, name):
        path = (self.case / name).resolve()
        if path.parent != self.case.resolve() or path.suffix != ".txt" or not path.is_file():
            raise ValueError("No file %r in this case; call list_files first." % name)
        return path.read_text(encoding="utf-8")


class ReadRules(CaseTool):
    name = "read_rules"
    description = "Returns the rule sheet of the University of Wernstadt that decides this case."
    inputs = {}

    def forward(self):
        return (PKG / "rules" / self.rules).read_text(encoding="utf-8")


OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.USub: operator.neg, ast.UAdd: operator.pos}


def arithmetic(node):
    if isinstance(node, ast.Expression):
        return arithmetic(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](arithmetic(node.left), arithmetic(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](arithmetic(node.operand))
    raise ValueError("Only numbers, + - * / and parentheses are allowed.")


class Calculate(CaseTool):
    name = "calculate"
    description = "Evaluates an arithmetic expression with numbers, + - * / and parentheses, for example '2*49.90 + 3*74'. Returns the result rounded to two decimals."
    inputs = {"expression": {"type": "string", "description": "The expression, with a dot as decimal separator."}}

    def forward(self, expression):
        return "%.2f" % arithmetic(ast.parse(expression, mode="eval"))


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds")


def reasoning_of(message):
    """The model's reasoning text, if the endpoint returns it (gpt-oss does)."""
    try:
        raw = message.raw.choices[0].message
    except (AttributeError, IndexError, TypeError):
        return None
    extra = getattr(raw, "model_extra", None) or {}
    return getattr(raw, "reasoning", None) or getattr(raw, "reasoning_content", None) \
        or extra.get("reasoning") or extra.get("reasoning_content")


def parse_answer(answer, scenario):
    if isinstance(answer, str):
        match = re.search(r"\{.*\}", answer, re.S)
        answer = json.loads(match.group(0)) if match else {}
    answer = dict(answer) if isinstance(answer, dict) else {}
    if scenario == "travel-request" and "form" not in answer:
        answer["form"] = {k: answer.pop(k) for k in list(answer) if k in evaluate.FORM}
    return answer


def run_case(case, scenario, args):
    """Runs the agent on one case; returns the trace events (the last one holds the answer)."""
    log = []
    tools = [cls(case, log) for cls in (ListFiles, ReadFile, ReadRules, Calculate)]
    tools[2].rules = RULES[scenario]
    model = OpenAIServerModel(model_id=args.model, api_base=args.base_url,
                              api_key=os.environ.get("OPENAI_API_KEY", "none"),
                              client_kwargs={"timeout": 900})
    agent = ToolCallingAgent(tools=tools, model=model, max_steps=args.max_steps,
                             max_tool_threads=1, verbosity_level=LogLevel.OFF)
    task = TASKS[scenario].format(case=case.name)
    started, answer, failure = time.time(), None, None
    try:
        answer = agent.run(task)
    except Exception as error:                 # the trace records it; the case counts as wrong
        failure = "%s: %s" % (type(error).__name__, error)
    events = []

    def event(event_type, start, end=None, **fields):
        events.append({"case_id": case.name, "event_id": "evt-%04d" % (len(events) + 1),
                       "parent_event_id": events[-1]["event_id"] if events else None,
                       "timestamp": iso(start), "event_type": event_type, "model": args.model,
                       "tool": fields.pop("tool", None), "input": fields.pop("input", None),
                       "output": fields.pop("output", None), "status": fields.pop("status", "ok"),
                       "error": fields.pop("error", None),
                       "duration_ms": None if end is None else round((end - start) * 1000), **fields})

    event("task", started, input={"system_prompt": agent.memory.system_prompt.system_prompt, "task": task})
    done = 0                                   # records of `log` already matched to a step
    for step in agent.memory.steps:
        if isinstance(step, TaskStep) or not isinstance(step, ActionStep):
            continue
        msg = step.model_output_message
        usage = step.token_usage
        event("model_call", step.timing.start_time, step.timing.end_time, step=step.step_number,
              output={"content": msg.content if msg else step.model_output,
                      "reasoning": reasoning_of(msg) if msg else None,
                      "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in step.tool_calls or []]},
              status="error" if step.error and not step.tool_calls else "ok",
              error=str(step.error) if step.error and not step.tool_calls else None,
              input_tokens=usage.input_tokens if usage else None,
              output_tokens=usage.output_tokens if usage else None)
        for call in step.tool_calls or []:
            if call.name == "final_answer":
                continue
            record = log[done] if done < len(log) else None
            if record is None or record["tool"] != call.name:     # the call failed before running
                event("tool_call", step.timing.start_time, tool=call.name, input=call.arguments,
                      status="error", error=str(step.error), step=step.step_number)
                continue
            done += 1
            event("tool_call", record["start"], record["end"], tool=call.name, input=call.arguments,
                  output=record.get("output"), status="error" if "error" in record else "ok",
                  error=record.get("error"), step=step.step_number)
    try:
        prediction = dict(parse_answer(answer, scenario), case_id=case.name) if failure is None else None
    except (ValueError, TypeError) as error:
        prediction, failure = None, "unreadable final answer: %s" % error
    if prediction and not any(v not in (None, "", [], {}) for k, v in prediction.items() if k != "case_id"):
        prediction, failure = None, EMPTY
    event("decision", time.time(), output=prediction or {"case_id": case.name},
          status="ok" if prediction else "error", error=failure,
          duration_ms_case=round((time.time() - started) * 1000))
    return events


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("split", help="a scenario split of the package, e.g. travel-request/dev")
    ap.add_argument("--model", required=True, help="model id at the endpoint")
    ap.add_argument("--base-url", required=True, help="OpenAI-compatible base URL")
    ap.add_argument("--out", required=True, help="output folder, e.g. agent-traces/gpt-oss-20b")
    ap.add_argument("--workers", type=int, default=1, help="cases in parallel")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--only", nargs="*", help="run only these case ids")
    args = ap.parse_args()
    split = (PKG / args.split).resolve()
    scenario = split.parent.name
    out = Path(args.out).resolve() / scenario / split.name
    (out / "traces").mkdir(parents=True, exist_ok=True)
    cases = [c for c in sorted((split / "inputs").iterdir())
             if not (out / "traces" / (c.name + ".jsonl")).exists() and (not args.only or c.name in args.only)]

    def one(case):
        events = run_case(case, scenario, args)
        with open(out / "traces" / (case.name + ".jsonl"), "w", encoding="utf-8") as fh:
            for e in events:
                fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        print("%s %s %s, %d events" % (time.strftime("%H:%M"), case.name, events[-1]["status"], len(events)), flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(one, cases))
    predictions = []
    for trace in sorted((out / "traces").glob("*.jsonl")):
        last = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
        predictions.append(last["output"])
    with open(out / "predictions.jsonl", "w", encoding="utf-8") as fh:
        for p in predictions:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    scores = evaluate.score(evaluate.load(split / "ground-truth.jsonl"), evaluate.load(out / "predictions.jsonl"), False)
    scores["model"] = args.model
    (out / "scores.json").write_text(json.dumps(scores, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in scores.items() if isinstance(v, float)}))


if __name__ == "__main__":
    main()
