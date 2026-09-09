# Event-Logging Contract for Coding Agents

This document specifies the event-logging contract that every UniAgent'26
submission (both Task 1, Retrieval, and Task 2, Solving) must comply with,
per the "Logging of Events and Tool Calls" section of the shared-task
description
(`https://uniagent.webis.de/cikm26/uniagent26-web/agentic-university-administration.html`). It is
binding: baselines and submissions in this repository must produce logs in
this exact shape.

The goal: every submission produces a machine-readable, auditable trace of
its run — not just which tools were called, but also the model calls,
inputs, outputs, and the final decision with its evidence — so that after
the shared task, the community can study evaluation measures that go beyond
accuracy (e.g. whether a decision was reached for the right reasons).

## Requirements

1. **Output file.** The executed software must produce a gzip-compressed
   JSON Lines file named `run_trace.jsonl.gz` (one JSON object per line,
   the file itself gzip-compressed). Logging can be skipped entirely only
   if the submission uses no tools **and** no model calls worth tracing;
   in practice, Task 2 submissions that call a model must log at least
   `model_call` and `decision` events.

2. **One JSON object per line (JSON Lines / NDJSON).** Each line is a
   self-contained event.

3. **Every event has the following fields** (fields that do not apply to a
   given event may be `null` or omitted, but the field names below must
   not be renamed):

   | Field | Type | Description |
   |---|---|---|
   | `case_id` | string | The identifier of the case/task the event belongs to. |
   | `event_id` | string | A unique identifier for this event, e.g. `evt-0007`. |
   | `parent_event_id` | string \| null | The `event_id` of the event that caused/preceded this one, forming a causal trace tree (e.g. a `tool_call` caused by a preceding `model_call`). `null` for root events. |
   | `timestamp` | string | ISO-8601 UTC timestamp when the event occurred/finished. |
   | `event_type` | string | One of `input`, `model_call`, `tool_call`, `observation`, `decision`, `error`, or an additional type if needed. |
   | `model` | string | The identifier of the LLM model backing this run (e.g. the value of `OPENAI_MODEL`/equivalent). Required on **every** event, not only `model_call`/`decision`, so the model behind a trace is never ambiguous. Submissions that call no model at all (e.g. a purely deterministic baseline) use `"-"`. |
   | `tool` | string \| null | The tool's name if `event_type == "tool_call"`, else `null`. |
   | `input` | object \| null | The prompt/arguments/documents given to the model or tool. |
   | `output` | object \| null | The model/tool response, including cited sources where applicable. |
   | `status` | string | `"ok"` or `"error"`. |
   | `error` | string \| null | The error message if `status == "error"`, else `null`. |

   `model` is the one field that is never optional/`null`, even for events
   unrelated to a specific model call (e.g. `tool_call`, `observation`):
   every event must be attributable to the model configured for the run
   that produced it, so traces from multi-model experiments or model
   changes between runs stay unambiguous without cross-referencing a
   separate run manifest.

4. **Log more than tool calls.** Beyond `tool_call` events, log important
   prompts and model responses (`model_call`), retrieved document
   identifiers and cited passages (`observation`), and errors (`error`).
   The log is meant to make the full reasoning/evidence trail auditable,
   not just which tools were invoked.

5. **`model_call` events** must include, at minimum, the prompt/input given
   to the model in `input` and the model's response (and any cited
   sources) in `output`. Example:

   ```json
   {"case_id": "dienstreiseantrag-03", "event_id": "evt-0007", "parent_event_id": "evt-0006", "timestamp": "2026-10-15T12:35:14.230Z", "event_type": "model_call", "model": "gpt-oss-20b", "tool": null, "input": {"prompt": "Check the travel request for completeness and rule compliance.", "documents": ["antrag.pdf", "bahn-ticket.pdf"]}, "output": {"response": "The request is incomplete because the return trip is missing...", "cited_sources": [{"source_id": "antrag.pdf", "page": 1, "quote": "Ende Dienstgeschäft: 11.02.2026"}]}, "status": "ok", "error": null}
   ```

6. **Every trace must end with a `decision` event.** The final event for
   each `case_id` must have `event_type: "decision"` and an `output`
   object containing the decision label, the submitted answer, and the
   evidence used to reach it. Example:

   ```json
   {"case_id": "dienstreiseantrag-03", "event_id": "evt-0012", "parent_event_id": "evt-0011", "timestamp": "2026-10-15T12:36:02.018Z", "event_type": "decision", "model": "gpt-oss-20b", "output": {"decision": "deny", "answer": "The request must be returned for correction...", "evidence": [{"source_id": "antrag.pdf", "page": 1, "relevance": "The end date of the business activity is before the travel date."}, {"source_id": "bahn-ticket.pdf", "page": 1, "relevance": "Only the outbound trip is documented."}]}, "status": "ok", "error": null}
   ```

7. **Errors must be logged, not swallowed.** A failing model/tool call must
   still produce an event with `status: "error"` and a non-null `error`
   message, with `parent_event_id` linking it back into the trace and
   `model` still populated, before any exception propagates.

8. **Token-usage metadata, if available, should be included** (e.g. inside
   `output` of the corresponding `model_call` event), since the hosted
   model may report it and it is useful for follow-up evaluation research.

9. **Causal linkage via `parent_event_id` is mandatory whenever an event is
   triggered by another** (e.g. a `tool_call` issued while handling a
   `model_call`'s output, or an `observation` produced by a `tool_call`),
   so the full trace can be reconstructed as a tree per `case_id`, not just
   a flat list.

## Non-goals

- This contract does not prescribe how an agent decides what to log beyond
  the required event types and fields; extra fields/event types are
  allowed as long as the required ones are present.
- This contract does not require logging model-internal reasoning tokens
  that never influence a tool call, prompt, or decision — only what is
  needed to make prompts, responses, tool arguments/outputs, retrieved
  documents, cited passages, and errors auditable.

