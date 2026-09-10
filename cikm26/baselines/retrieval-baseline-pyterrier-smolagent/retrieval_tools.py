"""The three agentic tools that turn ../retrieval-baseline-pyterrier/ into a
self-evaluating retrieval agent:

1. ``JudgeRelevanceTool`` asks the model to make up to 20 of its own graded
   relevance judgments for a query, over a set of candidate documents.
2. ``ComputeNdcgTool`` deterministically scores a ranked list of document IDs
   with nDCG@10 against the judgments made in (1) for the same query - no
   model call, just arithmetic, so repeated scoring is cheap and reliable.
3. ``ReformulateQueryTool`` asks the model to propose a new query
   formulation, given the original query, the previous query tried, and its
   nDCG@10 score from (2), and to say whether it is satisfied or wants
   another round.

``baseline.py`` orchestrates these three tools directly (as
``business-trip-smolagents-with-retrieval/predict.py`` orchestrates its own
tools) rather than handing them to an autonomous agent loop: it retrieves
candidates for the current best query, judges them, tries reformulations
while they keep improving nDCG@10, and finally reorders the winning query's
run so that documents judged relevant are moved to the top.
"""

import json
import math
from typing import Any, Optional

from smolagents import OpenAIModel, Tool

from event_logging import log_event, log_tool_calls


MAX_JUDGMENTS_PER_QUERY = 20
NDCG_CUTOFF = 10
MIN_RELEVANCE = 0
MAX_RELEVANCE = 3


class QueryJudgmentStore:
    """Holds each query's own relevance judgments, made once via
    JudgeRelevanceTool and then reused by every ComputeNdcgTool call for that
    query, exactly like a small per-run qrels file the agent writes itself."""

    def __init__(self) -> None:
        self._judgments: dict[str, dict[str, int]] = {}

    def set_judgments(self, qid: str, judgments: dict[str, int]) -> None:
        self._judgments[qid] = dict(judgments)

    def get_judgments(self, qid: str) -> dict[str, int]:
        return dict(self._judgments.get(qid, {}))

    def has_judgments(self, qid: str) -> bool:
        return qid in self._judgments


def dcg_at_k(gains: list[float], k: int = NDCG_CUTOFF) -> float:
    return sum(gain / math.log2(index + 2) for index, gain in enumerate(gains[:k]))


def ndcg_at_k(ranked_docnos: list[str], judgments: dict[str, int], k: int = NDCG_CUTOFF) -> float:
    """Standard nDCG@k with graded gains, 0 for any docno without a judgment."""
    gains = [judgments.get(docno, 0) for docno in ranked_docnos]
    actual_dcg = dcg_at_k(gains, k)
    ideal_gains = sorted(judgments.values(), reverse=True)
    ideal_dcg = dcg_at_k(ideal_gains, k)
    if ideal_dcg <= 0:
        return 0.0
    return actual_dcg / ideal_dcg


def _extract_all_json_values(text: str) -> list[Any]:
    """Scan `text` and decode every top-level JSON value found in it (object
    or array), in order. Unlike a single ``json.loads()``/first-match
    scan, this does not stop after the first valid value - needed because
    models sometimes answer with several separate top-level JSON values
    (e.g. one object per line/candidate) instead of a single wrapping
    object, and only using the first one would silently drop the rest."""
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] not in "{[":
            index += 1
        if index >= length:
            break
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        values.append(value)
        index = end
    return values


