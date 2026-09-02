#!/usr/bin/env bash

PATTERN='Dienstreise|Reisekosten|Trennungsgeld|Auslagenersatz|Fahrtkosten|Übernachtungsgeld|Tagegeld|Verpflegungsmehraufwand|Wegstreckenentschädigung|Reisekostenverordnung|Dienstreiseverordnung|A1-Bescheinigung'

zcat legal-hessen-processed/documents.jsonl.gz | grep -iE "$PATTERN" |gzip > ../datasets/in-progress/retrieval-hessian-law-de-spot-check/documents.jsonl.gz
