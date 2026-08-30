# Copilot Baseline

This baseline asks GitHub Copilot CLI to summarize each `paper.txt.md`
directly, instead of extracting the title/abstract deterministically like the
naive baseline.

## Authentication

The baseline requires the `GH_TOKEN` environment variable to be set to a
GitHub token with Copilot access (a fine-grained PAT with the "Copilot
Requests" permission, or an OAuth token from the GitHub Copilot CLI or `gh`
apps). The script fails fast if `GH_TOKEN` is missing.

`GH_TOKEN` is passed straight through to every `copilot` invocation, which
authenticates with it directly per call
(see `copilot help environment`). No separate `copilot login` step is run, so
no system keychain or persisted credential file is required — this avoids
"Login succeeded, but the token was not saved" warnings in headless/container
environments that lack a credential store.

```bash
export GH_TOKEN=...
python3 baseline.py \
  --input ../corpora-in-progress/touche-20-task-1-spot-check/papers \
  --output predictions.jsonl
```

The output contains one JSON object per line:

```json
{"id": "172", "summary": "Argument Retrieval Using Deep Neural Ranking Models by Entezari and Völske proposes..."}
```

Use `--model` to pick a specific Copilot model; otherwise Copilot chooses.

# Submit to TIRA:

```
tira-cli code-submission \
    --path . \
    --task inlg27-agent-in-the-loop \
    --dataset touche-20-task-1-spot-check-20260830-training \
    --forward-environment-variable GH_TOKEN \
    --allow-network \
    --command '/baseline.py --input $inputDataset --output ${outputDir}/predictions.jsonl' \
    --dry-run
```
