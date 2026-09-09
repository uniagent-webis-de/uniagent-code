FROM python:3.13-slim

# click: this script's CLI.
# tira[ir]: provides `tira-cli` plus trectools (for the retrieval datasets'
#   nDCG@10 measure).
# evaluate + scikit-learn: needed by tira's HuggingFaceEvaluator for the
#   business-trip datasets' `accuracy` measure (evaluate.load("accuracy")
#   uses scikit-learn under the hood).
RUN pip install --no-cache-dir click 'tira[ir]' evaluate scikit-learn

COPY evaluate_submission.py /evaluate_submission.py
RUN chmod +x /evaluate_submission.py

ENTRYPOINT ["/evaluate_submission.py"]
