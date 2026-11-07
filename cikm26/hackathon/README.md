# UniAgent Hackathon Data: The University of the Future

This package holds invented cases from the administration of a fictional university, for the open UniAgent hackathon on 8 November 2026 (CIKM 2026, Rome and online). Teams can build any agent or tool on it, for example a chatbot that fills a travel request, a checker for expense claims, or an assistant for the examination office, and evaluate it against the ground truth with the script included here.

Everything is invented: the University of Wernstadt, all people, companies, events, addresses, and numbers. No case is taken from or modelled on a real case. The travel cases follow the real rules of the University of Kassel and the Hessian travel expenses act, summarised in `rules/travel-rules.md`. The teaching cases follow an invented examination regulation in `rules/examination-regulations.md`.

## Scenarios

| Scenario | Task | Input per case | Cases (dev + test) |
|---|---|---|---|
| `travel-request` | Turn a traveller's message and attachments into a filled business trip request, list what must still be asked for, and decide whether the trip can be approved. | `message.txt`, invitations, offers | 20 + 20 |
| `expense-claim` | Compute the refund of an approved domestic trip after travel. | `note.txt`, the approved request, tickets, invoices, receipts | 14 + 14 |
| `teaching` | Answer a student's request to the examination office: classify it, decide it, and give the key value (a new deadline, recognised credits, or attempts left). | `message.txt`, certificates, transcripts | 15 + 15 |

Each expense claim belongs to the trip with the same number (`claim-07` is the claim of `trip-07`). In the travel requests, 30 trips are approved and 10 are refused; four trips go abroad. All texts are in English.

## Files

```
README.md                    this file
evaluate.py                  scores predictions against the ground truth
baseline.py                  trivial baseline, shows the prediction format
rules/travel-rules.md        the rules behind the travel and claim ground truth
rules/examination-regulations.md   the rules behind the teaching ground truth
travel-request/dev/inputs/trip-01/ ...   one folder per case
travel-request/dev/ground-truth.jsonl    one JSON object per case
travel-request/test/...                  same layout
expense-claim/{dev,test}/...             same layout, cases claim-NN
teaching/{dev,test}/...                  same layout, cases request-NN
agent-traces/agent.py                    a tool-calling agent, see Agent traces
agent-traces/<model>/<scenario>/dev/     its traces, predictions, and scores on the dev cases
```

Every case folder holds the traveller's or student's own text (`message.txt` or `note.txt`) and its attachments as PDF. Each PDF has a `.txt` twin with the same text (made by `pdftotext -layout`), so you can start without a PDF parser. The ground truth also contains an `explanation` (travel requests, teaching) or the refund `lines` and `per_diem_days` (claims), which help to debug; they are not scored.

## Loading the data

The scripts need Python 3.8 or newer and no packages.

```python
import json
from pathlib import Path

split = Path("travel-request/dev")
gold = [json.loads(line) for line in open(split / "ground-truth.jsonl", encoding="utf-8")]
for case in sorted((split / "inputs").iterdir()):
    message = (case / "message.txt").read_text(encoding="utf-8")
    attachments = {p.name: p.read_text(encoding="utf-8")
                   for p in case.glob("*.txt") if p.name != "message.txt"}
```

## Output format

Write one JSON object per case and line into a file such as `predictions.jsonl`. Missing values are `null`.

**Travel request.** The fields are defined in Section 3 of `rules/travel-rules.md`. `missing` lists the fields that neither the message nor the attachments give, plus `invitation`, `hotel_justification`, or `flight_price_comparison` when the rules require them and they are absent. `decision` is `approve` or `reject`; for a refused trip, `rule` names the rule (`R1` to `R5`).

```json
{"case_id": "trip-01", "form": {"traveler_name": "Marta Kowalczyk", "position": "Research Associate", "trip_type": "domestic", "destination_city": "Dresden", "destination_country": "Germany", "purpose": "Workshop on Sediment Transport in Regulated Rivers", "departure_date": "2027-03-08", "return_date": "2027-03-11", "transport": "train", "cost_centre": "6203 1147", "private_stay_start": null, "private_stay_end": null, "third_party": [], "cost_transport": 99.8, "cost_accommodation": 222.0, "cost_registration": 120.0, "cost_total": 441.8}, "missing": [], "decision": "approve", "rule": null}
```

**Expense claim.** Six amounts in EUR, computed by the rules in Section 4 of `rules/travel-rules.md`.

```json
{"case_id": "claim-01", "transport": 99.8, "accommodation": 222.0, "registration": 120.0, "per_diem": 44.8, "other": 0.0, "total": 486.6}
```

**Teaching.** `request_type` is one of `exam_withdrawal`, `illness`, `thesis_extension`, `credit_recognition`, `late_registration`, and `repeat_attempt`. `decision` is `grant` or `deny`. `key_value` is the new submission deadline (ISO date, `null` if denied) for a thesis extension, the number of recognised credits for a credit recognition, and the attempts left after the decision for a repeat attempt (the attempt asked for counts as left); it is `null` for all other types.

