"""Render the fictional Dienstreiseantrag example set as PDFs.

Everything rendered here is invented. The layouts imitate the document types that
occur in real business-trip files (SAP travel-request form, Outlook print-outs,
vendor invoices, bank statement extracts) so that agents see realistic input.

    /Users/simonruth/Documents/tasks/.venv-1/bin/python make_examples.py
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "inputs")
# The decision documents are the evidence for the gold label. They are written
# OUTSIDE inputs/ so that inputs/ can be handed to an agent without leaking it.
TRAIL = os.path.join(HERE, "decision-trail")

GREY = colors.HexColor("#666666")
LIGHT = colors.HexColor("#efefef")
LINE = colors.HexColor("#b4b4b4")

P = ParagraphStyle("p", fontName="Helvetica", fontSize=9, leading=12)
PS = ParagraphStyle("ps", parent=P, fontSize=7.5, leading=9.5, textColor=GREY)
PB = ParagraphStyle("pb", parent=P, fontName="Helvetica-Bold")
H1 = ParagraphStyle("h1", parent=P, fontName="Helvetica-Bold", fontSize=14, leading=18)
H2 = ParagraphStyle("h2", parent=P, fontName="Helvetica-Bold", fontSize=10, leading=14,
                    spaceBefore=8, spaceAfter=3)
RIGHT = ParagraphStyle("r", parent=P, alignment=2)
RIGHTS = ParagraphStyle("rs", parent=PS, alignment=2)


def _doc(path, top=2.0 * cm, bottom=1.8 * cm):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return SimpleDocTemplate(
        path, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.0 * cm,
        topMargin=top, bottomMargin=bottom, title=os.path.basename(path),
        author="", subject="", creator="",
    )


def kv_table(rows, widths=(5.4 * cm, 11.0 * cm), bold_keys=()):
    data = []
    for k, v in rows:
        ks = PB if k in bold_keys else P
        data.append([Paragraph(k, ks), Paragraph(v, PB if k in bold_keys else P)])
    t = Table(data, colWidths=list(widths))
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e2e2e2")),
    ]))
    return t


def money_table(rows, total=None, widths=(10.6 * cm, 3.0 * cm, 2.8 * cm)):
    data = [[Paragraph("<b>Position</b>", P), Paragraph("<b>Menge</b>", RIGHT),
             Paragraph("<b>Betrag</b>", RIGHT)]]
    for pos, qty, amount in rows:
        data.append([Paragraph(pos, P), Paragraph(qty, RIGHT), Paragraph(amount, RIGHT)])
    if total:
        data.append([Paragraph("<b>%s</b>" % total[0], P), Paragraph("", RIGHT),
                     Paragraph("<b>%s</b>" % total[1], RIGHT)])
    t = Table(data, colWidths=list(widths))
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#e2e2e2")),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
    ]
    if total:
        style.append(("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black))
    t.setStyle(TableStyle(style))
    return t


# --------------------------------------------------------------------------- #
# 1. Dienstreiseantrag (SAP/ESS-style travel request form)
# --------------------------------------------------------------------------- #

FB16 = ["Universität Kassel", "Fachbereich 16", "Elektrotechnik / Informatik",
        "Wilhelmshöher Allee 71-73", "34121 Kassel"]


def antrag_pdf(path, *, reisenummer, name, fachgebiet, personalnummer, status,
               geaendert_am, genehmigt_von, allgemein, verlauf, kosten,
               kosten_total, finanzierung, begruendung, antragsdatum,
               hinweis=None, pages_note="Seite 1 von 1"):
    doc = _doc(path, top=1.4 * cm)
    st = []

    hdr = Table([[
        Paragraph("<br/>".join(["<b>%s</b>" % name, fachgebiet,
                                "Personalnummer %s" % personalnummer]), P),
        Paragraph("<br/>".join(FB16), RIGHTS),
    ]], colWidths=[8.4 * cm, 8.0 * cm])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    st += [hdr, Spacer(1, 6)]

    meta = Table([[
        Paragraph(pages_note, PS),
        Paragraph("<br/>".join([
            "Zuletzt geändert am: %s" % geaendert_am,
            "Status: %s" % status,
            "Genehmigt von: %s" % genehmigt_von,
        ]), RIGHTS),
    ]], colWidths=[8.4 * cm, 8.0 * cm])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    st += [meta, Spacer(1, 10)]

    st += [Paragraph("ANTRAG AUF DIENSTREISEGENEHMIGUNG", H1),
           Paragraph("vor Antritt der Reise einzureichen &#183; Reisenummer %s"
                     % reisenummer, PS),
           Spacer(1, 10)]

    st += [Paragraph("Allgemeine Daten", H2), kv_table(allgemein)]
    st += [Paragraph("Reiseverlauf", H2), kv_table(verlauf)]
    st += [Paragraph("Voraussichtliche Kosten (Schätzung)", H2),
           money_table(kosten, kosten_total)]
    st += [Spacer(1, 4), kv_table([("Finanzierung:", finanzierung)])]

    st += [Paragraph("Kurzbegründung", H2), Paragraph(begruendung, P)]
    if hinweis:
        st += [Spacer(1, 6),
               Paragraph("<b>Hinweis der/des Antragsteller:in:</b> %s" % hinweis, P)]

    sig = Table([[
        Paragraph("Datum: %s" % antragsdatum, P),
        Paragraph("Unterschrift Antragsteller:in: %s" % name, RIGHT),
    ]], colWidths=[6.0 * cm, 10.4 * cm])
    sig.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE),
                             ("TOPPADDING", (0, 0), (-1, -1), 6),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    st += [Spacer(1, 18), sig, Spacer(1, 14),
           Paragraph("Erstellt durch ESS-Reisemanagement &#183; Universität Kassel",
                     PS)]
    doc.build(st)
    print("wrote", os.path.relpath(path, HERE))


# --------------------------------------------------------------------------- #
# 2. E-Mail print-out (Outlook-web style, as in the real corpus)
# --------------------------------------------------------------------------- #

def email_pdf(path, *, mailbox, url, subject, sender, sent, to, body, cc=None,
              folder=None, printed="16.06.26, 15:42"):
    doc = _doc(path, top=2.4 * cm, bottom=2.2 * cm)

    def deco(canv, _d):
        canv.saveState()
        canv.setFont("Helvetica", 6.5)
        canv.setFillColor(GREY)
        canv.drawString(2.2 * cm, A4[1] - 1.2 * cm, "E-Mail – %s" % mailbox)
        canv.drawRightString(A4[0] - 2.0 * cm, A4[1] - 1.2 * cm, url)
        canv.setStrokeColor(colors.HexColor("#dddddd"))
        canv.line(2.2 * cm, A4[1] - 1.35 * cm, A4[0] - 2.0 * cm, A4[1] - 1.35 * cm)
        canv.drawString(2.2 * cm, 1.3 * cm, "%d von %d" % (canv.getPageNumber(),
                                                           canv.getPageNumber()))
        canv.drawRightString(A4[0] - 2.0 * cm, 1.3 * cm, printed)
        canv.restoreState()

    st = [Paragraph(subject, H1), Spacer(1, 8), Paragraph("<b>%s</b>" % sender, P),
          Paragraph(sent, PS), Spacer(1, 4)]
    if folder:
        st += [Paragraph(folder, PS), Spacer(1, 2)]
    st += [Paragraph("An: %s" % to, PS)]
    if cc:
        st += [Paragraph("Cc: %s" % cc, PS)]
    st += [Spacer(1, 12)]
    for para in body:
        if para == "---":
            st += [Spacer(1, 6),
                   Table([[""]], colWidths=[16.4 * cm],
                         style=[("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE)]),
                   Spacer(1, 6)]
        else:
            st += [Paragraph(para, P), Spacer(1, 6)]
    doc.build(st, onFirstPage=deco, onLaterPages=deco)
    print("wrote", os.path.relpath(path, HERE))


# --------------------------------------------------------------------------- #
# 3. Vendor invoice / booking confirmation
# --------------------------------------------------------------------------- #

def invoice_pdf(path, *, vendor, vendor_addr, recipient, refs, heading, intro=None,
                items=None, sums=None, payment=None, closing=None, notes=None):
    doc = _doc(path)
    st = []

    hdr = Table([[
        Paragraph("<br/>".join(recipient), P),
        Paragraph("<br/>".join(["<b>%s</b>" % vendor] + vendor_addr), RIGHTS),
    ]], colWidths=[9.4 * cm, 7.0 * cm])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    st += [hdr, Spacer(1, 14)]

    ref = Table([[Paragraph("", P),
                  Paragraph("<br/>".join("%s %s" % (k, v) for k, v in refs), RIGHTS)]],
                colWidths=[9.4 * cm, 7.0 * cm])
    ref.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    st += [ref, Spacer(1, 14), Paragraph(heading, H1)]
    if intro:
        st += [Spacer(1, 2), Paragraph(intro, PS)]
    st += [Spacer(1, 10)]

    if items:
        data = [[Paragraph("<b>%s</b>" % c, RIGHT if i else P)
                 for i, c in enumerate(["Beschreibung", "Menge", "MwSt", "netto",
                                        "brutto"])]]
        for row in items:
            data.append([Paragraph(row[0], P)] +
                        [Paragraph(c, RIGHT) for c in row[1:]])
        t = Table(data, colWidths=[7.4 * cm, 1.6 * cm, 1.9 * cm, 2.7 * cm, 2.8 * cm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e2e2e2")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        st += [t, Spacer(1, 8)]

    if sums:
        data = [[Paragraph(k, RIGHT), Paragraph(v, RIGHT)] for k, v in sums]
        t = Table(data, colWidths=[13.6 * cm, 2.8 * cm])
        t.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ]))
        st += [t, Spacer(1, 14)]

    if payment:
        st += [Paragraph("Zahlungsinformationen", H2), kv_table(payment), Spacer(1, 10)]
    if notes:
        for n in notes:
            st += [Paragraph(n, PS), Spacer(1, 4)]
    if closing:
        st += [Spacer(1, 8), Paragraph(closing, P), Paragraph(vendor, P)]
    doc.build(st)
    print("wrote", os.path.relpath(path, HERE))


# --------------------------------------------------------------------------- #
# 4. Bank statement extract (Kontoauszug / payment proof)
# --------------------------------------------------------------------------- #

def bank_receipt_pdf(path, *, bic, iban, holder, queried, date, time, rows,
                     bank_footer):
    doc = _doc(path)
    top = Table([
        [Paragraph("BIC", PS), Paragraph(bic, P), Paragraph("Datum", PS),
         Paragraph(date, P)],
        [Paragraph("IBAN", PS), Paragraph(iban, P), Paragraph("Uhrzeit", PS),
         Paragraph(time, P)],
        [Paragraph("Kontoinhaber", PS), Paragraph(holder, P),
         Paragraph("Abgefragt von", PS), Paragraph(queried, P)],
    ], colWidths=[2.6 * cm, 6.4 * cm, 2.9 * cm, 4.5 * cm])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 2),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    st = [top, Spacer(1, 22), kv_table(rows, widths=(5.2 * cm, 11.2 * cm)),
          Spacer(1, 26), Paragraph(bank_footer, PS)]
    doc.build(st)
    print("wrote", os.path.relpath(path, HERE))


# =========================================================================== #
#                                  CASE 01                                    #
#            abgelehnt: Antrag erst nach Reiseantritt eingereicht             #
# =========================================================================== #

C1 = os.path.join(ROOT, "dienstreiseantrag-01")

antrag_pdf(
    os.path.join(C1, "antrag-dienstreisegenehmigung.pdf"),
    reisenummer="3381029441", name="Jonas Ahlgrim",
    fachgebiet="Fachgebiet Digitale Verwaltung", personalnummer="048822",
    status="Antrag eingereicht", geaendert_am="20. Oktober 2026",
    genehmigt_von="---",
    allgemein=[
        ("Reiseziel:", "Leipzig"),
        ("Anlass:", "Workshop &#8222;Digitale Verwaltung im Hochschulkontext&#8220;"),
        ("Grund der Reise:", "Teilnahme, fachlicher Austausch"),
        ("Reise ins Ausland:", "[ ] ja &#160;&#160; [X] nein"),
        ("Verkehrsmittel:", "Bahn, 2. Klasse"),
        ("Datum der Antragstellung:", "20.10.2026"),
    ],
    verlauf=[
        ("Start:", "Mittwoch, 14. Oktober 2026, 07:10 Uhr (Abreise vom Wohnort)"),
        ("Ende:", "Donnerstag, 15. Oktober 2026, 20:40 Uhr (Rückkehr zum Wohnort)"),
        ("Beginn Dienstgeschäft:", "14.10.2026, 09:00 Uhr"),
        ("Ende Dienstgeschäft:", "15.10.2026, 17:00 Uhr"),
        ("priv. Aufenthalt:", "keiner"),
        ("Arbeitstage:", "2 (Anreise + Workshop)"),
    ],
    kosten=[("Bahn Kassel&#8211;Leipzig, Hin- und Rückfahrt", "1", "90,00 &#8364;"),
            ("Übernachtung, 1 Nacht", "1", "75,00 &#8364;"),
            ("Workshopgebühr (kostenfreie Veranstaltung)", "1", "0,00 &#8364;")],
    kosten_total=("Summe (Schätzung)", "165,00 &#8364;"),
    finanzierung="Fachgebietsbudget Digitale Verwaltung, Kostenstelle 5512-03",
    begruendung="Der Workshop war für die laufende Digitalisierungs-Roadmap des "
                "Fachgebiets fachlich relevant; der Austausch mit den Referenten "
                "der beteiligten Hochschulen war für das Arbeitspaket 3 unmittelbar "
                "verwertbar.",
    hinweis="Die Genehmigung wurde im Vorfeld versäumt. Der Workshop hat bereits "
            "vom 14. bis 15.10.2026 stattgefunden; die Fahrkarte und die "
            "Übernachtung wurden privat vorausgelegt. Ich bitte um "
            "<b>nachträgliche Genehmigung</b> der bereits durchgeführten Reise.",
    antragsdatum="20.10.2026",
)

invoice_pdf(
    os.path.join(C1, "bahn-rechnung-kassel-leipzig.pdf"),
    vendor="Nordbahn Fernverkehr AG",
    vendor_addr=["Gleisfeld 4", "60329 Frankfurt am Main",
                 "", "Kontakt", "service@nordbahn-fv.example"],
    recipient=["Jonas Ahlgrim", "Am Weinberg 12", "34117 Kassel"],
    refs=[("Auftragsnummer:", "004518220931"), ("Rechnungsnummer:", "1792-0318824411"),
          ("Rechnungsdatum:", "09.10.2026")],
    heading="Rechnung",
    intro="zur Auftragsnummer 004518220931",
    items=[["Fahrkarte Sparpreis, Kassel-Wilhelmshöhe &#8594; Leipzig Hbf, "
            "2. Klasse, 1 Person (ab 15 Jahre), 14.10.2026",
            "1", "7 % (D)", "42,06 &#8364;", "45,00 &#8364;"],
           ["Fahrkarte Sparpreis, Leipzig Hbf &#8594; Kassel-Wilhelmshöhe, "
            "2. Klasse, 1 Person (ab 15 Jahre), 15.10.2026",
            "1", "7 % (D)", "42,06 &#8364;", "45,00 &#8364;"]],
    sums=[("Summe (netto) 7 % (D)", "84,12 &#8364;"),
          ("zzgl. 7 % MwSt (D)", "5,88 &#8364;"),
          ("Summe (brutto)", "90,00 &#8364;")],
    payment=[("Datum", "09.10.2026"), ("Art der Transaktion", "Zahlung"),
             ("Betrag", "90,00 &#8364;"), ("Zahlungsmittel", "Kreditkarte")],
    notes=["Dieses Dokument berechtigt nicht zur Fahrt.",
           "Rechnungsempfänger ist eine Privatperson. Für die Erstattung durch die "
           "Universität ist ein Ersatzbeleg mit dem Vermerk &#8222;sachlich "
           "richtig&#8220; erforderlich."],
    closing="Mit freundlichen Grüßen",
)

invoice_pdf(
    os.path.join(C1, "hotelrechnung-leipzig.pdf"),
    vendor="Hotel Alte Messe Leipzig GmbH",
    vendor_addr=["Zwickauer Straße 118", "04279 Leipzig",
                 "", "USt-IdNr. DE244810933"],
    recipient=["Jonas Ahlgrim", "Am Weinberg 12", "34117 Kassel"],
    refs=[("Reservierungsnummer:", "AM-2026-44197"),
          ("Rechnungsnummer:", "R-2026-10-0881"),
          ("Rechnungsdatum:", "15.10.2026")],
    heading="Rechnung",
    intro="Aufenthalt 14.10.2026 &#8211; 15.10.2026, 1 Nacht, Einzelzimmer",
    items=[["Übernachtung Einzelzimmer, 14.10.2026", "1", "7 % (D)",
            "63,55 &#8364;", "68,00 &#8364;"],
           ["Frühstück", "1", "19 % (D)", "5,88 &#8364;", "7,00 &#8364;"]],
    sums=[("Summe (netto)", "69,43 &#8364;"), ("zzgl. MwSt", "5,57 &#8364;"),
          ("Summe (brutto)", "75,00 &#8364;")],
    payment=[("Datum", "15.10.2026"), ("Art der Transaktion", "Kartenzahlung"),
             ("Betrag", "75,00 &#8364;"), ("Zahlungsmittel", "girocard")],
    notes=["Hinweis: Das Frühstück ist bei Dienstreisen nicht erstattungsfähig und "
           "wird bei der Abrechnung vom Übernachtungsbetrag abgesetzt."],
    closing="Wir danken für Ihren Aufenthalt.",
)

bank_receipt_pdf(
    os.path.join(C1, "kontoauszug-zahlungsnachweis.pdf"),
    bic="HELADEF1KAS", iban="DE44 5205 0353 0004 8871 92",
    holder="Jonas Ahlgrim", queried="Jonas Ahlgrim",
    date="19.10.2026", time="18:52:07",
    rows=[
        ("Zahlungsbeteiligter", "Nordbahn Fernverkehr AG<br/>"
                                "DE29 5001 0517 0091 4477 30<br/>NOFVDEFFXXX"),
        ("Buchungstag", "09.10.2026"),
        ("Betrag", "-90,00 EUR"),
        ("Vorgang", "Kartenzahlung"),
        ("Verwendungszweck", "NORDBAHN FV AG//FRANKFURT/DE 09.10.2026 "
                             "AUFTRAG 004518220931 REF 771904/220931"),
        ("&#160;", "&#160;"),
        ("Zahlungsbeteiligter", "Hotel Alte Messe Leipzig GmbH<br/>"
                                "DE82 8605 5592 0100 4471 08<br/>WELADE8LXXX"),
        ("Buchungstag", "15.10.2026"),
        ("Betrag", "-75,00 EUR"),
        ("Vorgang", "Lastschrift-Kartenzahlung"),
        ("Verwendungszweck", "HOTEL ALTE MESSE//LEIPZIG/DE 15.10.2026 um "
                             "10:04:11 Uhr 52091407/016904/R-2026-10-0881"),
    ],
    bank_footer="Kontoauszug &#8211; elektronisch abgerufen. Dieser Auszug wurde "
                "dem Antrag als Zahlungsnachweis für die privat vorausgelegten "
                "Kosten beigefügt. &#160;&#160;&#160;&#160; Seite 1 von 1",
)

email_pdf(
    os.path.join(TRAIL, "dienstreiseantrag-01", "email-rueckfrage-reisekostenstelle.pdf"),
    mailbox="jonas.ahlgrim@uni-kassel.de",
    url="https://outlook.office.example/mail/id/AAQkAD",
    subject="[Extern] Ihr Dienstreiseantrag 3381029441 &#8211; Rückfrage zum Antragsdatum",
    sender="Reisekostenstelle, Universität Kassel &lt;dienstreisegenehmigung@uni-kassel.de&gt;",
    sent="Do 22.10.2026 09:04",
    to="Jonas Ahlgrim &lt;jonas.ahlgrim@uni-kassel.de&gt;",
    cc="Prof. Dr. Henrik Baumgart &lt;h.baumgart@uni-kassel.de&gt;",
    body=[
        "Sehr geehrter Herr Ahlgrim,",
        "Ihr Antrag auf Genehmigung einer Dienstreise (Reisenummer 3381029441) ist "
        "am 20.10.2026 bei uns eingegangen. Die beantragte Reise nach Leipzig hat "
        "nach Ihren Angaben bereits vom 14. bis 15.10.2026 stattgefunden.",
        "Dienstreisen sind vor Reiseantritt zu beantragen und zu genehmigen. Eine "
        "Genehmigung nach durchgeführter Reise ist nur in begründeten "
        "Ausnahmefällen und ausschließlich über einen gesonderten Antrag auf "
        "nachträgliche Genehmigung möglich, dem eine Stellungnahme der "
        "Fachgebietsleitung zu den Gründen des Versäumnisses beizufügen ist.",
        "Ein solcher Antrag liegt uns nicht vor. Bitte teilen Sie uns mit, ob Sie "
        "das Ausnahmeverfahren einleiten möchten. Wir bitten um Verständnis, dass "
        "wir den vorliegenden Antrag in dieser Form nicht genehmigen können.",
        "Mit freundlichen Grüßen<br/>i. A. Corinna Delfs<br/>"
        "Abteilung Personal und Organisation &#183; Reisekostenstelle<br/>"
        "Universität Kassel &#183; Mönchebergstraße 19 &#183; 34109 Kassel",
    ],
)

# =========================================================================== #
#                                  CASE 02                                    #
#                 angenommen: reguläre Konferenzreise, vollständig             #
# =========================================================================== #

C2 = os.path.join(ROOT, "dienstreiseantrag-02")

antrag_pdf(
    os.path.join(C2, "antrag-dienstreisegenehmigung.pdf"),
    reisenummer="3381029442", name="Dr. Mareike Voss",
    fachgebiet="Fachgebiet Verteilte Systeme", personalnummer="041907",
    status="Antrag eingereicht", geaendert_am="2. September 2026",
    genehmigt_von="---",
    allgemein=[
        ("Reiseziel:", "Rotterdam, NIEDERLANDE"),
        ("Anlass:", "NordSys 2026 &#8211; International Symposium on Distributed Systems"),
        ("Grund der Reise:", "Vortrag des nach Peer-Review angenommenen Beitrags "
                             "&#8222;Adaptive Replication under Partial Failure&#8220;"),
        ("Reise ins Ausland:", "[X] ja &#160;&#160; [ ] nein"),
        ("Verkehrsmittel:", "Bahn, 2. Klasse (An- und Abreisetag)"),
        ("Datum der Antragstellung:", "02.09.2026"),
    ],
    verlauf=[
        ("Start:", "Montag, 9. November 2026, 06:30 Uhr (Abreise vom Wohnort)"),
        ("Ende:", "Donnerstag, 12. November 2026, 21:15 Uhr (Rückkehr zum Wohnort)"),
        ("Beginn Dienstgeschäft:", "10.11.2026, 09:00 Uhr"),
        ("Ende Dienstgeschäft:", "11.11.2026, 18:00 Uhr"),
        ("priv. Aufenthalt:", "keiner"),
        ("Arbeitstage:", "4 (Anreise + 2 Konferenztage + Abreise)"),
        ("A1-Bescheinigung:", "beantragt am 02.09.2026 (Vorlauf &gt; 8 Wochen)"),
    ],
    kosten=[("Konferenzregistrierung (Early Bird, Mitglied)", "1", "450,00 &#8364;"),
            ("Bahn Kassel&#8211;Rotterdam, Hin- und Rückfahrt", "1", "180,00 &#8364;"),
            ("Unterkunft, 3 Nächte à 75,00 &#8364;", "3", "225,00 &#8364;"),
            ("Verpflegungsmehraufwand (Pauschale NL)", "1", "60,00 &#8364;")],
    kosten_total=("Summe (Schätzung)", "915,00 &#8364;"),
    finanzierung="Drittmittelprojekt SFB-1187 &#8222;Verteilte Resilienz&#8220;, "
                 "Kostenstelle 4471-08 (Reisemittel AP 2)",
    begruendung="Der Beitrag wurde nach Peer-Review angenommen (Annahmebestätigung "
                "liegt bei). Die Vorstellung auf der NordSys erhöht die Sichtbarkeit "
                "der Projektergebnisse und ermöglicht den fachlichen Austausch mit "
                "potenziellen Kooperationspartnern. Die Übernachtung erfolgt im "
                "Konferenzhotel; der Satz von 75,00 &#8364; liegt innerhalb der "
                "Höchstgrenze des Auslandsübernachtungsgeldes für die Niederlande.",
    antragsdatum="02.09.2026",
)

email_pdf(
    os.path.join(C2, "email-annahmebestaetigung-konferenz.pdf"),
    mailbox="mareike.voss@uni-kassel.de",
    url="https://outlook.office.example/mail/id/AAQkAE",
    subject="NordSys 2026 &#8211; Paper Acceptance Notification (#118)",
    sender="NordSys 2026 Program Chairs &lt;program-chairs@nordsys2026.example&gt;",
    sent="Fr 21.08.2026 23:41",
    to="Mareike Voss &lt;mareike.voss@uni-kassel.de&gt;",
    body=[
        "Dear Dr. Voss,",
        "we are pleased to inform you that your submission",
        "<b>#118 &#8211; &#8222;Adaptive Replication under Partial Failure&#8220;</b>",
        "has been <b>accepted</b> for presentation at NordSys 2026, the "
        "International Symposium on Distributed Systems, to be held in Rotterdam, "
        "the Netherlands, 10&#8211;11 November 2026.",
        "Your paper received three reviews with an average score of 2.0 (weak "
        "accept to accept). Please address the reviewers' comments in the "
        "camera-ready version, due 25 September 2026.",
        "At least one author is required to register and present the paper on site. "
        "Early-bird registration closes on 15 September 2026 (450 EUR for members).",
        "Congratulations, and we look forward to seeing you in Rotterdam.",
        "Best regards,<br/>The NordSys 2026 Program Committee",
    ],
)

invoice_pdf(
    os.path.join(C2, "konferenz-registrierungsbestaetigung.pdf"),
    vendor="NordSys 2026 Conference Office",
    vendor_addr=["c/o Symposia Events B.V.", "Weena 505", "3013 AL Rotterdam",
                 "Niederlande", "", "VAT NL812449770B01"],
    recipient=["Universität Kassel", "Fachbereich 16 &#183; Fachgebiet Verteilte Systeme",
               "z. Hd. Dr. Mareike Voss", "Wilhelmshöher Allee 71-73",
               "34121 Kassel, Deutschland"],
    refs=[("Registrierungsnummer:", "NS26-R-0417"),
          ("Rechnungsnummer:", "NS26-INV-0417"),
          ("Rechnungsdatum:", "08.09.2026")],
    heading="Registration Confirmation / Rechnung",
    intro="NordSys 2026, 10&#8211;11 November 2026, Rotterdam &#183; "
          "Teilnehmerin: Dr. Mareike Voss &#183; Presenting author, paper #118",
    items=[["Full registration, early bird, member rate", "1", "0 % (reverse charge)",
            "450,00 &#8364;", "450,00 &#8364;"]],
    sums=[("Summe (netto)", "450,00 &#8364;"),
          ("MwSt (Reverse Charge, Art. 44 MwStSystRL)", "0,00 &#8364;"),
          ("Summe (brutto)", "450,00 &#8364;")],
    payment=[("Zahlungsziel", "30.09.2026"),
             ("Art der Transaktion", "Überweisung"),
             ("Betrag", "450,00 &#8364;"),
             ("Status", "offen &#8211; Zahlung nach Genehmigung der Dienstreise")],
    notes=["Rechnungsempfänger ist die Universität Kassel. "
           "Leistungsempfänger im Sinne des Reverse-Charge-Verfahrens ist die "
           "Universität; die USt-IdNr. wurde geprüft.",
           "Die Registrierung schließt den Zugang zu allen Sessions sowie die "
           "Mittagsverpflegung an beiden Konferenztagen ein. Das optionale "
           "Conference Dinner (65,00 EUR) wurde nicht gebucht."],
    closing="Kind regards,",
)

invoice_pdf(
    os.path.join(C2, "bahn-buchungsbestaetigung.pdf"),
    vendor="Nordbahn Fernverkehr AG",
    vendor_addr=["Gleisfeld 4", "60329 Frankfurt am Main"],
    recipient=["Dr. Mareike Voss", "c/o Universität Kassel", "Fachbereich 16",
               "34121 Kassel"],
    refs=[("Auftragsnummer:", "004518334127"), ("Buchungsdatum:", "05.09.2026"),
          ("Status:", "reserviert, zahlbar bei Abreise")],
    heading="Buchungsbestätigung",
    intro="Reservierung, noch keine Rechnung &#8211; Zahlung erfolgt erst nach "
          "Genehmigung der Dienstreise",
    items=[["Kassel-Wilhelmshöhe &#8594; Rotterdam Centraal, 09.11.2026, 06:30 Uhr, "
            "2. Klasse, 1 Umstieg (Duisburg Hbf)", "1", "7 % (D)", "84,11 &#8364;",
            "90,00 &#8364;"],
           ["Rotterdam Centraal &#8594; Kassel-Wilhelmshöhe, 12.11.2026, 15:52 Uhr, "
            "2. Klasse, 1 Umstieg (Duisburg Hbf)", "1", "7 % (D)", "84,11 &#8364;",
            "90,00 &#8364;"]],
    sums=[("Summe (netto)", "168,22 &#8364;"), ("zzgl. MwSt", "11,78 &#8364;"),
          ("Summe (brutto)", "180,00 &#8364;")],
    notes=["Der Preisvergleich gegenüber einer Flugverbindung "
           "(Frankfurt&#8211;Rotterdam, ab 214,00 EUR) wurde durchgeführt; "
           "die Bahnverbindung ist wirtschaftlicher.",
           "Dieses Dokument berechtigt nicht zur Fahrt."],
    closing="Mit freundlichen Grüßen",
)

email_pdf(
    os.path.join(TRAIL, "dienstreiseantrag-02", "genehmigt.pdf"),
    mailbox="mareike.voss@uni-kassel.de",
    url="https://outlook.office.example/mail/id/AAQkAF",
    subject="[Extern] Ihr Dienstreiseantrag 3381029442 wurde genehmigt",
    sender="ESS-Reisemanagement, Universität Kassel &lt;noreply-ess@uni-kassel.de&gt;",
    sent="Mo 07.09.2026 08:12",
    to="Mareike Voss &lt;mareike.voss@uni-kassel.de&gt;",
    cc="Prof. Dr. Anke Wielandt &lt;a.wielandt@uni-kassel.de&gt;",
    body=[
        "Guten Tag,",
        "Ihr Antrag auf Genehmigung einer Dienstreise (Reisenummer 3381029442) "
        "wurde genehmigt.",
        "Bitte kontrollieren Sie Ihren Antrag im ESS-Reisemanagement auf etwaige "
        "Anmerkungen der Vorgesetzten und weiterer Genehmigungsinstanzen.",
        "Die folgenden Hinweise &#8211; sofern für Ihre Dienstreise zutreffend "
        "&#8211; sind Bestandteil der Dienstreisegenehmigung:",
        "&#8226; Übernachtungskosten im Inland sind gegen Nachweis bis zu einer "
        "Höchstgrenze von 80,00 &#8364; pro Nacht erstattungsfähig. Im Ausland gilt "
        "die Höchstgrenze des Auslandsübernachtungsgeldes gemäß "
        "Auslandsreisekostenverordnung.",
        "&#8226; Die Reisekostenabrechnung ist innerhalb der Ausschlussfrist von "
        "sechs Monaten nach Reiseende einzureichen. Danach erlischt der "
        "Erstattungsanspruch.",
        "&#8226; Bei Reisen ins EU-Ausland ist eine A1-Bescheinigung erforderlich. "
        "Bitte beantragen Sie diese mit einem Vorlauf von mindestens acht Wochen.",
        "&#8226; Kosten für Begleit- und Abendprogramme (z. B. Conference Dinner) "
        "sind grundsätzlich nicht erstattungsfähig.",
        "Mit freundlichen Grüßen<br/>ESS-Reisemanagement<br/>"
        "Universität Kassel &#183; Abteilung Personal und Organisation",
    ],
)

# =========================================================================== #
#                                  CASE 03                                    #
#        abgelehnt: unvollständig / widersprüchlich (Rückreise, Datum)        #
# =========================================================================== #

C3 = os.path.join(ROOT, "dienstreiseantrag-03")

antrag_pdf(
    os.path.join(C3, "antrag-dienstreisegenehmigung.pdf"),
    reisenummer="3381029443", name="Selin Kortmann",
    fachgebiet="Fachgebiet Umwelttechnik", personalnummer="052641",
    status="Antrag eingereicht", geaendert_am="12. Februar 2026",
    genehmigt_von="---",
    allgemein=[
        ("Reiseziel:", "Lyon, FRANKREICH"),
        ("Anlass:", "EnviroTech Summit 2026"),
        ("Grund der Reise:", "Teilnahme, Posterbeitrag"),
        ("Reise ins Ausland:", "[ ] ja &#160;&#160; [ ] nein &#160;&#160; <i>(Feld nicht ausgefüllt)</i>"),
        ("Verkehrsmittel:", "Bahn"),
        ("Datum der Antragstellung:", "12.02.2026"),
    ],
    verlauf=[
        ("Start:", "Montag, 9. März 2026, 07:00 Uhr (Abreise vom Wohnort)"),
        ("Ende:", "Mittwoch, 11. März 2026, 19:00 Uhr (Rückkehr zum Wohnort)"),
        ("Beginn Dienstgeschäft:", "10.03.2026, 09:00 Uhr"),
        ("Ende Dienstgeschäft:", "11.02.2026, 17:00 Uhr"),
        ("Hinreise:", "Bahn Kassel &#8594; Lyon, 09.03.2026, Ticket liegt bei"),
        ("Rückreise:", "&#8212;"),
        ("priv. Aufenthalt:", "keiner"),
        ("Arbeitstage:", "3"),
    ],
    kosten=[("Bahn Kassel&#8211;Lyon, Hinfahrt", "1", "145,00 &#8364;"),
            ("Bahn Lyon&#8211;Kassel, Rückfahrt", "1", "&#8212;"),
            ("Unterkunft, 2 Nächte", "2", "190,00 &#8364;"),
            ("Konferenzgebühr", "1", "180,00 &#8364;")],
    kosten_total=("Summe (Schätzung)", "unvollständig"),
    finanzierung="Fachgebietsbudget Umwelttechnik, Kostenstelle 5588-11",
    begruendung="Teilnahme am EnviroTech Summit zur Vorstellung eines Posters aus "
                "dem laufenden Feldprojekt. Die Rückreise wird gebucht, sobald das "
                "Programm final feststeht.",
    antragsdatum="12.02.2026",
)

invoice_pdf(
    os.path.join(C3, "bahn-ticket-hinfahrt.pdf"),
    vendor="Nordbahn Fernverkehr AG",
    vendor_addr=["Gleisfeld 4", "60329 Frankfurt am Main"],
    recipient=["Selin Kortmann", "c/o Universität Kassel", "Fachbereich 16",
               "34121 Kassel"],
    refs=[("Auftragsnummer:", "004516770218"), ("Rechnungsnummer:", "1792-0311447725"),
          ("Rechnungsdatum:", "11.02.2026")],
    heading="Rechnung",
    intro="zur Auftragsnummer 004516770218 &#183; einfache Fahrt",
    items=[["Fahrkarte Sparpreis Europa, Kassel-Wilhelmshöhe &#8594; Lyon Part-Dieu, "
            "2. Klasse, 1 Person, 09.03.2026, 07:00 Uhr, 2 Umstiege "
            "(Frankfurt Hbf, Paris Gare de Lyon)",
            "1", "7 % (D)", "135,51 &#8364;", "145,00 &#8364;"]],
    sums=[("Summe (netto)", "135,51 &#8364;"), ("zzgl. MwSt", "9,49 &#8364;"),
          ("Summe (brutto)", "145,00 &#8364;")],
    payment=[("Datum", "11.02.2026"), ("Art der Transaktion", "Zahlung"),
             ("Betrag", "145,00 &#8364;"), ("Zahlungsmittel", "Kreditkarte")],
    notes=["Es wurde ausschließlich eine <b>einfache Fahrt</b> gebucht. Eine "
           "Rückfahrkarte ist unter dieser Auftragsnummer nicht enthalten.",
           "Dieses Dokument berechtigt nicht zur Fahrt."],
    closing="Mit freundlichen Grüßen",
)

invoice_pdf(
    os.path.join(C3, "konferenz-anmeldebestaetigung.pdf"),
    vendor="EnviroTech Summit 2026",
    vendor_addr=["c/o Congrès Rhône SARL", "12 Rue de la Part-Dieu", "69003 Lyon",
                 "Frankreich"],
    recipient=["Selin Kortmann", "Universität Kassel", "Fachgebiet Umwelttechnik",
               "34121 Kassel, Deutschland"],
    refs=[("Anmeldenummer:", "ETS26-0912"), ("Bestätigt am:", "05.02.2026")],
    heading="Anmeldebestätigung",
    intro="EnviroTech Summit 2026, 10.&#8211;11. März 2026, Lyon &#183; "
          "Posterbeitrag P-44 &#8222;Sensor drift in long-term field deployments&#8220;",
    items=[["Standard registration incl. poster session", "1", "20 % (FR)",
            "150,00 &#8364;", "180,00 &#8364;"]],
    sums=[("Summe (netto)", "150,00 &#8364;"), ("zzgl. 20 % TVA (FR)", "30,00 &#8364;"),
          ("Summe (brutto)", "180,00 &#8364;")],
    notes=["Das Programm endet am <b>11. März 2026 um 16:30 Uhr</b> mit der "
           "Abschluss-Session. Das Posterprogramm P-44 ist für den 10. März, "
           "14:00&#8211;16:00 Uhr angesetzt."],
    closing="Cordialement,",
)

email_pdf(
    os.path.join(TRAIL, "dienstreiseantrag-03", "korrekturbedarf.pdf"),
    mailbox="selin.kortmann@uni-kassel.de",
    url="https://outlook.office.example/mail/id/AAQkAG",
    subject="[Extern] Ihr Dienstreiseantrag nach Lyon (3381029443) &#8211; "
            "Rücksendung zur Korrektur",
    sender="Reisekostenstelle, Universität Kassel &lt;dienstreisegenehmigung@uni-kassel.de&gt;",
    sent="Mo 16.02.2026 11:27",
    to="Selin Kortmann &lt;selin.kortmann@uni-kassel.de&gt;",
    cc="Prof. Dr. Katja Rehberg &lt;k.rehberg@uni-kassel.de&gt;",
    body=[
        "Sehr geehrte Frau Kortmann,",
        "vielen Dank für Ihren Antrag. Eine für die Genehmigung zuständige Instanz "
        "sieht Korrekturbedarf in Ihrer beantragten Reise nach Lyon (Reisenummer "
        "3381029443), weshalb diese Ihnen zur Korrektur zurückgeschickt wurde. "
        "Konkret ist Folgendes offen:",
        "1. <b>Rückreise nicht dokumentiert.</b> Beigefügt ist ausschließlich die "
        "Hinfahrt vom 09.03.2026; die Rückfahrkarte fehlt und die zugehörige "
        "Kostenposition ist offen. Damit ist der Reiseverlauf nicht prüfbar und "
        "die Gesamtsumme der Reise steht nicht fest.",
        "2. <b>Pflichtfeld &#8222;Reise ins Ausland&#8220; nicht ausgefüllt.</b> "
        "Das Reiseziel Lyon liegt in Frankreich; das Feld ist zwingend mit "
        "&#8222;ja&#8220; zu belegen, da Auslandsreisen stets der Genehmigung "
        "durch die Abteilung Personal und Organisation bedürfen und zusätzlich "
        "eine A1-Bescheinigung erforderlich ist.",
        "3. <b>Datumsangabe widersprüchlich.</b> Als &#8222;Ende "
        "Dienstgeschäft&#8220; ist der 11.02.2026 eingetragen; dieses Datum liegt "
        "vor dem angegebenen Reisebeginn am 09.03.2026. Hat sich hier ein "
        "Tippfehler eingeschlichen (Februar statt März)? Nach der "
        "Anmeldebestätigung endet das Programm am 11.03.2026 um 16:30 Uhr.",
        "Bitte überarbeiten Sie Ihren Antrag entsprechend und senden Sie ihn "
        "anschließend erneut zur Genehmigung. Bitte beachten Sie, dass "
        "Dienstreisen erst nach abschließender Genehmigung durch die zuständige "
        "Instanz durchgeführt werden dürfen.",
        "Mit freundlichen Grüßen<br/>i. A. Corinna Delfs<br/>"
        "Abteilung Personal und Organisation &#183; Reisekostenstelle",
    ],
)

# =========================================================================== #
#                                  CASE 04                                    #
#      angenommen: Dienstreise + privater Anschluss, Kosten sauber getrennt   #
# =========================================================================== #

C4 = os.path.join(ROOT, "dienstreiseantrag-04")

antrag_pdf(
    os.path.join(C4, "antrag-dienstreisegenehmigung.pdf"),
    reisenummer="3381029444", name="Dr. Tobias Rehmann",
    fachgebiet="Fachgebiet Photonik", personalnummer="039215",
    status="Antrag eingereicht", geaendert_am="3. Juni 2026",
    genehmigt_von="---",
    allgemein=[
        ("Reiseziel:", "Barcelona, SPANIEN"),
        ("Anlass:", "PhotonicsConnect 2026"),
        ("Grund der Reise:", "Eingeladener Vortrag &#8222;Integrated Photonic "
                             "Sensing at Scale&#8220;"),
        ("Reise ins Ausland:", "[X] ja &#160;&#160; [ ] nein"),
        ("Verkehrsmittel:", "Flug (Economy), Hin- und Rückflug"),
        ("Datum der Antragstellung:", "03.06.2026"),
    ],
    verlauf=[
        ("Start:", "Montag, 7. September 2026, 06:00 Uhr (Abreise vom Wohnort)"),
        ("Ende:", "Donnerstag, 17. September 2026, 22:00 Uhr (Rückkehr zum Wohnort)"),
        ("Beginn Dienstgeschäft:", "07.09.2026, 09:00 Uhr"),
        ("Ende Dienstgeschäft:", "10.09.2026, 18:00 Uhr"),
        ("priv. Aufenthalt:", "11.09.2026 bis 16.09.2026 (6 Arbeitstage, im "
                              "Anschluss an das Dienstgeschäft, privat veranlasst)"),
        ("Arbeitstage:", "4 (Anreise + Konferenz)"),
        ("A1-Bescheinigung:", "beantragt am 03.06.2026"),
    ],
    kosten=[
        ("Hinflug Frankfurt&#8211;Barcelona, 07.09.2026, Economy", "1", "210,00 &#8364;"),
        ("Rückflug Barcelona&#8211;Frankfurt, Vergleichstarif zum dienstlichen "
         "Rückreisetag 10.09.2026 (erstattungsfähiger Anteil)", "1", "195,00 &#8364;"),
        ("Unterkunft Konferenzhotel, 3 Nächte (07.&#8211;10.09.), à 80,00 &#8364;",
         "3", "240,00 &#8364;"),
        ("Konferenzgebühr (Invited Speaker Rate)", "1", "380,00 &#8364;"),
        ("Transfer Flughafen &#8211; Konferenzhotel, Hin- und Rückweg", "2",
         "35,00 &#8364;"),
    ],
    kosten_total=("Summe der dienstlich veranlassten Kosten (zur Erstattung "
                  "beantragt)", "1.060,00 &#8364;"),
    finanzierung="Fachgebietsbudget Photonik, Kostenstelle 4890-02",
    begruendung="Eingeladener Vortrag auf der PhotonicsConnect 2026; das "
                "erhebliche dienstliche Interesse ergibt sich aus der Einladung "
                "des Programmkomitees (liegt bei). Im Anschluss an das "
                "Dienstgeschäft nehme ich vom 11. bis 16.09.2026 Erholungsurlaub "
                "in Barcelona (Urlaubsantrag separat gestellt).",
    hinweis="Der private Anschlussaufenthalt umfasst <b>mehr als fünf "
            "Arbeitstage</b>. Nach der Reisekostenregelung sind daher nur die "
            "Kosten erstattungsfähig, die im direkten Zusammenhang mit dem "
            "Dienstgeschäft entstanden sind. Ich beantrage entsprechend "
            "ausschließlich den dienstlich veranlassten Anteil: den Hinflug, den "
            "Rückflug <b>zum Vergleichstarif des dienstlichen Rückreisetags "
            "(10.09.2026)</b>, drei Übernachtungen und die Konferenzgebühr. "
            "Die sechs privaten Übernachtungen (480,00 EUR) sowie den "
            "Mehrpreis des späteren Rückflugs am 17.09.2026 (40,00 EUR) trage "
            "ich selbst; der Preisvergleich liegt bei.",
    antragsdatum="03.06.2026", pages_note="Seite 1 von 2",
)

email_pdf(
    os.path.join(C4, "email-einladung-vortrag.pdf"),
    mailbox="tobias.rehmann@uni-kassel.de",
    url="https://outlook.office.example/mail/id/AAQkAH",
    subject="PhotonicsConnect 2026 &#8211; Invitation as keynote speaker",
    sender="PhotonicsConnect 2026 Steering Committee &lt;chairs@photonicsconnect.example&gt;",
    sent="Di 19.05.2026 17:03",
    to="Tobias Rehmann &lt;tobias.rehmann@uni-kassel.de&gt;",
    body=[
        "Dear Dr. Rehmann,",
        "on behalf of the steering committee it is our pleasure to invite you to "
        "deliver an <b>invited keynote talk</b> at PhotonicsConnect 2026, "
        "Barcelona, 8&#8211;10 September 2026.",
        "We would like to propose the title &#8222;Integrated Photonic Sensing at "
        "Scale&#8220;, based on your recent work, for the opening session on "
        "8 September. The slot is 40 minutes plus discussion.",
        "As an invited speaker your registration is charged at the reduced invited "
        "speaker rate of 380 EUR. Unfortunately our budget does not allow us to "
        "cover travel or accommodation this year; we hope your institution can "
        "support your participation.",
        "Please let us know by 15 June 2026 whether you accept.",
        "With best regards,<br/>The PhotonicsConnect 2026 Steering Committee",
    ],
)

invoice_pdf(
    os.path.join(C4, "flug-preisvergleich.pdf"),
    vendor="Reisebüro Campus Kassel GmbH",
    vendor_addr=["Königsplatz 47", "34117 Kassel", "",
                 "Rahmenvertragspartner der Universität Kassel"],
    recipient=["Universität Kassel", "Fachgebiet Photonik",
               "z. Hd. Dr. Tobias Rehmann", "34121 Kassel"],
    refs=[("Angebotsnummer:", "RCK-2026-1188"), ("Angebotsdatum:", "02.06.2026"),
          ("Gültig bis:", "16.06.2026")],
    heading="Preisvergleich Rückflug",
    intro="Anfrage: Barcelona (BCN) &#8594; Frankfurt (FRA), Economy, 1 Person "
          "&#183; Vergleich dienstlicher vs. privat verlängerter Rückreisetag",
    items=[
        ["<b>Variante A</b> &#8211; Rückflug am dienstlichen Rückreisetag "
         "10.09.2026, 19:40 Uhr (Nordluft Airlines NL 4471)",
         "1", "&#8212;", "195,00 &#8364;", "195,00 &#8364;"],
        ["<b>Variante B</b> &#8211; Rückflug nach privatem Anschlussaufenthalt am "
         "17.09.2026, 20:15 Uhr (Nordluft Airlines NL 4487)",
         "1", "&#8212;", "235,00 &#8364;", "235,00 &#8364;"],
        ["Differenz Variante B &#8211; Variante A (privat veranlasster Mehrpreis)",
         "&#8212;", "&#8212;", "40,00 &#8364;", "<b>40,00 &#8364;</b>"],
    ],
    sums=[("Erstattungsfähiger Anteil (Variante A)", "195,00 &#8364;"),
          ("Privat zu tragender Mehrpreis", "40,00 &#8364;"),
          ("Gesamtpreis der gebuchten Variante B", "235,00 &#8364;")],
    notes=["Der Preisvergleich wurde am 02.06.2026 zu identischen Buchungsklassen "
           "und Konditionen erstellt. Er dient als Nachweis, dass durch die private "
           "Verlängerung keine Mehrkosten zulasten der Universität entstehen.",
           "Hinflug (Variante A und B identisch): Frankfurt (FRA) &#8594; Barcelona "
           "(BCN), 07.09.2026, 08:25 Uhr, 210,00 EUR."],
    closing="Mit freundlichen Grüßen",
)

invoice_pdf(
    os.path.join(C4, "hotel-buchungsbestaetigung.pdf"),
    vendor="Hotel Diagonal Congress S.L.",
    vendor_addr=["Avinguda Diagonal 412", "08037 Barcelona", "Spanien", "",
                 "NIF B65442017"],
    recipient=["Dr. Tobias Rehmann", "Universität Kassel", "Fachgebiet Photonik",
               "34121 Kassel, Deutschland"],
    refs=[("Buchungsnummer:", "HDC-2026-77140"), ("Buchungsdatum:", "02.06.2026"),
          ("Status:", "bestätigt, Zahlung bei Abreise")],
    heading="Buchungsbestätigung",
    intro="Konferenzhotel der PhotonicsConnect 2026 &#183; Einzelzimmer &#183; "
          "zwei getrennte Buchungen (dienstlich / privat)",
    items=[
        ["<b>Buchung 1 (dienstlich)</b> &#8211; 07.09.&#8211;10.09.2026, 3 Nächte "
         "à 80,00 EUR, Konferenztarif", "3", "10 % (ES)", "218,18 &#8364;",
         "240,00 &#8364;"],
        ["<b>Buchung 2 (privat, selbst zu zahlen)</b> &#8211; "
         "11.09.&#8211;16.09.2026, 6 Nächte à 80,00 &#8364;", "6", "10 % (ES)",
         "436,36 &#8364;", "480,00 &#8364;"],
    ],
    sums=[("Buchung 1 &#8211; Rechnung an die Universität Kassel", "240,00 &#8364;"),
          ("Buchung 2 &#8211; Rechnung an den Gast persönlich", "480,00 &#8364;"),
          ("Gesamt", "720,00 &#8364;")],
    notes=["Auf Wunsch des Gastes werden zwei getrennte Rechnungen ausgestellt. "
           "Buchung 1 lautet auf die Universität Kassel, Buchung 2 auf den Gast.",
           "Der Zimmerpreis von 80,00 &#8364; entspricht dem Konferenztarif und "
           "liegt innerhalb der Höchstgrenze des Auslandsübernachtungsgeldes für "
           "Spanien."],
    closing="Atentamente,",
)

email_pdf(
    os.path.join(TRAIL, "dienstreiseantrag-04", "genehmigt.pdf"),
    mailbox="tobias.rehmann@uni-kassel.de",
    url="https://outlook.office.example/mail/id/AAQkAI",
    subject="[Extern] Ihr Dienstreiseantrag 3381029444 wurde genehmigt",
    sender="ESS-Reisemanagement, Universität Kassel &lt;noreply-ess@uni-kassel.de&gt;",
    sent="Mi 10.06.2026 07:48",
    to="Tobias Rehmann &lt;tobias.rehmann@uni-kassel.de&gt;",
    cc="Prof. Dr. Peter Marquardt &lt;p.marquardt@uni-kassel.de&gt;",
    body=[
        "Guten Tag,",
        "Ihr Antrag auf Genehmigung einer Dienstreise (Reisenummer 3381029444) "
        "wurde genehmigt.",
        "<b>Anmerkung der genehmigenden Instanz:</b> Die Verbindung der Dienstreise "
        "mit einem privaten Aufenthalt von mehr als fünf Arbeitstagen wurde "
        "geprüft. Da ausschließlich die dienstlich veranlassten Kosten beantragt "
        "wurden und der Preisvergleich für den Rückflug vorliegt, entstehen der "
        "Universität keine Mehrkosten aus der privaten Verlängerung. Der Antrag "
        "ist insoweit nicht zu beanstanden.",
        "Die folgenden Hinweise sind Bestandteil der Dienstreisegenehmigung:",
        "&#8226; Bei der Verbindung von Dienstreisen mit privaten Aufenthalten sind "
        "die anlässlich des privaten Aufenthalts entstehenden Kosten nicht "
        "erstattungsfähig. Wird eine Dienstreise mit einem privaten Aufenthalt von "
        "mehr als fünf Arbeitstagen verbunden, sind nur die zusätzlichen Kosten "
        "erstattungsfähig, die im direkten Zusammenhang mit dem Dienstgeschäft "
        "entstanden sind.",
        "&#8226; Der Preisvergleich ist der Reisekostenabrechnung erneut beizufügen.",
        "&#8226; Die Reisekostenabrechnung ist innerhalb der Ausschlussfrist von "
        "sechs Monaten nach Reiseende einzureichen.",
        "Mit freundlichen Grüßen<br/>ESS-Reisemanagement<br/>"
        "Universität Kassel &#183; Abteilung Personal und Organisation",
    ],
)

# =========================================================================== #
#                                  CASE 05                                    #
#            abgelehnt: doppelte Kostenübernahme (Stipendium)                 #
# =========================================================================== #

C5 = os.path.join(ROOT, "dienstreiseantrag-05")

antrag_pdf(
    os.path.join(C5, "antrag-dienstreisegenehmigung.pdf"),
    reisenummer="3381029445", name="Finn Osterkamp",
    fachgebiet="Fachgebiet Materialwissenschaften", personalnummer="061033",
    status="Antrag eingereicht", geaendert_am="14. Juli 2026",
    genehmigt_von="---",
    allgemein=[
        ("Reiseziel:", "Boston, USA"),
        ("Anlass:", "MRS Fall Meeting 2026"),
        ("Grund der Reise:", "Posterbeitrag im Rahmen des Promotionsprojekts"),
        ("Reise ins Ausland:", "[X] ja &#160;&#160; [ ] nein"),
        ("Verkehrsmittel:", "Flug (Economy)"),
        ("Datum der Antragstellung:", "14.07.2026"),
    ],
    verlauf=[
        ("Start:", "Sonntag, 29. November 2026, 08:40 Uhr (Abreise vom Wohnort)"),
        ("Ende:", "Freitag, 4. Dezember 2026, 21:30 Uhr (Rückkehr zum Wohnort)"),
        ("Beginn Dienstgeschäft:", "30.11.2026, 09:00 Uhr"),
        ("Ende Dienstgeschäft:", "03.12.2026, 18:00 Uhr"),
        ("priv. Aufenthalt:", "keiner"),
        ("Arbeitstage:", "6 (Anreise + 4 Konferenztage + Abreise)"),
    ],
    kosten=[("Flug Frankfurt&#8211;Boston, Hin- und Rückflug, Economy", "1",
             "780,00 &#8364;"),
            ("Konferenzregistrierung (Student Rate)", "1", "420,00 &#8364;"),
            ("Unterkunft, 5 Nächte à 130,00 &#8364;", "5", "650,00 &#8364;"),
            ("Transfer / Nahverkehr vor Ort", "1", "60,00 &#8364;")],
    kosten_total=("Summe (Schätzung), zur vollständigen Erstattung beantragt",
                  "1.910,00 &#8364;"),
    finanzierung="Lehrstuhlbudget Materialwissenschaften, Kostenstelle 4720-06 "
                 "(volle Summe)",
    begruendung="Vorstellung eines Posters aus dem Promotionsprojekt auf dem MRS "
                "Fall Meeting, einer der wichtigsten Fachtagungen im Bereich. Der "
                "Beitrag ist Teil der kumulativen Dissertation. Ich bitte um "
                "vollständige Übernahme der Reisekosten durch das Fachgebiet.",
    antragsdatum="14.07.2026",
)

email_pdf(
    os.path.join(C5, "email-stipendienzusage.pdf"),
    mailbox="finn.osterkamp@uni-kassel.de",
    url="https://outlook.office.example/mail/id/AAQkAJ",
    subject="Nachwuchsreisestipendium &#8211; Zusage MRS Fall Meeting 2026",
    sender="Geschäftsstelle Nachwuchsförderung, DGMK e. V. "
           "&lt;travelgrants@dgmk-nachwuchs.example&gt;",
    sent="Di 30.06.2026 14:12",
    to="Finn Osterkamp &lt;finn.osterkamp@uni-kassel.de&gt;",
    body=[
        "Sehr geehrter Herr Osterkamp,",
        "wir freuen uns, Ihnen mitteilen zu können, dass Ihnen für Ihre Teilnahme "
        "am MRS Fall Meeting 2026 in Boston ein <b>Nachwuchsreisestipendium in "
        "Höhe von bis zu 1.200 USD</b> zuerkannt wurde.",
        "Das Stipendium ist zur Deckung von <b>Flug, Unterkunft und "
        "Konferenzregistrierung</b> bestimmt. Die Auszahlung erfolgt nach der "
        "Reise gegen Vorlage der Originalbelege direkt an Sie.",
        "<b>Wichtiger Hinweis:</b> Eine Doppelfinanzierung derselben Kostenpositionen "
        "ist ausgeschlossen. Sofern Ihre Hochschule Kosten übernimmt, sind die "
        "betreffenden Positionen bei der Abrechnung mit uns entsprechend zu "
        "kürzen. Bitte informieren Sie Ihre Reisekostenstelle über diese Zusage.",
        "Wir wünschen Ihnen einen erfolgreichen Kongressbeitrag.",
        "Mit freundlichen Grüßen<br/>Geschäftsstelle Nachwuchsförderung",
    ],
)

invoice_pdf(
    os.path.join(C5, "konferenz-registrierung.pdf"),
    vendor="MRS Fall Meeting 2026 Registration Office",
    vendor_addr=["c/o Meeting Services Inc.", "506 Keystone Drive",
                 "Warrendale, PA 15086", "USA"],
    recipient=["Finn Osterkamp", "University of Kassel",
               "Dept. of Materials Science", "34121 Kassel, Germany"],
    refs=[("Registration ID:", "FM26-STU-20884"), ("Invoice No.:", "FM26-I-20884"),
          ("Invoice date:", "10.07.2026")],
    heading="Registration Invoice",
    intro="MRS Fall Meeting 2026, Boston MA, 29 November &#8211; 4 December 2026 "
          "&#183; Poster contribution QM04.11.07",
    items=[["Student registration, full meeting", "1", "&#8212;", "420,00 &#8364;",
            "420,00 &#8364;"]],
    sums=[("Total due", "420,00 &#8364;")],
    payment=[("Zahlungsziel", "15.09.2026"), ("Art der Transaktion", "Überweisung"),
             ("Betrag", "420,00 &#8364;"), ("Status", "offen")],
    notes=["Registration is confirmed upon receipt of payment. Cancellation is "
           "free of charge until 15 October 2026."],
    closing="Sincerely,",
)

invoice_pdf(
    os.path.join(C5, "flug-angebot.pdf"),
    vendor="Reisebüro Campus Kassel GmbH",
    vendor_addr=["Königsplatz 47", "34117 Kassel", "",
                 "Rahmenvertragspartner der Universität Kassel"],
    recipient=["Universität Kassel", "Fachgebiet Materialwissenschaften",
               "z. Hd. Finn Osterkamp", "34121 Kassel"],
    refs=[("Angebotsnummer:", "RCK-2026-1402"), ("Angebotsdatum:", "09.07.2026"),
          ("Gültig bis:", "23.07.2026")],
    heading="Flugangebot",
    intro="Frankfurt (FRA) &#8211; Boston (BOS) &#8211; Frankfurt (FRA), Economy, "
          "1 Person",
    items=[["Hinflug FRA &#8594; BOS, 29.11.2026, 10:35 Uhr, Nordluft Airlines "
            "NL 8412, Economy", "1", "&#8212;", "395,00 &#8364;", "395,00 &#8364;"],
           ["Rückflug BOS &#8594; FRA, 04.12.2026, 18:50 Uhr, Nordluft Airlines "
            "NL 8413, Economy", "1", "&#8212;", "385,00 &#8364;", "385,00 &#8364;"]],
    sums=[("Summe", "780,00 &#8364;")],
    notes=["Es wurde die günstigste zumutbare Verbindung in der Economy-Klasse "
           "angeboten. Ein Upgrade wurde nicht angefragt."],
    closing="Mit freundlichen Grüßen",
)

email_pdf(
    os.path.join(TRAIL, "dienstreiseantrag-05", "email-rueckfrage-reisekostenstelle.pdf"),
    mailbox="finn.osterkamp@uni-kassel.de",
    url="https://outlook.office.example/mail/id/AAQkAK",
    subject="[Extern] Ihr Dienstreiseantrag 3381029445 &#8211; Rückfrage zur Finanzierung",
    sender="Reisekostenstelle, Universität Kassel &lt;dienstreisegenehmigung@uni-kassel.de&gt;",
    sent="Do 16.07.2026 10:31",
    to="Finn Osterkamp &lt;finn.osterkamp@uni-kassel.de&gt;",
    cc="Prof. Dr. Insa Dornberg &lt;i.dornberg@uni-kassel.de&gt;",
    body=[
        "Sehr geehrter Herr Osterkamp,",
        "vielen Dank für Ihren Antrag (Reisenummer 3381029445). Bei der Prüfung "
        "ist uns aufgefallen, dass Ihrem Antrag eine Stipendienzusage über bis zu "
        "1.200 USD beiliegt, die ausdrücklich <b>Flug, Unterkunft und "
        "Konferenzregistrierung</b> abdeckt.",
        "Im Feld &#8222;Finanzierung&#8220; ist gleichwohl die vollständige "
        "Übernahme der Reisekosten in Höhe von 1.910,00 &#8364; durch das "
        "Lehrstuhlbudget beantragt; eine Anrechnung des Stipendiums ist der "
        "Kostenaufstellung nicht zu entnehmen.",
        "Dieselben Kostenpositionen können nicht zweimal erstattet werden. Bitte "
        "reichen Sie eine korrigierte Kostenaufstellung ein, die ausweist, welche "
        "Positionen durch das Stipendium gedeckt sind und welcher Restbetrag "
        "tatsächlich von der Universität zu tragen ist. Der Antrag kann in der "
        "vorliegenden Form nicht genehmigt werden.",
        "Mit freundlichen Grüßen<br/>i. A. Corinna Delfs<br/>"
        "Abteilung Personal und Organisation &#183; Reisekostenstelle",
    ],
)

print("\ndone")
