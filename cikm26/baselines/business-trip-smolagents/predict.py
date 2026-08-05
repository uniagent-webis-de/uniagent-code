#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from typing import Any

from smolagents import OpenAIModel, ToolCallingAgent

from business_trip_tools import build_tools


INSTRUCTIONS = """
Du prüfst deutsche Dienstreiseanträge sorgfältig und konservativ.
Nutze die Werkzeuge, statt Dokumentinhalte, Regeln, Datumsvergleiche oder Summen zu erraten.
Arbeite ausschließlich am im Auftrag genannten Fall. Lies mindestens den Antrag und alle Unterlagen,
die für Vollständigkeit, Finanzierung, Reisedaten und Regelkonformität relevant sind.
Eine auffällige private Reiseverlängerung ist nicht automatisch ein Ablehnungsgrund, wenn private
Kosten sauber getrennt sind und der Universität keine Mehrkosten entstehen.
Beende die Prüfung mit genau einem JSON-Objekt ohne Markdown:
{"antrag":"dienstreiseantrag-XX","result":"angenommen|abgelehnt","begruendung":"kurze belegte Begründung"}
"""


def required_environment() -> tuple[str, str, str]:
    values = []
    for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        value = os.environ.get(name, "").strip()
        if not value:
            raise RuntimeError(f"Required environment variable {name} is not set.")
        values.append(value)
    return values[0], values[1], values[2]


def parse_decision(answer: Any, expected_case: str) -> dict[str, str]:
    if isinstance(answer, dict):
        decision = answer
    elif isinstance(answer, str):
        text = answer.strip()
        if text.startswith("```") and text.endswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip()
        try:
            decision = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"Agent did not return valid JSON: {answer!r}") from error
    else:
        raise ValueError(f"Agent returned unsupported answer type: {type(answer).__name__}")

    if not isinstance(decision, dict):
        raise ValueError("Agent decision must be a JSON object.")
    if decision.get("antrag") != expected_case:
        raise ValueError(
            f"Agent returned case {decision.get('antrag')!r}, expected {expected_case!r}."
        )
    if decision.get("result") not in {"angenommen", "abgelehnt"}:
        raise ValueError(f"Invalid result label: {decision.get('result')!r}")
    reason = decision.get("begruendung")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Agent decision requires a non-empty begruendung.")
    return {
        "antrag": expected_case,
        "result": decision["result"],
        "begruendung": reason.strip(),
    }


def input_cases(input_directory: Path) -> list[str]:
    if not input_directory.is_dir():
        raise ValueError(f"Input directory does not exist: {input_directory}")
    cases = sorted(
        path.name
        for path in input_directory.iterdir()
        if path.is_dir() and any(path.glob("*.pdf"))
    )
    if not cases:
        raise ValueError(f"No application directories found in {input_directory}")
    return cases


def decide_case(
    input_directory: Path,
    case_id: str,
    model: OpenAIModel,
    max_steps: int,
) -> dict[str, str]:
    def valid_final_answer(answer: Any, _memory: Any, _agent: Any) -> bool:
        try:
            parse_decision(answer, case_id)
            return True
        except ValueError:
            return False

    agent = ToolCallingAgent(
        tools=build_tools(input_directory, case_id),
        model=model,
        instructions=INSTRUCTIONS,
        max_steps=max_steps,
        final_answer_checks=[valid_final_answer],
        verbosity_level=1,
    )
    task = (
        f"Prüfe ausschließlich den Dienstreiseantrag {case_id}. "
        "Ermittle anhand aller Eingabedokumente und der abrufbaren Richtlinien, "
        "ob er angenommen oder abgelehnt werden muss."
    )
    return parse_decision(agent.run(task), case_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smolagents baseline for business-trip approval.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps must be positive.")

    api_base, api_key, model_id = required_environment()
    model = OpenAIModel(
        model_id=model_id,
        api_base=api_base,
        api_key=api_key,
        temperature=0,
        max_tokens=1200,
    )

    args.output.mkdir(parents=True, exist_ok=True)
    output_file = args.output / "predictions.jsonl"
    with output_file.open("w", encoding="utf-8") as predictions:
        for case_id in input_cases(args.input):
            decision = decide_case(args.input.resolve(), case_id, model, args.max_steps)
            predictions.write(json.dumps(decision, ensure_ascii=False) + "\n")
            predictions.flush()


if __name__ == "__main__":
    main()