```json
{"case_id": "request-04", "request_type": "thesis_extension", "decision": "grant", "key_value": "2027-08-02"}
```

## Evaluation

```bash
python baseline.py travel-request/dev > predictions.jsonl
python evaluate.py travel-request/dev/ground-truth.jsonl predictions.jsonl
python evaluate.py travel-request/dev/ground-truth.jsonl predictions.jsonl --details
```

The script recognises the scenario from the ground truth and prints the scores as JSON; `--details` adds every wrong value with the gold value. A case without a prediction counts as wrong.

| Scenario | Scores |
|---|---|
| `travel-request` | `form_accuracy` over all form fields and cases (amounts to the cent; dates, codes, and categories exact; a text field is right if it contains every word of the gold value); precision, recall, and F1 of the `missing` items; `decision_accuracy`; `rule_accuracy_on_rejected` |
| `expense-claim` | `amount_accuracy` over the six amounts (to the cent); `claims_fully_correct`; `total_mean_absolute_error` in EUR |
| `teaching` | `request_type_accuracy`, `decision_accuracy`, `key_value_accuracy` (over the cases with a key value) |

Trivial baseline scores on dev, for orientation: travel requests 0.23 form accuracy and 0.75 decision accuracy (it approves everything), expense claims 0.39 amount accuracy, teaching 0.53 decision accuracy.

## Free models

You can use any model. Teams without an API key can use the free options below. Providers change their models and limits without notice, so check the linked pages; the figures were read on 5 November 2026.

<!-- If TIRA offers an endpoint with the shared task's hosted models (gpt-oss-120b, gpt-oss-20b, Qwen2.5-7B), describe it here first. -->

