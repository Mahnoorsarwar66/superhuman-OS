import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .core import DB, DATA, OUTPUTS, PROJECTS, SYSTEM


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute('''CREATE TABLE IF NOT EXISTS tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project TEXT NOT NULL,
      title TEXT NOT NULL,
      details TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'queued',
      output_file TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )''')
    con.commit()
    return con


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    p = argparse.ArgumentParser(description='Superhuman OS v0.1')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    add = sub.add_parser('add')
    add.add_argument('--project', choices=list(PROJECTS), required=True)
    add.add_argument('--title', required=True)
    add.add_argument('--details', default='')
    sub.add_parser('list')
    for op in ('show','run'):
        s = sub.add_parser(op)
        s.add_argument('id', type=int)
    args = p.parse_args()
    con = connect()
    if args.command == 'init':
        print('Initialized:', DB)
        print('Projects:', ', '.join(PROJECTS))
    elif args.command == 'add':
        stamp = now()
        cur = con.execute('INSERT INTO tasks(project,title,details,created_at,updated_at) VALUES(?,?,?,?,?)', (args.project,args.title,args.details,stamp,stamp))
        con.commit()
        print('Task created:', cur.lastrowid)
    elif args.command == 'list':
        for row in con.execute('SELECT id,project,status,title FROM tasks ORDER BY id DESC'):
            print(f"#{row['id']} [{row['project']}] {row['status']} — {row['title']}")
    else:
        row = con.execute('SELECT * FROM tasks WHERE id=?',(args.id,)).fetchone()
        if not row:
            raise SystemExit('Task not found')
        if args.command == 'show':
            print(dict(row))
            if row['output_file'] and Path(row['output_file']).exists():
                print('\n--- Draft output ---\n', Path(row['output_file']).read_text(encoding='utf8'))
        elif args.command == 'run':
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parent.parent / '.env')
            if not os.getenv('OPENAI_API_KEY'):
                raise SystemExit('Set OPENAI_API_KEY in .env before using run; other commands work without it.')
            from openai import OpenAI
            client = OpenAI()
            prompt = f"Project: {PROJECTS[row['project']]}\nTask: {row['title']}\nDetails: {row['details']}"
            model = os.getenv('OPENAI_MODEL','gpt-5-mini')
            response = client.responses.create(model=model, instructions=SYSTEM.format(project=PROJECTS[row['project']]), input=prompt)
            output = response.output_text
            OUTPUTS.mkdir(exist_ok=True, parents=True)
            dest = OUTPUTS / f"task_{row['id']}.md"
            dest.write_text('# DRAFT — HUMAN REVIEW REQUIRED\n\n'+output,encoding='utf8')
            con.execute('UPDATE tasks SET status=?,output_file=?,updated_at=? WHERE id=?', ('needs_review',str(dest),now(),row['id']))
            con.commit()
            print('Draft ready for review:',dest)
    con.close()

if __name__ == '__main__':
    main()
