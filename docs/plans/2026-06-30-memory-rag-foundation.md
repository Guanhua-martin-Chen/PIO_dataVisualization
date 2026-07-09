# Memory And RAG Foundation

## What was implemented now

### Memory V1

- AI Analyst answers are now persisted automatically.
- Each saved memory stores:
  - question
  - focus part
  - risk level
  - answer
  - evidence
  - recommended actions
  - follow-up questions
  - used tools
  - warnings
  - mode
  - model
  - filter scope
- Storage is SQLite-based and lives in `outputs/analyst_memory.sqlite3`.
- The UI shows recent analyst memory per workbook sheet and allows replaying prior questions.

### RAG-ready foundation

- A `knowledge/` folder is now reserved for future retrieval documents.
- The project now distinguishes clearly between:
  - structured numeric tools
  - analyst memory
  - retrievable narrative/definition documents

### RAG V1 without extra files

- The AI Analyst now performs lightweight retrieval even if there are no extra business documents yet.
- Current retrieval sources are:
  - current filter scope
  - workbook field / schema profiles
  - anomaly-center records
  - forecast-center summaries
  - saved analyst memory from the same workbook sheet
  - optional markdown files under `knowledge/`
- Retrieved context is returned to the UI so each analyst answer shows what narrative context was pulled in.
- This keeps numeric facts in trusted tool calls while giving the product a practical first RAG layer.

## Why this is the right order

Memory gives immediate value because the same parts and questions will come back repeatedly. RAG should come after you have stable internal reference material worth retrieving.

## Recommended next step

1. Add real business documents under `knowledge/`
2. Build a simple document catalog and chunker
3. Add retrieval to AI Analyst only for:
   - metric definitions
   - SOP
   - method notes
   - past analysis memos

Do not move structured workbook facts into RAG. Keep numerical reasoning in tool calls.
