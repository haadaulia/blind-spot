# Run BlindSpot
## Setup
    python -m venv .venv && .venv\Scripts\activate     # mac/linux: source .venv/bin/activate
    pip install -r requirements.txt
    copy .env.example .env      # then fill in SEC_API_KEY, SEC_IDENTITY, GROQ_API_KEY
## Web app (the demo)
    python -m uvicorn app:app --reload
    open http://127.0.0.1:8000
Use the two preset chips (cached = instant). First run of a NEW ticker fetches+extracts+verifies (slow on free Groq tier; caches after).
## CLI
    python smoke_test.py                 # TSLA vs F, GM, RIVN
    python smoke_test.py GS MS JPM BAC   # any target + peers
    python build_report.py               # static report.html from last run
## Notes
- Demo only from cached presets; don't type fresh tickers live (rate-limit hang).
- ABSENT findings are auto-verified against the target's full filing; still confirm at source.
- See LOOM_SCRIPT.md and GITHUB_AND_SUBMIT.md to finish the submission.
