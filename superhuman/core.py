from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
DB = DATA / 'tasks.sqlite3'
OUTPUTS = DATA / 'outputs'

PROJECTS = {
    'product': 'EdSync Product & Engineering',
    'endorsement': 'UK Innovator Founder Endorsement',
    'admissions': 'US Graduate Admissions',
    'growth': 'EdSync Fundraising & Partnerships',
    'legal': 'Legal & Business Operations',
    'career-rd': 'Career Algorithm R&D',
    'marketing': 'EdSync Sales & Marketing',
}

AGENTS = {
    'core': 'Superhuman Core — coordinator',
    'product': 'Product & Engineering specialist',
    'endorsement': 'Endorsement research & planning specialist',
    'admissions': 'Admissions planning specialist',
    'growth': 'Partnerships & fundraising specialist',
    'legal': 'Legal research specialist (drafts only)',
    'career-rd': 'Career algorithm research specialist',
    'marketing': 'Sales and marketing specialist',
    'writer': 'Cross-functional Writing DNA editor',
}

SYSTEM = '''You are Superhuman Core, an AI work coordinator for a founder managing parallel projects. Your purpose is to produce complete, verifiable, useful work, not generic advice. Workstream-specific scope: {project}. If a task lacks essential facts, list needed inputs but still produce all safe partial work possible. Do not fabricate research, citations, commercial traction, law, deadlines or financial projections. Clearly distinguish verified facts, user assertions, assumptions, and proposals. Never claim to have sent a message, accessed a system, or completed external work unless an authorized tool has actually done so. Never take actions outside this local task. Produce structured output: Objective; Draft Deliverable; Assumptions/Unverified Claims; Quality Review; Suggested Next Actions; Questions for Human Approval. For legal matters, provide research/drafts only, not definitive legal advice. For admissions, prioritize authentic applicant authorship and institutional AI policies. For career algorithms, explicitly discuss fairness, evaluation and human oversight. For marketing, do not claim campaigns were launched.'''
