"""Local calendar behavior with saved synthetic reports, no provider/model requests."""
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import json
import re
import unittest
from uuid import uuid4
from test_dialogue import DialogueTests,DialogueWebTests
from superhuman.calendar import store as c,export
from superhuman.dialogue import store as d
from superhuman.projects import engine as p
from superhuman.mail import store as mail

START='2026-11-01T10:00:00+00:00'
END='2026-11-01T11:00:00+00:00'


def report(items=None,slot='personal_gmail',status='done',context=None):
    c.initialize();tid=d.create('marketing','Saved meeting report');turn=d.send(tid,'Prepare report',uuid4().hex)
    payload={'briefing':{'items':items if items is not None else [dict(headline='University discovery',reason='Invitation says this is a discovery meeting.',meeting_at=START,sources=['E1'])]}}
    snapshot=dict(account_id=slot,label=mail.SLOTS[slot][0],email='owner@example.com',captured_at=p.stamp(),messages=[dict(source_id=uuid4().hex,subject='Invitation',sender='Partner',sent_at=p.stamp(),body='Meet on 1 November 2026 at 10:00 UTC.')])
    key=uuid4().hex
    with p.connect() as db:
        db.execute('UPDATE dialogue_turns SET status=?,context_json=? WHERE id=?',(status,json.dumps(payload) if context is None else context,turn))
        db.execute('INSERT INTO mail_reports VALUES(?,?,?,?,?,?,?)',(key,slot,tid,turn,json.dumps(snapshot),p.stamp(),uuid4().hex))
    return key


def proposed():
    report();c.collect();return c.candidates()[0]


class CalendarTests(unittest.TestCase):
    setUp=DialogueTests.setUp
    tearDown=DialogueTests.tearDown
    def create(self,**kw):return c.create(kw.get('title','Meeting'),kw.get('start',START),kw.get('end',END),kw.get('notes',''),kw.get('key',uuid4().hex))
    def test_collect_is_review_only_and_idempotent(self):
        report();result=c.collect();self.assertEqual(result['added'],1);self.assertEqual(c.collect()['added'],0)
        self.assertEqual(c.events(),[]);self.assertEqual(len(c.candidates()),1)
    def test_all_four_accounts_keep_their_sources(self):
        for slot in mail.SLOTS:report(slot=slot)
        self.assertEqual(c.collect()['added'],4);self.assertEqual({r['account_id'] for r in c.candidates()},set(mail.SLOTS))
    def test_no_time_or_naive_time_is_not_guessed(self):
        report(items=[dict(headline='Deadline',reason='Submit tomorrow',meeting_at='',sources=['E1']),dict(headline='Meeting',reason='',meeting_at='2026-11-01T10:00',sources=['E1'])])
        self.assertEqual(c.collect()['unusable'],1);self.assertEqual(c.candidates(),[])
    def test_invalid_references_are_rejected(self):
        report(items=[dict(headline='Meeting',reason='',meeting_at=START,sources=['E2'])]);self.assertEqual(c.collect()['unusable'],1)
    def test_malformed_report_does_not_block_following_reports(self):
        report(context='{broken');report();result=c.collect();self.assertEqual(result['added'],1);self.assertEqual(result['unusable'],1)
    def test_pending_reports_collected_when_complete(self):
        report(status='queued');self.assertEqual(c.collect()['reports'],0)
        with p.connect() as db:db.execute("UPDATE dialogue_turns SET status='done' WHERE status='queued'")
        self.assertEqual(c.collect()['added'],1)
    def test_collection_is_concurrent_safe(self):
        report()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:c.collect(),range(2)))
        self.assertEqual(sum(r['added'] for r in results),1);self.assertEqual(len(c.candidates()),1)
    def test_confirm_edits_and_repeat_are_atomic(self):
        row=proposed();pid=c.confirm(row['id'],'Reviewed meeting',START,END,'Owner notes')
        self.assertEqual(pid,c.confirm(row['id'],'Reviewed meeting',START,END,'Owner notes'))
        self.assertEqual(c.get(pid)['title'],'Reviewed meeting');self.assertEqual(len(c.sources(pid)),1);self.assertEqual(c.candidates(),[])
    def test_concurrent_confirm_creates_one_event(self):
        row=proposed()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:c.confirm(row['id'],'Reviewed meeting',START,END,''),range(2)))
        self.assertEqual(results[0],results[1])
        with p.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM calendar_events').fetchone()[0],1)
    def test_dismissed_candidate_cannot_be_confirmed(self):
        row=proposed();c.dismiss(row['id']);c.dismiss(row['id'])
        with self.assertRaises(ValueError):c.confirm(row['id'],'Meeting',START,'','')
    def test_duplicate_link_preserves_existing_event(self):
        pid=self.create();row=proposed();c.link(row['id'],pid,1);c.link(row['id'],pid,1)
        self.assertEqual(c.get(pid)['title'],'Meeting');self.assertEqual(len(c.sources(pid)),1)
        self.assertEqual(len(c.events(now=datetime(2026,10,1,tzinfo=timezone.utc))),1)
    def test_stale_duplicate_link_refused(self):
        pid=self.create();row=proposed();c.update(pid,1,'Changed',START,END,'','confirmed')
        with self.assertRaises(ValueError):c.link(row['id'],pid,1)
        self.assertEqual(c.candidate(row['id'])['status'],'proposed')
    def test_owner_creation_idempotent(self):
        key=uuid4().hex;pid=self.create(key=key);self.assertEqual(pid,self.create(key=key))
        with self.assertRaises(ValueError):self.create(key=key,title='Different')
    def test_end_must_follow_start(self):
        with self.assertRaises(ValueError):self.create(end='2026-11-01T09:00:00Z')
    def test_timezone_is_normalized(self):
        self.assertEqual(c.instant('2026-11-01T15:00',local=True),START)
        self.assertEqual(c.instant('2026-11-01T15:00:00+05:00'),START)
        with self.assertRaises(ValueError):c.instant('2026-11-01T15:00')
    def test_tomorrow_uses_pakistan_day_boundary(self):
        self.create(start='2026-11-01T00:00:00+05:00',end='')
        self.create(start='2026-11-02T00:00:00+05:00',end='')
        self.assertEqual(len(c.tomorrow(now=datetime(2026,10,31,18,tzinfo=timezone.utc))),1)
    def test_ongoing_events_and_cancellation(self):
        pid=self.create();now=datetime(2026,11,1,10,30,tzinfo=timezone.utc)
        self.assertEqual(len(c.events(now=now)),1);self.assertEqual(c.events('past',now=now),[])
        c.update(pid,1,'Meeting',START,END,'','cancelled');self.assertEqual(c.events(now=now),[]);self.assertEqual(len(c.events('cancelled')),1)
        with self.assertRaises(ValueError):c.update(pid,1,'Meeting',START,END,'','confirmed')
    def test_conflicts_and_other_suggestions(self):
        pid=self.create();row=proposed();self.assertEqual(c.conflicts(START)[0]['id'],pid)
        report();c.collect();self.assertEqual(len(c.similar_candidates(row['id'])),1)
    def test_ical_escaping_and_octet_folding(self):
        pid=self.create(title='Meeting, café; '+('界'*30),notes='A\nBEGIN:VEVENT\nB; C, D\\E')
        data=export.event(c.get(pid));self.assertIn(b'DTSTART:20261101T100000Z',data)
        self.assertIn(b'\\nBEGIN:VEVENT',data);self.assertEqual(data.count(b'\r\nBEGIN:VEVENT\r\n'),1)
        self.assertTrue(all(len(line)<=75 for line in data.split(b'\r\n')))
        self.assertIn(b'DTEND:',data);self.assertNotIn(b'ATTENDEE',data);self.assertNotIn(b'VALARM',data)
    def test_unknown_end_stays_unknown(self):
        pid=self.create(end='');self.assertNotIn(b'DTEND:',export.event(c.get(pid)))
    def test_invalid_page_and_view(self):
        with self.assertRaises(ValueError):c.events('invalid')
        with self.assertRaises(ValueError):c.candidates(0)


