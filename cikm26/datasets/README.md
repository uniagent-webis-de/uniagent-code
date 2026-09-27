# Dataset Definitions

This directory contains the dataset and task definitions for TIRA.

There are currently spot-check datasets available that you can use to develop your systems.

You can download those datasets from tira (Please see [tira.io/datasets?query=uniagent](tira.io/datasets?query=uniagent)), or can access them from this directory.

# Spot-Check Datasets for Task 1 on Retrieval

We have three types of retrieval datasets for task 1. They are in the directories [retrieval-de-spot-check](retrieval-de-spot-check), [retrieval-en-spot-check](retrieval-en-spot-check), and [retrieval-hessian-law-de-spot-check](retrieval-hessian-law-de-spot-check). You can download the datasets from TIRA via the commands below.

Downloading the inputs to your system:
```
tira-cli download --dataset uniagent-2026/retrieval-de-spot-check-20260816-training
tira-cli download --dataset uniagent-2026/retrieval-en-spot-check-20260816-training
tira-cli download --dataset uniagent-2026/retrieval-hessian-law-de-spot-check-20260902-training
```

Download the truth for evaluation:
```
tira-cli download --dataset uniagent-2026/retrieval-de-spot-check-20260816-training --truths
tira-cli download --dataset uniagent-2026/retrieval-en-spot-check-20260816-training --truths
tira-cli download --dataset uniagent-2026/retrieval-hessian-law-de-spot-check-20260902-training --truths
```

# Spot-Check Datasets for Task 2 on Solving

The data is in the [business-trip-spot-check](business-trip-spot-check) directory, you can download it from TIRA via the commands below.

Downloading the inputs to your system:
```
tira-cli download --dataset uniagent-2026/business-trip-spot-check-20260907-training
```

Download the truth for evaluation:
```
tira-cli download --dataset uniagent-2026/business-trip-spot-check-20260907-training --truths
```