| Option | What you need | Base URL for OpenAI-compatible clients | Free limits |
|---|---|---|---|
| [Duck.ai](https://duck.ai) | nothing, no account | none: chat only, for drafting ideas | a daily usage limit ([details](https://duckduckgo.com/duckduckgo-help-pages/duckai/usage-limits)) |
| Groq | free account and API key | `https://api.groq.com/openai/v1` ([docs](https://console.groq.com/docs/openai)) | per model, for example about 30 requests per minute and 1,000 per day for `openai/gpt-oss-120b` ([limits](https://console.groq.com/docs/rate-limits)) |
| OpenRouter | free account and API key; only models whose ID ends in `:free` | `https://openrouter.ai/api/v1` | 20 requests per minute and 50 per day, so a last resort ([limits](https://openrouter.ai/docs/api-reference/limits)) |
| Cerebras | account with a verified payment method | `https://api.cerebras.ai/v1` ([docs](https://inference-docs.cerebras.ai/resources/openai)) | trial credits of USD 5 for 30 days, 5 requests per minute ([limits](https://inference-docs.cerebras.ai/support/rate-limits)) |
| Ollama on your laptop | the model download, then no network | `http://localhost:11434/v1` with any API key, such as `ollama` ([docs](https://docs.ollama.com/openai)) | none; `gpt-oss:20b` (14 GB) needs at least 16 GB of memory, `qwen2.5:7b` (4.7 GB) less |

GitHub Models is not in the list because GitHub retired it on 30 July 2026.

The shared task's hosted models were gpt-oss-120b, gpt-oss-20b, and Qwen2.5-7B. Groq serves `openai/gpt-oss-120b` and `openai/gpt-oss-20b`, and Ollama runs `gpt-oss:20b` and `qwen2.5:7b`, so your results stay comparable with the shared task's runs.

An example with the `openai` package (`pip install openai`):

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.environ["GROQ_API_KEY"])
# on your laptop instead: OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"), model "gpt-oss:20b"
reply = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[{"role": "user", "content": "Which details does this travel request still lack? ..."}])
print(reply.choices[0].message.content)
```

At about 30 requests per minute, a dev split of 20 cases runs in a few minutes. Store the answers, so that you never send the same case twice.

## Agent traces

The folder `agent-traces/` holds runs of a tool-calling agent on the dev splits, for teams who study how agents behave: every model step, tool call, observation, and final answer, with timing.

- `agent-traces/agent.py` is the agent: a smolagents `ToolCallingAgent` with four tools, `list_files` and `read_file` (the text files of its case), `read_rules` (the scenario's rule sheet), and `calculate` (arithmetic). It sees only its own case folder and the rule sheet, never the ground truth. Like the shared task's baselines, it uses smolagents and the UniAgent event-logging contract; unlike them, it lets the model choose its tools instead of calling them in a fixed order. It runs on any OpenAI-compatible endpoint (see Free models), and you may change it as you like.
- `agent-traces/<model>/<scenario>/dev/traces/<case>.jsonl` is the trace of one case.
- `agent-traces/<model>/<scenario>/dev/predictions.jsonl` and `scores.json` hold the agent's answers and their scores by `evaluate.py`.

A trace has one JSON object per line with the fields of the event-logging contract (`case_id`, `event_id`, `parent_event_id`, `timestamp`, `event_type`, `model`, `tool`, `input`, `output`, `status`, `error`), plus `duration_ms`, the agent's `step`, and the token counts of each model call. The parent of an event is the event before it; the timestamp marks its start in UTC.

| `event_type` | `input` | `output` |
|---|---|---|
| `task` | the system prompt and the task, once per case | |
| `model_call` | not repeated: the task and all earlier events of the case | the model's message: `content`, `reasoning` (when the endpoint returns it), and `tool_calls` with their arguments |
| `tool_call` | the arguments of the call | the observation the model receives, or the error |
| `decision` | | the prediction in the format of `evaluate.py` |

**How the traces were made.** Both runs used `agent.py` as it is in this folder (smolagents 1.24.0, at most 20 steps per case, the models' default sampling) on all 49 dev cases, on 6 November 2026. The run `gpt-oss-120b` used GPT-OSS-120b at Blablador (Helmholtz), model id "01 - GPT-OSS-120b - an open model released by OpenAI in August 2025", four cases in parallel, 30 minutes in total. The run `gpt-oss-20b` used `gpt-oss:20b` in Ollama 0.40.14 on a laptop (Apple M4 Pro, 24 GB, context of 32,768 tokens), one case at a time, 37 minutes in total. Neither run saw the ground truth.

| Dev scores | `gpt-oss-120b` | `gpt-oss-20b` |
|---|---|---|
| Travel requests: form accuracy | 0.98 | 0.96 |
| Travel requests: F1 of the missing items (precision, recall) | 0.34 (0.21, 1.00) | 0.56 (0.38, 1.00) |
| Travel requests: decision accuracy | 1.00 | 0.90 |
| Travel requests: rule accuracy on refused trips | 1.00 | 0.60 |
| Expense claims: amount accuracy | 0.76 | 0.87 |
| Expense claims: claims fully correct | 0.57 | 0.71 |
| Teaching: request type accuracy | 1.00 | 1.00 |
| Teaching: decision accuracy | 0.80 | 0.80 |
| Teaching: key value accuracy | 0.75 | 0.50 |

| Mean per case (travel / claims / teaching) | `gpt-oss-120b` | `gpt-oss-20b` |
|---|---|---|
| Steps (model calls) | 11.2 / 14.1 / 8.9 | 8.8 / 11.9 / 8.5 |
| Steps without a tool call | 4.7 / 4.4 / 3.4 | 2.3 / 3.4 / 2.8 |
| Seconds | 143 / 172 / 110 | 46 / 65 / 26 |

What the traces show, as starting points:

- Both agents read the rule sheet in 97 of 98 cases, no tool call failed, and they used the calculator at most 1.6 times per case, even for refunds.
- In 26 to 42 percent of their steps, the models send no tool call (plain text or an empty message); smolagents records an error and asks again. The 120b agent hit the step limit twice and once ended without an answer (`claim-02`).
- Both agents list fields as missing that are empty by definition, such as a fee when there is none; the 120b agent also lists the dates of a private stay that does not exist. The agent's prompt asks for "fields you could not fill"; the rule sheet means fields whose value the documents do not give. Both also ask for an invitation where a fair ticket with the appointments, a confirmation of the archive, or the organiser's mail is attached, because the rule's "or similar document" leaves room.
- Both paid a claim filed eight months after the trip (`claim-15`, rule E1), both overlooked Ascension Day when counting working days (`request-03`), both let a student withdraw from a third attempt without a reason (`request-07`), and both set a thesis deadline on Whit Monday (`request-14`).
- The 20b agent approved a trip to an online conference (`trip-05`) and a keynote with an honorarium (`trip-11`), and it ignored the cap on recognised credits (`request-13`). The 120b agent refunded a shared taxi in full (`claim-06`), a taxi taken for comfort (`claim-07`), and parking for a private car without approved reasons (`claim-18`).

To run the agent yourself, for example with Ollama:

```bash
pip install smolagents openai
OPENAI_API_KEY=ollama python agent-traces/agent.py travel-request/dev --model gpt-oss:20b --base-url http://localhost:11434/v1 --out my-run
```

## Rules of the game

- Build and tune on `dev`. The `test` ground truth is in the package so that you can score yourself during the afternoon; please score on `test` once, at the end, and report that number.
- Say which model and which tools your system uses, and whether it reads the rule sheets or retrieves the rules itself. The shared task's public corpora (University of Kassel web pages and Hessian law) are in the UniAgent repository and may be used.
- The travel decisions correspond to the decisions of UniAgent Task 2: `approve` is `angenommen`, `reject` is `abgelehnt`.

## How the data was made

A generator writes every case from a short list of facts per case: the traveller, dates, fares, hotel, fee, and the rule the case tests. Message, attachments, and ground truth derive from the same facts, and the refunds are computed by the rules in `rules/travel-rules.md`. All cases were checked against the shared task's real cases and pseudonymisation lists: they share no names, numbers, addresses, or longer text passages.
