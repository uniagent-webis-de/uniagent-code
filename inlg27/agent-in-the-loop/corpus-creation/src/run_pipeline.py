#!/usr/bin/env python
"""Run the multi-source shared-task corpus pipeline in the canonical order.

The individual stages remain directly executable for debugging. This wrapper provides
one resumable entry point and stops at the first failed stage so a partial corpus is not
mistaken for a successful run.
"""

import argparse
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
LOGS_DIR = PROJECT_ROOT / "logs"


def setup_logging() -> logging.Logger:
    """Create a readable run log, replacing any previous runner log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"run_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger("run_pipeline")
    logger.setLevel(logging.INFO)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.info("logging to %s", log_path)
    logger.info("data root: %s", PROJECT_ROOT / "data")
    return logger


def stage_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    common = []
    if args.confidence != "high":
        common += ["--confidence", args.confidence]
    if args.task_id:
        common += ["--task-id", args.task_id]

    fetch = []
    parse = []
    group = []
    if args.volume:
        fetch += ["--volume", args.volume]
        parse += ["--volume", args.volume]
        group += ["--volume", args.volume]

    parse_fulltext = list(common)
    if args.ocr_server_url:
        parse_fulltext += ["--ocr-server-url", args.ocr_server_url, "--ocr-language", args.ocr_language]
    if args.only_needs_ocr:
        parse_fulltext.append("--only-needs-ocr")

    extract_figs_tbls = list(common)
    if args.pdffigures2_dir:
        extract_figs_tbls += ["--pdffigures2-dir", args.pdffigures2_dir]
    if args.pdffigures2_jar:
        extract_figs_tbls += ["--pdffigures2-jar", args.pdffigures2_jar]
    if args.pdffigures2_dpi != 150:
        extract_figs_tbls += ["--dpi", str(args.pdffigures2_dpi)]
    if args.pdffigures2_image_format != "png":
        extract_figs_tbls += ["--image-format", args.pdffigures2_image_format]
    if args.pdffigures2_threads != 4:
        extract_figs_tbls += ["--threads", str(args.pdffigures2_threads)]

    build = []
    if args.confidence != "high":
        build += ["--confidence", args.confidence]
    if args.target is not None:
        build += ["--target", str(args.target)]
    if args.task_id:
        build += ["--task-id", args.task_id]

    semeval = []
    if args.semeval_year:
        semeval = ["--year", str(args.semeval_year)]

    trec = []
    if args.trec_year:
        trec = ["--year", str(args.trec_year)]

    return [
        ("fetch_volumes", ["fetch_volumes.py", *fetch]),
        ("parse_sections", ["parse_sections.py", *parse]),
        ("group_tasks", ["group_tasks.py", *group]),
        ("fetch_semeval", ["fetch_semeval.py", *semeval]),
        ("collect_semeval", ["collect_semeval.py", *semeval]),
        ("fetch_trec", ["fetch_trec.py", *trec]),
        ("collect_trec", ["collect_trec.py", *trec]),
        ("merge_candidates", ["merge_candidates.py"]),
        ("download_papers", ["download_papers.py", *common, "--workers", str(args.download_workers)]),
        ("parse_fulltext", ["parse_fulltext.py", *parse_fulltext]),
        ("extract_figs_tbls", ["extract_figs_tbls.py", *extract_figs_tbls]),
        ("extract_counts", ["extract_counts.py", *common]),
        ("find_code", ["find_code.py", *common]),
        ("build_corpus", ["build_corpus.py", *build]),
    ]


def run_pipeline(args: argparse.Namespace) -> int:
    logger = setup_logging()
    for name, command in stage_commands(args):
        executable = [sys.executable, str(SRC_DIR / command[0]), *command[1:]]
        logger.info("=== START %s ===", name)
        logger.info("command: %s", " ".join(executable))
        process = subprocess.Popen(
            executable,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            logger.info("[%s] %s", name, line.rstrip())
        result = process.wait()
        logger.info("=== END %s (status=%d) ===", name, result)
        if result != 0:
            logger.error("pipeline stopped: %s exited with status %d", name, result)
            return result
    logger.info("pipeline completed successfully")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the multi-source shared-task corpus pipeline.")
    parser.add_argument("--volume", help="Process only one CLEF volume during metadata stages.")
    parser.add_argument("--confidence", choices=["high", "medium", "all"], default="high")
    parser.add_argument("--task-id", help="Process and assemble only one task.")
    parser.add_argument(
        "--download-workers",
        type=int,
        default=8,
        help="Concurrent PDF downloads (default: 8).",
    )
    parser.add_argument("--semeval-year", type=int, help="Process only one configured SemEval year during SemEval stages.")
    parser.add_argument("--trec-year", type=int, help="Process only one configured TREC year during TREC stages.")
    parser.add_argument(
        "--target",
        type=int,
        default=None,
        help="Optional maximum number of tasks to emit; by default all selected candidates are emitted.",
    )
    parser.add_argument("--ocr-server-url", help="Optional Liteparse OCR server URL.")
    parser.add_argument("--ocr-language", default="eng", help="OCR language for the OCR server.")
    parser.add_argument("--only-needs-ocr", action="store_true", help="Reparse only documents flagged by a previous full-text run.")
    parser.add_argument(
        "--pdffigures2-dir",
        default=None,
        help="PDFFigures2 checkout; defaults to third_party/pdffigures2.",
    )
    parser.add_argument("--pdffigures2-jar", help="Built PDFFigures2 JAR; avoids invoking sbt.")
    parser.add_argument("--pdffigures2-dpi", type=int, default=150, help="PDFFigures2 render resolution.")
    parser.add_argument(
        "--pdffigures2-image-format",
        choices=["png", "jpg", "jpeg"],
        default="png",
        help="PDFFigures2 output image format.",
    )
    parser.add_argument("--pdffigures2-threads", type=int, default=4, help="PDFFigures2 worker threads.")
    args = parser.parse_args()
    if args.download_workers < 1:
        parser.error("--download-workers must be at least 1")
    raise SystemExit(run_pipeline(args))


if __name__ == "__main__":
    main()
