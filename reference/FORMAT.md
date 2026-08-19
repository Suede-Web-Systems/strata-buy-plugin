# The Proposal XML format — what we know and how we know it

Working notes on the AAAA `SpotTVCableProposal` v0.3.0.5A format ("Proposal
XML") as Strata VIEW emits and imports it. Everything here was established
empirically from real files and confirmed import tests in August 2026, plus
FreeWheel's public KB. **There is no public canonical XSD** — proposalxml.com
describes the consortium standard but hosts no schema. The XSDs in
`../schema/` are reverse-engineered and descriptive: passing them is
necessary, not sufficient.

## Document shape

```
AAAA-Message                       (default ns .../spotTVCableProposal)
├── AAAA-Values                    SchemaName/Version/Media/BusinessObject/Action/UniqueMessageID
└── Proposal                       @uniqueIdentifier @version @sendDateTime @weekStartDay @startDate @endDate
    ├── Seller > Salesperson · Buyer · Advertiser > Product · Name · [SellerReference]
    ├── Outlets > TelevisionStation@callLetters/@outletId
    └── AvailList                  @startDate @endDate @identifier @isPackage
        ├── Name                   ← carries the SURVEY name (see Import behavior)
        ├── OutletReferences · DemoCategories · TargetDemo
        └── AvailLineWithDetailedPeriods*
            ├── OutletReference@outletFromListRef
            ├── DayTimes > DayTime > StartTime/EndTime/Days/ProgramName
            ├── DaypartName · AvailName · SpotLength · [Comment]
            └── Periods > DayDetailedPeriod* @startDate @endDate
                ├── Rate
                ├── [SpotsByDay]   ← THE BUY SIGNAL
                └── DemoValues > DemoValue@demoRef
```

## The buy signal: `<SpotsByDay>`

- Position matters: **after `<Rate>`, before `<DemoValues>`**. (A file with
  the spots after `DemoValues`, or using `<NumberOfSpots>`, was rejected
  outright by Strata: "Invalid Proposal XML file. Import stopped.")
- Seven children `Monday..Sunday` with integer counts; **omit the whole
  block** for unbought periods — Strata never emits all-zero blocks.
- **Namespace trap:** the weekday elements inside `<Days>` are in the
  `TVBGeneralTypes` (tvb-tp) namespace; the weekday elements inside
  `<SpotsByDay>` are in the **main proposal namespace**. Confusing the two
  produces a file that looks right and is wrong.
- Since periods are single-day, the only meaningful weekday column is the
  one matching the period's `startDate` — all others must be 0. (The
  toolkit predicts Strata drops spots in a mismatched column; that is
  inferred from this convention, not import-confirmed like the air-day
  rule — the confirmed 674/674 test covered non-air *days* only.)

## The air-day rule (the most expensive lesson)

**Strata VIEW silently drops any spot whose weekday is flagged `N` in the
line's `<Days>`.** No error, no warning — the import "succeeds" short.
Confirmed with a perfect 674/674-period separation and exact dollar
reconciliation on a real import (2026-08-18).

Corollary: seller avails routinely include rate periods on non-air days
(59% of periods in one real file). This is **phantom inventory** — it must
be masked before optimizing, and any CPP computed over it is fiction.

## Serialization conventions (match Strata's own output)

- CRLF line endings, tab indentation, double-quoted XML declaration
  (`<?xml version="1.0" encoding="UTF-8"?>`), non-alphabetized attributes
  in Strata's order, self-closing tags without a space (`<TargetDemo .../>`).
- `UniqueMessageID` = `ID` + 51–52 uppercase alphanumerics; regenerate it
  (and `sendDateTime`) on every new file.
- **Edit-in-place is the law:** inject spots into the source file's own
  bytes. Never re-serialize — buyers must return seller files with terms,
  comments, and rates unmodified, and re-serializers introduce exactly the
  deviations that get files rejected.

## Broadcast clock

Times run `05:00`–`29:59`; hour ≥ 24 is the small hours of the *next*
calendar day (28:00 = 4:00 AM). ~25% of lines use extended hours; a naive
time parse breaks. VIEW's broadcast day boundary has been 3:00 AM since
Nov 2015, which is why Strata XLS headers show 3 AM windows while the XML
uses the 5 AM-anchored clock.

## Import behavior (from FreeWheel KB + confirmed by test)

- Import path: VIEW `File | Import | Proposal XML file (*.xml, *.prx)`;
  also RFP Pre-Buy `Actions → Import Proposal XML`.
- **Dayparts:** seller daypart strings are *retained* on import (no
  cleaning needed to upload); validation only bites at SBMS submit, where
  "Reset Daypart Codes" is the documented fix.
- **Demos:** non-matching demos are *appended*, not rejected.
- **Survey binding:** if the survey named in `AvailList/Name` isn't
  installed, VIEW prompts for a substitute; declining cancels the import.
  Always carry the source file's exact survey name.
- **Merge:** merging into an active view requires matching flight dates,
  demos, and survey — otherwise the file lands as a *new* scheduler.
- **Transit:** zip XML before emailing (FreeWheel's own guidance; bare
  XML corrupts in transit and imports with wrong data rather than erroring).
- Imported ratings display `«` chevrons; these do not mean the data was
  altered.
