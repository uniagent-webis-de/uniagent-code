#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def input_cases(input_directory: Path) -> list[str]:
    if not input_directory.is_dir():
        raise ValueError(f"Input directory does not exist: {input_directory}")

    cases = sorted(
        path.name
        for path in input_directory.iterdir()
        if path.is_dir() and any(file.is_file() for file in path.iterdir())
    )
    if not cases:
        raise ValueError(f"No application directories found in {input_directory}")
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Predict 'abgelehnt' for every business-trip application."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    predictions = args.output / "predictions.jsonl"
    with predictions.open("w", encoding="utf-8") as output_file:
        for case in input_cases(args.input):
            prediction = {"antrag": case, "result": "abgelehnt"}
            output_file.write(json.dumps(prediction, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
