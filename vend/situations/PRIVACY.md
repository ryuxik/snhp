# What the helper keeps, and why we think it isn't personal information

Written to be checked, not to reassure. If a claim here is wrong, the
right response is to change the code, not the page.

**Status: off by default.** Nothing is collected unless an operator sets
`SNHP_HELPER_TELEMETRY=1`. `/rent` collects nothing at all and its
no-storage promise stays true.

## Why collect anything

`writing/rent-no-source.md` went looking for what landlords actually
concede — rent, versus a free month, versus a waived fee, versus a term
deal — and found a blank. The largest renter survey in the country
(Zillow's, 21,000+ renters) never asks whether you negotiated. The only
usable numbers trace to a single 2022 Avail survey via the Urban
Institute.

So the dataset that would settle the question does not exist, and a tool
handing this advice to real people is sitting on the collection
mechanism for it. That is the entire justification. If the data does not
answer that question it should not be collected.

## The choke point

Everything written passes through `telemetry.redact()`, which is an
**allowlist, not a filter**. A field absent from `FIELD_BUCKETS` does not
survive, so adding a field to a situation loses telemetry rather than
leaking it.

`redact()`'s signature does not accept the person's description, a
request object, an IP, a user agent, or a session. The unsafe data is
structurally unavailable rather than filtered — this is enforced by
`test_the_description_cannot_be_recorded_by_accident`, which inspects the
signature.

## Never stored

| | why it matters |
|---|---|
| The description in their own words | The largest PII risk by far. People write addresses, landlord names, and their whole situation into a free-text box. Not a parameter of `redact()`. |
| Any exact figure | An exact rent + metro + lease length approaches a fingerprint. Everything is banded first. |
| Address, name, email, phone | Never collected anywhere in the product. |
| IP, user agent, referrer | Not passed to the module. |
| Cookies, accounts, device IDs | The tool has none. |
| Time finer than the calendar month | See below — this was the weakest link. |

## Re-identification analysis

**The cell space.** A record is: situation (2) × metro (50 + unknown) ×
rent band (6) × months band (6) × verdict (3) × a few booleans and closed
choices. Order 10⁴–10⁵ cells against a US renter population of ~44
million, concentrated in the 50 largest metros. A cell is a population,
not a person.

**Metro is the coarsest useful geography and we go no finer.** A metro
is millions of people — the granularity Zillow publishes at. No
neighbourhood, no borough, no postcode. "Brooklyn" normalises to the New
York metro before anything is written.

**Time was the real risk, and it was fixed.** The first cut stored the
calendar day. Day-level time is the classic re-identification vector: a
rare band combination plus a specific date approaches a singleton even
when every other field is coarse — *the one person in Buffalo who used
this on a Tuesday*. Now month only, asserted by
`test_timestamps_are_never_finer_than_a_month`.

**The receipt.** A record carries a random 16-hex token so a person can
later report what happened. It is generated per answer, not per person;
it is not derived from any input (identical inputs produce different
tokens, asserted by test); it is never stored alongside anything
identifying; and holding it lets you attach an outcome to one bucketed
row and do nothing else. It gives *us* no ability to recognise anyone.

**Residual risk, stated plainly.** At very low volume — the first weeks
after launch — a cell could contain one record. That is not
identification (there is nothing in the row that names a person) but it
weakens the population argument. If this ships, the honest mitigations
are to hold records until a cell has several members, or to publish only
aggregates above a threshold. Neither is implemented. **This is the open
item.**

## Legal posture

Not legal advice about ourselves; this is the analysis a lawyer would
want to start from.

**FTC Act §5 is the sharpest exposure, and it is a copy problem.**
Saying "nothing is stored" while storing something is deceptive
regardless of how anonymous the stored thing is. Every no-storage
promise about `/helper` was removed on the same change that added
collection, and `test_no_page_promises_that_nothing_is_stored` fails the
build if one comes back. `/rent` still stores nothing and still says so.

**CPRA** does not treat "we removed the name" as deidentification. It
requires reasonable measures against reassociation (bucketing, no free
text, no identifiers, month-level time), a **public commitment** to keep
the data deidentified and not attempt reassociation (`COMMITMENT` in
`telemetry.py`, served from `/v1/helper/privacy`), and no re-identification
attempts. Note CPRA's "personal information" reaches *households* — which
is why exact rent plus precise geography is exactly what we refuse to
keep. We do not sell, share with brokers or advertisers, or combine this
with any other dataset.

**GDPR Recital 26** asks whether re-identification is reasonably likely
by any means. With no free text, no IP, no cookie, no exact values and
month-level granularity, we assess that it is not — which would place
the data outside the Regulation. We are not relying on that assessment
alone: the collection is minimised as though it applied.

**Consent.** The helper has no accounts, so there is nothing to hang
account-level consent on the way `/v1/telemetry/*` does for the API.
Instead: off by default, disclosed on the page from the module that does
the redaction, and `no_telemetry: true` on any request opts out — checked
before the record is *built*, not before it is written
(`test_the_opt_out_is_honoured_before_anything_is_built`).

**Unauthorised practice of law** is the other real exposure, and it is
handled elsewhere: per-situation must-not-assert rules enforced on every
user-facing string, verification steps instead of legal conclusions, and
`NOT_ADVICE` on the page rather than only inside an answer.

## Before this is switched on

1. Implement the small-cell mitigation above, or accept and document the
   early-volume window.
2. Have a lawyer read this file and `telemetry.py` together.
3. Decide a retention period. Currently unbounded, which is defensible
   for genuinely deidentified data and is still a decision somebody
   should make on purpose.
4. Publish the aggregate findings. The justification for collecting this
   is that the answer does not exist; keeping it private would make that
   justification false.
