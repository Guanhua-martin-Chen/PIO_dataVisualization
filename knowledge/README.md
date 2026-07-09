# Knowledge Base

This folder is the RAG-ready document zone for the PIO Demand Intelligence Platform.

If this folder is still empty, the current RAG V1 falls back to workbook-derived context and saved analyst memory so the AI Analyst can still retrieve grounded narrative context.

## What belongs here

- Metric glossary
- Field definitions
- Planning SOP documents
- Forecast methodology notes
- Anomaly interpretation rules
- Business FAQ
- Analyst playbooks
- Historical analysis memos that are worth reusing

## What does NOT belong here

- Raw sales tables
- Full workbook exports
- Large structured fact tables that should stay in Pandas / API tools
- Files containing private secrets

## Recommended structure

- `knowledge/glossary/`
- `knowledge/sop/`
- `knowledge/methods/`
- `knowledge/memos/`

The future RAG layer should retrieve explanatory documents from this folder, while all business numbers continue to come from trusted structured tools.
