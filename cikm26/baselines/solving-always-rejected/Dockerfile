FROM python:3.13-slim

COPY predict.py /predict.py
RUN chmod +x /predict.py

ENTRYPOINT ["/predict.py"]
