FROM ghcr.io/uniagent-webis-de/uniagent-pyserini-baseline:dev-0.0.1

WORKDIR /app

ADD test_baseline.py baseline.py /app/

RUN PYTHONPATH=. pytest .
