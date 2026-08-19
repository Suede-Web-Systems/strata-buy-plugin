# Strata Buy Plugin

A Claude plugin for broadcast TV media buyers who work in **Strata VIEW**
(FreeWheel / Comcast Advertising). It reads station avails files (AAAA
`SpotTVCableProposal` "Proposal XML"), builds an optimized spot buy against
buyer-controlled rules, and produces a validated XML file ready to import
via VIEW's `File | Import | Proposal XML` — with a preflight that predicts
exactly what Strata will keep, before anything is sent.

Built and maintained by [Suede Web Systems](mailto:support@suedewebsystems.ai).
Open source under the MIT license — use it, fork it, tell us what breaks.

> **Disclaimer:** This project is not affiliated with, endorsed by, or
> supported by FreeWheel, Comcast, Strata, or the AAAA. "Strata" and
> related marks belong to their owners; they are used here only to describe
> what this toolkit interoperates with. The schemas in `schema/` are
> reverse-engineered from real files and are descriptive, not official.
> **Always verify imported buys against your own system of record** — a
> media buy is your responsibility, not this software's.

## What it does

| Skill | What it's for |
|---|---|
| `/strata-buy:ingest-avails` | Read a station/provider schedule file and report the market: stations, flight, demos, dayparts, and how much inventory is *actually buyable* (seller files routinely carry rate periods on days programs don't air). |
| `/strata-buy:build-buy` | Build an optimized buy (budget, target demo, station caps, news floor, overnight cap, daily coverage — all editable in a plain-text parameters file) and generate the Strata-ready XML by injecting spots into the seller file's own bytes. |
| `/strata-buy:preflight` | Validate any buy file and predict its post-import totals. Catches both hard rejections and Strata's **silent** dropping of spots placed on non-air days. Run it after every hand-tweak. |

The intended loop: **ingest → build → preflight → zip → import → compare
totals**. Each skill tells you the next step.

## Installing (one time)

In Claude Code:

```
/plugin marketplace add Suede-Web-Systems/strata-buy-plugin
/plugin install strata-buy@strata-buy-plugin
```

In Cowork (Claude desktop): open the plugin manager and add the marketplace
`Suede-Web-Systems/strata-buy-plugin`, then install **strata-buy**.

Requirements: Python 3 with `lxml` (parsing) and `pulp` (optimizer). The
skills install these automatically on first use; if `pulp` can't install,
the optimizer falls back to a clearly-labeled heuristic.

Updates: none needed on your side — when Suede publishes a fix, your Claude
picks it up automatically.

## What stays on your machine

The plugin ships **no client data** and expects none. Your rates, avails
files, and buy parameters live only in your working folder. The parameters
file (`buy-parameters.toml`, copied from `config/buy-parameters.template.toml`
on first run) is yours to edit — every optimizer rule is a commented,
plain-English setting.

## Strata references

FreeWheel's public documentation for the import path this toolkit targets:

- [VIEW for Media Buying — File Imports: Overview](https://freewheel.zendesk.com/hc/en-us/articles/33524456056333-VIEW-for-Media-Buying-File-Imports-Overview)
- [Importing Proposal XML files into VIEW](https://freewheel.zendesk.com/hc/en-us/articles/33524609269901-Importing-Proposal-XML-files-into-VIEW)
- [File Imports: Proposal XML file (.XML)](https://freewheel.zendesk.com/hc/en-us/articles/33524461793421-VIEW-for-Media-Buying-File-Imports-Proposal-XML-file-XML)
- [How to fix XML import issues](https://freewheel.zendesk.com/hc/en-us/articles/33524307903373-How-to-fix-XML-import-issues)
- [Importing Avails in Automated RFP](https://freewheel.zendesk.com/hc/en-us/articles/33524230361357-Importing-Avails-in-Automated-RFP)
- [proposalxml.com](https://www.proposalxml.com/) — the consortium standard the format follows (no public XSD; the schemas in `schema/` are reverse-engineered and descriptive)

## For maintainers (Suede)

Layout: three skills in `skills/`, all deterministic logic in `scripts/`
(shared parser in `proposal_lib.py`), reverse-engineered XSDs in `schema/`,
institutional knowledge in `reference/`. A synthetic end-to-end fixture
lives at `reference/examples/sample-avails.xml` (no client data).

Releasing a change:

1. Make the change; run the pipeline end-to-end against
   `reference/examples/sample-avails.xml` (parse → optimize → inject →
   validate → simulate; all gates must pass).
2. Add a CHANGELOG entry. If the change encodes a newly discovered Strata
   behavior, document the evidence in `reference/FORMAT.md`.
3. Bump `version` in `.claude-plugin/plugin.json` — this is what triggers
   client updates.
4. `claude plugin validate .` then push to `main`.

Test locally without installing: `claude --plugin-dir ./strata-buy-plugin`.
