# docker build -t ghcr.io/uniagent-webis-de/agent-in-the-loop-evaluator:0.0.1 .
FROM python:3-slim

ADD requirements.txt /

RUN pip3 install --no-cache-dir -r /requirements.txt \
	&& pip3 --no-cache-dir install pytest \
	&& rm /requirements.txt

ADD *.py /

RUN cd / \
	&& PYTHONPATH=/ pytest test_evaluate.py

