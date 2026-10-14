# Superhuman OS — Starter v0.1

A local-first, approval-first foundation for a personal AI workforce.

## What works now
- Local SQLite task register (seven workstreams, shared writing specialist)
- Create, list and inspect tasks using a command-line interface
- Ask Superhuman Core to produce a research/draft plan (requires your OpenAI API key)
- Store execution output locally; **no email, payments, external publishing or external app actions**
- Every generated answer is marked as a draft pending human review

## Requirements
Python 3.10+ and an OpenAI API key to use the AI command (task management works without a key).

## Install
```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env  # on Windows copy .env.example .env
```
Edit `.env` and set `OPENAI_API_KEY` to your personal API key. **Never share that key in chat or commit it to git.**

## Run
```bash
python -m superhuman.cli init
python -m superhuman.cli add --project endorsement --title "Develop UK endorsement business plan outline" --details "Structure and evidence checklist"
python -m superhuman.cli list
python -m superhuman.cli run 1
python -m superhuman.cli show 1
```

`run` makes an AI request, writes the draft to `data/outputs/`, and changes task state to `needs_review`. No external actions are performed.

## Next engineering milestones
1. Document ingestion with explicit consent and per-project access control
2. Evidence-backed research agent with source citations and verification
3. User authentication, encrypted secrets vault, approval queue and audit log
4. Background task workers, retries, budgets and monitoring
5. Specialized integrations (email, calendar, files, repositories) with least privilege
6. Writing DNA evaluation suite and controlled agent quality testing

This is a **starter**, not a production-secure autonomous application. Do not upload confidential third-party or client data yet.
