# Inductive Natural Language Generation for Shared Tasks

## Overview

This project investigates how AI agents can support shared tasks as human-driven experiments. The goal is not to automate shared tasks, but to study how agents can help researchers understand and communicate a solution space by synthesizing example solutions into an accessible synopsis.

## Proposed Challenge

The primary task is to generate a shared-task overview from participating systems' notebook papers, submissions, and—where available—prompt or communication logs. A complementary task may generate notebook papers directly from submissions, providing practical value while avoiding train–test leakage.

Expected corpus structure:

```text
task/
├── papers/
│   ├── paper-1.pdf
│   └── paper-n.pdf
├── overview.pdf
└── summaries.json
```

Systems will be evaluated through qualitative expert review and comparative automated judging. The evaluation must account for overview papers that describe teams without corresponding notebook papers.

## Data Sources

Candidate collections include shared tasks from [CLEF](https://clef-initiative.eu/), TREC, NTCIR, FIRE, SemEval, PAN, and Touché. Existing resources include the [TIRA shared-task collection](https://git.webis.de/code-research/tira/tira-shared-tasks) and canonical CLEF overview/notebook-paper proceedings.

## Resources

- [Proposal draft](https://www.overleaf.com/7375677649nhbknmygttkd#56811b)
- [UniAgent code and baselines](https://github.com/uniagent-webis-de/uniagent-code)
- [Archived corpus repository](https://github.com/uniagent-webis-de/uniagent_inlg_26-ARCHIVED)
