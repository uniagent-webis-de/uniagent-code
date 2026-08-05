---
configs:
- config_name: inputs
  data_files:
  - split: train
    path: "inputs/**"
- config_name: truths
  data_files:
  - split: train
    path:
    - "decision-trail/**"
    - "ground-truth.jsonl"

tira_configs:
  resolve_inputs_to: "inputs"
  resolve_truths_to: "."
  default_upload_name: "predictions.jsonl"
  input_format:
    name: "arbitrary"
  truth_format:
    name: "*.jsonl"
    config:
      id_field: "antrag"
      value_field: "result"
      required_fields: ["antrag", "result"]
      minimum_lines: 5
  baseline:
    link: "https://github.com/uniagent-webis-de/uniagent-code/tree/main/cikm26/baselines/business-trip-always-rejected"
    command: "/predict.py --input $inputDataset --output $outputDir"
    format:
      name: "*.jsonl"
      config:
        id_field: "antrag"
        value_field: "result"
        required_fields: ["antrag", "result"]
        minimum_lines: 5
        re_map:
          abgelehnt: 0
          angenommen: 1
  evaluator:
    measures: ["accuracy"]
---

# Dienstreiseantrag — Beispiel-Set (Solving)

**Alle Personen, Fachgebiete, Reisen, Firmen, Beträge, Aktenzeichen, Bank- und
Kontaktdaten in diesem Ordner sind frei erfunden.** Aufbau, Dokumenttypen und
Regelwerk orientieren sich an echten (im UNIAGENT-Projekt pseudonymisierten)
Dienstreisevorgängen der Universität Kassel; es sind aber keine realen Personen-
oder Falldaten enthalten. Die Fachbereichs- und Institutsangaben (FB 16,
Wilhelmshöher Allee 71-73) sind reale, öffentliche Adressdaten der Hochschule —
die darin auftretenden Personen und Fachgebiete nicht. Die IBAN-Prüfsummen sind
bewusst ungültig, können also keinem realen Konto entsprechen. Das Set ist zur
Veröffentlichung freigegeben.

## Aufgabe

Für jeden Fall unter `inputs/dienstreiseantrag-XX/` liegt ein eingereichter
"Antrag auf Dienstreisegenehmigung" mit den zugehörigen Unterlagen vor
(Tickets, Rechnungen, Buchungsbestätigungen, E-Mail-Korrespondenz). Aufgabe ist
es, den Antrag auf **Vollständigkeit und Regelkonformität** zu prüfen und zu
entscheiden: **angenommen** oder **abgelehnt**. Bei Ablehnung soll benannt
werden können, was fehlt oder nicht den Regeln entspricht.

## Struktur

```
dienstreiseantrag-solving/
  README.md
  make_examples.py            # erzeugt alle PDFs reproduzierbar neu
  ground-truth.jsonl          # Gold-Antwort pro Fall
  inputs/
    dienstreiseantrag-01/     # 4 PDF — was der Agent sieht
    dienstreiseantrag-02/     # 4 PDF
    dienstreiseantrag-03/     # 3 PDF
    dienstreiseantrag-04/     # 4 PDF
    dienstreiseantrag-05/     # 4 PDF
  decision-trail/             # NICHT an den Agenten geben
    dienstreiseantrag-01/     # Entscheidungsdokument (Beleg für das Gold-Label)
    ...
```

`inputs/` enthält ausschließlich Unterlagen, die **vor** der Entscheidung
vorliegen — es verrät die Antwort also nicht. Die Genehmigungs- bzw.
Korrektur-/Ablehnungsmails liegen getrennt in `decision-trail/`; sie belegen das
Gold-Label und dienen der Nachvollziehbarkeit (analog zu
`gold_status: evidenced_in_corpus` in `working/tira-dataset/`).

Alle 24 PDFs haben einen Textlayer (`pdftotext -layout` liefert Text), es gibt
keine Bild-Only-Dokumente.

## Fälle

| # | Fall | Ergebnis | Ablehnungs-/Prüfmuster |
|---|---|---|---|
| 1 | `dienstreiseantrag-01` | abgelehnt | Antrag erst nach durchgeführter Reise eingereicht — keine Vorab-Genehmigung |
| 2 | `dienstreiseantrag-02` | angenommen | Reguläre Konferenzreise, vollständig, rechtzeitig, Vortrag belegt |
| 3 | `dienstreiseantrag-03` | abgelehnt | Rückreise nicht dokumentiert, Auslands-Pflichtfeld leer, Datum vor Reisebeginn |
| 4 | `dienstreiseantrag-04` | angenommen | Privater Anschlussaufenthalt > 5 Arbeitstage, Kosten aber korrekt getrennt |
| 5 | `dienstreiseantrag-05` | abgelehnt | Doppelte Kostenübernahme — Stipendium deckt dieselben Positionen |

Die Prüfmuster in Spalte 4 sowie die im Set verwendeten Regeln
(6-Monats-Ausschlussfrist, 80 €-Übernachtungsgrenze Inland,
Auslandsübernachtungsgeld, 5-Arbeitstage-Regel bei privaten Aufenthalten,
A1-Bescheinigung mit 8 Wochen Vorlauf, Preisvergleich Bahn/Flug,
Rechnungsadressat Universität, Nichterstattung von Abendprogrammen) stammen aus
der anonymisierten Auswertung von `annotation_dienstreisen_combined_260528.xlsx`
und der Dienstreisegenehmigung im pseudonymisierten Korpus. Die Fälle selbst sind
neu geschrieben.

Fälle 3 und 5 verlangen, zwei Dokumente gegeneinander zu lesen (Antrag vs.
Anlage) bzw. einen Widerspruch innerhalb des Formulars zu erkennen; Fall 4 ist
bewusst ein *Trap*: das auffällige Merkmal (langer Privataufenthalt) ist regel-
konform behandelt, der Antrag also zu genehmigen.

## Neu erzeugen

```bash
python make_examples.py
```

Benötigt `reportlab`. Der Aufruf überschreibt `inputs/` und `decision-trail/`.

## TIRA-Konfiguration

Die TIRA-Konfiguration veröffentlicht ausschließlich den Inhalt von `inputs/`
als Systemeingabe. `decision-trail/` und `ground-truth.jsonl` werden gemeinsam
als private Ground Truth verpackt und nur dem Evaluator bereitgestellt.

Systeme schreiben `predictions.jsonl` mit genau einer Zeile pro Antrag:

```json
{"antrag": "dienstreiseantrag-01", "result": "abgelehnt"}
```

Zulässige Werte für `result` sind `angenommen` und `abgelehnt`. Bewertet wird
die Accuracy über den Hugging-Face-Evaluator von TIRA. Die vorläufige Baseline
unter `../../baselines/business-trip-always-rejected/` sagt für jeden Antrag
`abgelehnt` voraus.

Die lokale Paketierung lässt sich ohne Upload und ohne Baseline prüfen:

```bash
tira-cli dataset-submission \
  --path business-trip-spot-check \
  --task uniagent-2026 \
  --split train \
  --dry-run
```

Sobald die Baseline auf dem konfigurierten GitHub-Pfad verfügbar ist, prüft
derselbe Befehl ohne `--skip-baseline` zusätzlich Build, Ausführung,
Ausgabeformat und Evaluation.
