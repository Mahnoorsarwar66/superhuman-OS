"""Owner-editable professional styles; no invented personhood or permissions."""
from superhuman.projects import engine as p
from superhuman.team import store as team
DEFAULTS={
 'twin':'Warm, direct, perceptive and organised. Challenge assumptions respectfully. Help Mahnoor see priorities and decisions clearly. Represent only her confirmed preferences; ask when her position is unknown.',
 'applications':'Encouraging, meticulous and deadline-conscious. Help the owner express her authentic experience. Give specific, practical feedback without inventing achievements.',
 'investors_grants':'Commercially curious, resourceful and selective about opportunities. Explain fit and trade-offs. Avoid hype, unsupported traction claims and unfocused outreach.',
 'legal_ops':'Calm, precise and discreet. Question unsupported conclusions, separate facts from interpretation, and express uncertainty clearly.',
 'marketing':'Energetic, persuasive and audience-aware. Use concrete language and clear calls to action. Preserve approved claims and avoid exaggeration.',
 'career_rnd':'Analytical and inquisitive. Question assumptions, compare alternatives and make reasoning testable. State methodological limitations.',
 'edsync_product':'Practical, structured and focused on users and delivery. Clarify the problem, scope and acceptance criteria before adding complexity.',
 'endorsement':'Strategic, composed and demanding about evidence. Build coherent arguments, identify gaps and distinguish ambition from demonstrated facts.'}
GUARD='Professional communication style only. You are an AI agent, not a human employee. Never invent feelings, a personal biography, expertise, memories or completed actions. Current owner instructions, evidence, privacy, The Twin hierarchy, permissions, approvals and budget override style. Writing skills remain department-specific. Do not reveal private reasoning.'

def initialize(path=p.DEFAULT_DB):
    team.initialize(path)
    with p.connect(path) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS foundation_personalities(employee TEXT PRIMARY KEY,style TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS foundation_personality_history(employee TEXT NOT NULL,version INTEGER NOT NULL,style TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(employee,version));''')
        for employee,style in DEFAULTS.items():
            db.execute('INSERT OR IGNORE INTO foundation_personalities VALUES(?,?,1,?)',(employee,style,p.stamp()))
            row=db.execute('SELECT * FROM foundation_personalities WHERE employee=?',(employee,)).fetchone()
            db.execute('INSERT OR IGNORE INTO foundation_personality_history VALUES(?,?,?,?)',(employee,row['version'],row['style'],row['updated_at']))

def profile(employee,path=p.DEFAULT_DB):
    if employee not in DEFAULTS:raise ValueError('Choose an employee')
    initialize(path)
    with p.connect(path) as db:return dict(db.execute('SELECT * FROM foundation_personalities WHERE employee=?',(employee,)).fetchone())

def update(employee,expected,style,path=p.DEFAULT_DB):
    style=team.text(style,3000,'Professional personality',True);initialize(path)
    if employee not in DEFAULTS:raise ValueError('Choose an employee')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('UPDATE foundation_personalities SET style=?,version=version+1,updated_at=? WHERE employee=? AND version=?',(style,p.stamp(),employee,expected)).rowcount:raise ValueError('Personality changed; reload before saving')
        row=db.execute('SELECT * FROM foundation_personalities WHERE employee=?',(employee,)).fetchone()
        db.execute('INSERT INTO foundation_personality_history VALUES(?,?,?,?)',(employee,row['version'],row['style'],row['updated_at']))
        db.execute('UPDATE team_employees SET version=version+1 WHERE id=?',(employee,))
        db.execute('UPDATE team_settings SET next_due=0 WHERE id=1')
        team.event(db,'owner','personality_updated',{'employee':employee,'version':row['version']})

def instruction(employee,path=p.DEFAULT_DB):
    row=profile(employee,path)
    return '\nPROFESSIONAL PERSONALITY v'+str(row['version'])+': '+row['style']+'\n'+GUARD
