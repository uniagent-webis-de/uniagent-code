FROM node:22-slim

RUN apt-get update \
	&& apt-get install --no-install-recommends -y python3 python3-pip \
	&& rm -rf /var/lib/apt/lists/*

RUN npm install -g @github/copilot

ADD requirements.txt /

RUN pip3 install --no-cache-dir --break-system-packages -r /requirements.txt \
	&& pip3 --no-cache-dir install --break-system-packages pytest \
	&& rm /requirements.txt

ADD *.py /

RUN cd / \
	&& PYTHONPATH=/ pytest test_baseline.py
