FROM ghcr.io/uniagent-webis-de/uniagent-pyterrier-baseline:dev-0.0.1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --requirement /app/requirements.txt

ADD german-stopwords.txt event_logging.py retrieval_tools.py test_baseline.py baseline.py /app/
RUN chmod +x /app/baseline.py

RUN PYTHONPATH=. pytest .