class CalendarWebTests(unittest.TestCase):
    setUp=DialogueWebTests.setUp
    tearDown=DialogueWebTests.tearDown
    token=DialogueWebTests.token
    login=DialogueWebTests.login
    def test_calendar_and_export_require_authentication(self):
        for url in ('/calendar','/calendar/suggestions','/calendar/new','/calendar/event/id/download'):
            self.assertEqual(self.client.get(url,follow_redirects=False).status_code,303)
    def test_csrf_required_for_collection_and_meetings(self):
        self.login()
        for url in ('/calendar/collect','/calendar/create','/calendar/suggestion/id/confirm','/calendar/event/id/save'):
            self.assertEqual(self.client.post(url,data={}).status_code,403)
    def test_create_edit_export_flow_in_pakistan_time(self):
        csrf=self.login();page=self.client.get('/calendar/new');key=re.search('name="submission_key" value="([^"]+)"',page.text).group(1)
        data=dict(csrf=csrf,title='Owner meeting',start_at='2026-11-01T15:00',end_at='',notes='Owner notes',submission_key=key)
        response=self.client.post('/calendar/create',data=data,follow_redirects=False);self.assertEqual(response.status_code,303)
        pid=response.headers['location'].split('/')[-1];self.assertEqual(c.get(pid)['start_at'],START)
        result=self.client.get(response.headers['location']);self.assertIn('2026-11-01T15:00',result.text)
        download=self.client.get('/calendar/event/'+pid+'/download');self.assertEqual(download.status_code,200);self.assertIn('DTSTART:20261101T100000Z',download.text)
        self.assertIn('no-store',download.headers.get('cache-control',''))
    def test_collect_review_source_confirm_flow(self):
        csrf=self.login();report();result=self.client.post('/calendar/collect',data=dict(csrf=csrf));self.assertEqual(result.status_code,200)
        row=c.candidates()[0];page=self.client.get('/calendar/suggestion/'+row['id'])
        self.assertIn('/briefing/source/'+row['report_id']+'/E1',page.text)
        result=self.client.post('/calendar/suggestion/'+row['id']+'/confirm',data=dict(csrf=csrf,title='Verified meeting',start_at='2026-11-01T15:00',end_at='',notes='Checked original invitation'),follow_redirects=False)
        self.assertEqual(result.status_code,303);self.assertIn('Verified meeting',self.client.get(result.headers['location']).text)
    def test_html_escaped(self):
        self.login();pid=c.create('<img src=x onerror=bad()>',START,'','<script>bad</script>',uuid4().hex)
        result=self.client.get('/calendar/event/'+pid);self.assertNotIn('<script>bad',result.text);self.assertNotIn('<img src=x',result.text)
    def test_calendar_explains_local_reminder_limits(self):
        self.login();page=self.client.get('/calendar');self.assertIn('push notifications',page.text);self.assertIn('Tomorrow',page.text)
    def test_invalid_meeting_does_not_create(self):
        csrf=self.login();result=self.client.post('/calendar/create',data=dict(csrf=csrf,title='Meeting',start_at='wrong',submission_key=uuid4().hex))
        self.assertEqual(result.status_code,400);self.assertEqual(c.events(),[])
    def test_invalid_page(self):
        self.login();self.assertEqual(self.client.get('/calendar?view=invalid').status_code,400)


del DialogueTests,DialogueWebTests
