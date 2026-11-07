# Travel rules of the University of Wernstadt

The University of Wernstadt is fictional. Its business trips follow the rules of the University of Kassel, as in the UniAgent shared task. The sources are the Kassel intranet page "Dienstreisemanagement" (in the shared task corpus `university-kassel-public-de`) and the Hessian travel expenses act, Hessisches Reisekostengesetz or HRKG (in the corpus `hessian-law-de`). This sheet states, in English, every rule that decides the ground truth of the scenarios `travel-request` and `expense-claim`. Where the sources leave room, the sheet fixes one reading and marks it as a hackathon reading.

## 1 Travel requests: when a trip is refused

The decision is `reject` if one of these rules applies, and `approve` otherwise. Each refused trip in the data breaks exactly one of them. Rules that only cap a refund (a hotel above EUR 80, a private stay) never refuse a trip, and missing information is asked for, not refused.

| Code | Rule | Source |
|---|---|---|
| R1 | A trip must be approved before it starts. A request filed after the trip has started is refused. Exception: domestic trips of professors of up to seven days count as approved by office. | Kassel page; § 2 (1) HRKG; decision 656 of the Kassel presidium (21 July 2025), quoted on the page |
| R2 | Conferences and meetings held online are not business trips. | Kassel page |
| R3 | An honorarium for an activity on the trip (for example a talk) marks the trip as privately caused; it cannot be approved as a business trip. | Kassel page |
| R4 | No trips are approved to Russia, Ukraine, Belarus, the southern and eastern parts of Moldova that border Ukraine, Niger, Iran, Israel, the Palestinian territories, and Lebanon. | Kassel page |
| R5 | A business trip needs official business at the destination. Travelling without it (for example after the meeting was cancelled) is no business trip. | § 2 (1) HRKG |

## 2 Travel requests: what must be asked for

A field is `null` in the gold form and its name is listed in `missing` when neither the message nor the attachments give its value (for example `cost_centre`, `return_date`, `cost_accommodation`). Three more items go into `missing`:

| Item | Rule | Source |
|---|---|---|
| `invitation` | Every request needs an invitation, programme, or similar document that shows the official interest, the place, and the duration. | Kassel page |
| `hotel_justification` | A hotel in Germany above EUR 80 per night needs a written justification with the request. Without it, at most EUR 80 per night are refunded. | Kassel page |
| `flight_price_comparison` | A request for a flight needs an attached price comparison. | Kassel page |

## 3 Fields of the travel request form

| Field | Meaning |
|---|---|
| `traveler_name` | Name of the traveller, without academic titles. |
| `position` | Position as stated in the traveller's signature, for example "Research Associate" or "Professor". |
| `trip_type` | `domestic` (destination in Germany) or `abroad`. |
| `destination_city`, `destination_country` | City and country of the business, in English ("Munich", "Cologne", "Germany", "Lithuania"). |
| `purpose` | Title of the event or business as the invitation or the message names it. |
| `departure_date`, `return_date` | Day the traveller leaves home and day the traveller is back, including a private stay (ISO format, `2027-03-08`). |
| `transport` | Main means of transport: `train`, `bus`, `plane`, `private_car`, or `service_car` (car from the university car pool). |
| `cost_centre` | Cost centre as given, for example `6203 1147`. |
| `private_stay_start`, `private_stay_end` | First and last day of a private stay as the traveller states them, else `null`. |
| `third_party` | The cost types a third party pays or provides free of charge: any of `accommodation`, `transport`, `registration`, `meals`; empty list if none. |
| `cost_transport` | Sum of all fares (tickets, flights, the train to the airport). Private car: kilometres times EUR 0.35 if the traveller states a valid reason (for example heavy equipment, no public transport), else times EUR 0.21. Service car: 0. Paid by a third party: 0. |
| `cost_accommodation` | Nights times the rate of the hotel offer, also above EUR 80. Zero when the traveller stays privately, when a third party pays, or for a day trip. |
| `cost_registration` | The registration or course fee without optional extras such as a conference dinner. Zero if there is none or a third party pays it. |
| `cost_total` | Sum of the three costs; `null` if one of them is `null`. |

## 4 Expense claims: what is refunded

Expense claims exist for approved domestic trips only. The refund has five parts (`transport`, `accommodation`, `registration`, `per_diem`, `other`) and their `total`. Taxis and mileage count as `transport`; parking and optional extras count as `other`.

| Code | Rule | Source |
|---|---|---|
| E1 | A claim must arrive within six months after the trip. The period starts on the day after the return. A late claim gets nothing. | § 4 (5) HRKG; Kassel page |
| E2 | Tickets are refunded as paid, in the lowest class. A taxi is refunded if the claim gives a valid reason (for example no bus at night). Without a valid reason, at most the public transport fare that the claim states is refunded. | § 5 HRKG; Kassel page |
| E3 | Private car: EUR 0.21 per km, or EUR 0.35 per km if valid reasons were approved before the trip. Parking fees only in the second case. | § 6 HRKG; Kassel page |
| E4 | Hotel costs with an invoice: up to EUR 80 per night, more only if the necessity was justified in writing with the request. Without an invoice (for example staying with friends): EUR 20 per night, on request. Nothing if a third party paid the hotel. | § 8 HRKG; Kassel page |
| E5 | Registration fees are refunded. Optional extras such as conference dinner tickets are meals and are not refunded. | § 11 HRKG; Kassel page |
| E6 | Restaurant bills are not refunded; the per diem covers meals. | Kassel page |
| E7 | Per diem: EUR 14 for a single-day trip of more than 8 hours away from home, nothing for 8 hours or less. For a trip over several days, EUR 14 on the first and on the last day and EUR 28 for each day in between. The time away runs from leaving home to coming back. | § 7 HRKG with § 9 (4a) sentence 3 EStG; § 2 (2) HRKG |
| E7 (cuts) | Each meal that is provided free of charge (by a host, an organiser, or a hotel that a third party paid) or that is included in refunded costs (breakfast in the hotel price, lunch in the fee) cuts the per diem of that day: EUR 5.60 for breakfast, EUR 11.20 for lunch, EUR 11.20 for dinner. A day never goes below zero. Hotel breakfast belongs to the morning after each night. | § 10 HRKG; Kassel page |
| E8 | Private stay of up to five working days: the refund is computed as if only the business trip had taken place. Hotel and per diem are paid for the business days only, and the last business day counts as the day of return. The return ticket is refunded at most up to the fare of a return right after the business, if that fare is stated. | § 14 (1) HRKG; Kassel page |
| E9 | Costs paid for other people are refunded only for the traveller's own share. | Kassel page |
| E10 | Costs a third party has already reimbursed are not refunded again. | § 4 (3) HRKG; Kassel page |

## 5 Hackathon readings

- Trips abroad have no expense claims: per diem and hotel limits abroad follow federal tables that are not in the corpora.
- The per diem rates of EUR 14 and EUR 28 are the values of § 9 (4a) sentence 3 EStG as of 2026; § 7 HRKG refers to them.
- Itemised hotel breakfasts, first-class tickets, and private stays of more than five working days do not occur in the claims, because the sources leave their refund open to interpretation.