def call_model_json(model: OpenAIModel, messages: list[dict[str, str]]) -> dict[str, Any]:
    """Call the model and parse its answer as a single JSON object, tolerating
    markdown fences and leading/trailing prose around the JSON object."""
    response = model.generate(messages)
    content = getattr(response, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Model returned no final content.")

    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
        for value in _extract_all_json_values(text):
            if isinstance(value, dict):
                parsed = value
                break
        if parsed is None:
            raise ValueError(f"Model did not return valid JSON: {content!r}")
    if not isinstance(parsed, dict):
        raise ValueError("Model answer must be a JSON object.")
    return parsed


def _call_model_text(model: OpenAIModel, messages: list[dict[str, str]]) -> str:
    response = model.generate(messages)
    content = getattr(response, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Model returned no final content.")
    return content


def _parse_judgment_entries(content: str) -> list[dict[str, Any]]:
    """Parse the model's judge_relevance answer into a flat list of judgment
    entries, tolerating every shape models tend to produce despite being
    asked for a single ``{"judgments": [...]}`` object: a bare JSON array of
    judgments, a single bare judgment object, or several separate top-level
    JSON objects/arrays (e.g. one object per candidate, one per line) -
    every top-level JSON value in the answer is inspected, not just the
    first, so none of the model's judgments are silently dropped."""
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()

    entries: list[dict[str, Any]] = []
    for value in _extract_all_json_values(text):
        if isinstance(value, dict) and isinstance(value.get("judgments"), list):
            entries.extend(value["judgments"])
        elif isinstance(value, list):
            entries.extend(value)
        elif isinstance(value, dict) and "docno" in value:
            entries.append(value)
    if not entries:
        raise ValueError(f"Model did not return any judgment objects: {content!r}")
    return entries


class JudgeRelevanceTool(Tool):
    """Tool (1): ask the model to make up to 20 graded relevance judgments
    for one query, over a set of retrieved candidate documents."""

    name = "judge_relevance"
    description = (
        "Ask the model to make up to 20 graded relevance judgments "
        "(0=not relevant, 1=marginally relevant, 2=relevant, 3=highly relevant) "
        "for a query, over a list of candidate documents. Stores the judgments "
        "for the query so compute_ndcg can score any ranking against them."
    )
    inputs = {
        "qid": {"type": "string", "description": "The query ID being judged."},
        "query": {"type": "string", "description": "The query text (original or a reformulation)."},
        "description": {
            "type": "string",
            "description": "Optional longer description of the query's information need.",
            "nullable": True,
        },
        "candidates": {
            "type": "array",
            "description": "Up to 20 candidate documents to judge, each {docno, snippet}.",
        },
    }
    output_type = "string"

    def __init__(self, model: OpenAIModel, store: QueryJudgmentStore):
        super().__init__()
        self.model = model
        self.store = store

    def forward(
        self,
        qid: str,
        query: str,
        candidates: list[dict[str, Any]],
        description: Optional[str] = None,
    ) -> str:
        if not candidates:
            raise ValueError("candidates must not be empty.")
        candidates = candidates[:MAX_JUDGMENTS_PER_QUERY]

        prompt = (
            "You are making your own graded relevance judgments for a search query, "
            "as if building a small qrels file from scratch.\n"
            f"QUERY_ID: {qid}\nQUERY: {query}\n"
            + (f"DESCRIPTION: {description}\n" if description else "")
            + "For EVERY candidate below, judge how relevant its text is to the query on a "
            "0-3 scale (0=not relevant, 1=marginally relevant, 2=relevant, 3=highly relevant). "
            "Only judge the exact docno values given below; do not invent, rename, or retype them.\n"
            f"CANDIDATES_JSON:\n{json.dumps(candidates, ensure_ascii=False)}\n\n"
            "Respond with ONLY a JSON object, no markdown: "
            '{"judgments":[{"docno":"...","relevance":0-3}, ...]}'
        )
        content = _call_model_text(self.model, [{"role": "user", "content": prompt}])
        raw_judgments = _parse_judgment_entries(content)

        # The model occasionally returns entries that are not usable: a
        # hallucinated/retyped docno that does not match any candidate (LLMs
        # are error-prone at retyping long UUIDs, and the lenient multi-object
        # parser above can also pick up illustrative example JSON from the
        # model's reasoning text), an out-of-range relevance grade, or a
        # malformed entry altogether. A single such entry must not abort the
        # whole judge_relevance call (and with it the query's entire
        # reformulation loop): invalid entries are skipped and logged as
        # `error` observations instead, and only if *no* entry is usable at
        # all does this tool raise.
        candidate_docnos = {str(candidate["docno"]) for candidate in candidates}
        judgments: dict[str, int] = {}
        skipped: list[dict[str, Any]] = []
        for entry in raw_judgments[:MAX_JUDGMENTS_PER_QUERY]:
            reason = self._invalid_reason(entry, candidate_docnos)
            if reason is not None:
                skipped.append({"entry": entry, "reason": reason})
                continue
            judgments[str(entry["docno"])] = int(entry["relevance"])

        if skipped:
            log_event(
                "error",
                tool=self.name,
                input={"qid": qid, "candidate_docnos": sorted(candidate_docnos)},
                output={"skipped": skipped},
                status="error",
                error=f"Skipped {len(skipped)} unusable judgment entry/entries.",
            )
        if not judgments:
            raise ValueError(
                f"Model did not return any usable judgments for query {qid!r}; "
                f"all {len(raw_judgments)} entries were invalid: {skipped!r}"
            )

        self.store.set_judgments(qid, judgments)
        return json.dumps({"qid": qid, "judgments": judgments}, ensure_ascii=False)

    @staticmethod
    def _invalid_reason(entry: Any, candidate_docnos: set[str]) -> Optional[str]:
        """Return why `entry` cannot be used as a judgment, or None if valid."""
        if not isinstance(entry, dict) or "docno" not in entry:
            return "not a {docno, relevance} object"
        docno = str(entry["docno"])
        if docno not in candidate_docnos:
            return "docno was not among the candidates"
        try:
            relevance = int(entry["relevance"])
        except (KeyError, TypeError, ValueError):
            return f"invalid relevance grade: {entry.get('relevance')!r}"
        if not MIN_RELEVANCE <= relevance <= MAX_RELEVANCE:
            return f"relevance grade {relevance} out of range [{MIN_RELEVANCE}, {MAX_RELEVANCE}]"
        return None


class ComputeNdcgTool(Tool):
    """Tool (2): deterministically score a ranked list of docnos with
    nDCG@10 against the query's own judgments made by judge_relevance."""

    name = "compute_ndcg"
    description = (
        "Compute nDCG@10 for a ranked list of document IDs (best first) against the "
        "relevance judgments already recorded for this query via judge_relevance. "
        "Call judge_relevance for the query first."
    )
    inputs = {
        "qid": {"type": "string", "description": "The query ID whose judgments to score against."},
        "ranked_docnos": {
            "type": "array",
            "description": "Ranked document IDs, best first, for a candidate query formulation.",
        },
    }
    output_type = "string"

    def __init__(self, store: QueryJudgmentStore):
        super().__init__()
        self.store = store

    def forward(self, qid: str, ranked_docnos: list[str]) -> str:
        if not self.store.has_judgments(qid):
            raise ValueError(f"No relevance judgments recorded yet for query {qid!r}; call judge_relevance first.")
        if not ranked_docnos:
            raise ValueError("ranked_docnos must not be empty.")
        judgments = self.store.get_judgments(qid)
        score = ndcg_at_k([str(docno) for docno in ranked_docnos], judgments)
        return json.dumps({"qid": qid, "ndcg@10": score}, ensure_ascii=False)


class ReformulateQueryTool(Tool):
    """Tool (3): ask the model to propose a new query formulation, informed
    by the previous formulation's nDCG@10 score."""

    name = "reformulate_query"
    description = (
        "Ask the model to propose a new formulation of the query, given the original "
        "query, the previously tried query and its nDCG@10 score. Returns the new query "
        "text and whether the model considers the search already good enough."
    )
    inputs = {
        "qid": {"type": "string", "description": "The query ID being reformulated."},
        "original_query": {"type": "string", "description": "The original, unmodified query text."},
        "previous_query": {"type": "string", "description": "The most recently tried query text."},
        "previous_ndcg": {"type": "number", "description": "nDCG@10 achieved by previous_query."},
        "description": {
            "type": "string",
            "description": "Optional longer description of the query's information need.",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, model: OpenAIModel):
        super().__init__()
        self.model = model

    def forward(
        self,
        qid: str,
        original_query: str,
        previous_query: str,
        previous_ndcg: float,
        description: Optional[str] = None,
    ) -> str:
        prompt = (
            "You are improving a search query for a BM25 keyword retrieval system by "
            "proposing an alternative formulation (synonyms, more specific/general terms, "
            "removed noise words). Judge whether the previous attempt already scores well.\n"
            f"QUERY_ID: {qid}\nORIGINAL_QUERY: {original_query}\n"
            + (f"DESCRIPTION: {description}\n" if description else "")
            + f"PREVIOUS_QUERY: {previous_query}\nPREVIOUS_NDCG@10: {previous_ndcg}\n\n"
            "Respond with ONLY a JSON object, no markdown: "
            '{"query":"the new query text","satisfied":true|false,"reasoning":"..."}'
        )
        parsed = call_model_json(self.model, [{"role": "user", "content": prompt}])
        new_query = parsed.get("query")
        if not isinstance(new_query, str) or not new_query.strip():
            raise ValueError(f"Model did not return a non-empty 'query': {parsed!r}")
        return json.dumps(
            {
                "qid": qid,
                "query": new_query.strip(),
                "satisfied": bool(parsed.get("satisfied")),
                "reasoning": str(parsed.get("reasoning", "")).strip(),
            },
            ensure_ascii=False,
        )


def build_query_tools(model: OpenAIModel, store: QueryJudgmentStore) -> dict[str, Tool]:
    """Build the three per-run agentic tools, keyed by tool name."""
    tools = [
        log_tool_calls(JudgeRelevanceTool(model, store)),
        log_tool_calls(ComputeNdcgTool(store)),
        log_tool_calls(ReformulateQueryTool(model)),
    ]
    return {tool.name: tool for tool in tools}
