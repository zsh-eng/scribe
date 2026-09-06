"""Deterministic summary inputs and provenance, independent of the LLM client."""
from dataclasses import dataclass
import hashlib
import json

from prompts import PQ_PROMPT, SECTION_PROMPT, BILL_PROMPT, MEMBER_PROMPT

DEFAULT_MODEL = 'gemini-3.7-flash'
DEFAULT_INPUT_LIMIT = 20_000


def content_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class SummaryJob:
    kind: str
    entity_id: str
    prompt_key: str
    template: str
    inputs: dict
    summary: str | None

    @property
    def input_hash(self):
        return content_hash(json.dumps(self.inputs, sort_keys=True, ensure_ascii=False))

    @property
    def prompt_version(self):
        return content_hash(self.template)

    @property
    def prompt(self):
        return self.template.format(**self.inputs)

    @property
    def input_chars(self):
        return len(self.prompt)


def sitting_jobs(conn, start, end):
    rows = conn.execute('''
        SELECT sec.* FROM sections sec JOIN sittings s ON s.id=sec.sitting_id
        WHERE s.date BETWEEN ? AND ? AND length(sec.content_plain)>1500
        AND sec.category!='bill' AND sec.section_type NOT IN ('BI','BP')
        ORDER BY s.date, sec.section_order, sec.id
    ''', (start, end))
    for row in rows:
        question = row['category'] == 'question'
        yield SummaryJob('section', row['id'], 'question' if question else 'section',
                         PQ_PROMPT if question else SECTION_PROMPT,
                         {'title': row['section_title'], 'text': row['content_plain']}, row['summary'])
    bills = conn.execute('''
        SELECT DISTINCT b.id, b.title, b.summary FROM bills b
        JOIN sections sec ON sec.bill_id=b.id JOIN sittings s ON s.id=sec.sitting_id
        WHERE s.date BETWEEN ? AND ? AND sec.section_type='BP' ORDER BY b.id
    ''', (start, end)).fetchall()
    for bill in bills:
        rows = conn.execute('''
            SELECT sec.id, sec.content_plain FROM sections sec JOIN sittings s ON s.id=sec.sitting_id
            WHERE sec.bill_id=? ORDER BY s.date, sec.section_order, sec.id
        ''', (bill['id'],)).fetchall()
        text = '\n\n'.join(row['content_plain'] or '' for row in rows)
        if len(text) < 1500:
            continue
        yield SummaryJob('bill', bill['id'], 'bill', BILL_PROMPT,
                         {'title': bill['title'], 'text': text,
                          'source_ids': [row['id'] for row in rows]}, bill['summary'])


def member_jobs(conn):
    members = conn.execute('''
        SELECT m.id, m.name, ms.summary FROM members m
        LEFT JOIN member_summaries ms ON ms.member_id=m.id
        WHERE m.id IN (
            SELECT sa.member_id FROM sitting_attendance sa JOIN sittings s ON s.id=sa.sitting_id
            WHERE s.parliament=(SELECT MAX(parliament) FROM sittings)
        ) ORDER BY m.id
    ''').fetchall()
    for member in members:
        rows = conn.execute('''
            SELECT sec.id, sec.section_title, min.acronym AS ministry, ss.designation, s.date
            FROM section_speakers ss JOIN sections sec ON sec.id=ss.section_id
            JOIN sittings s ON s.id=sec.sitting_id LEFT JOIN ministries min ON min.id=sec.ministry_id
            WHERE ss.member_id=? ORDER BY s.date DESC, sec.section_order DESC, sec.id LIMIT 20
        ''', (member['id'],)).fetchall()
        if not rows:
            continue
        lines = [f"- {row['date']}: " + (f"[{row['ministry']}] " if row['ministry'] else '')
                 + row['section_title'] for row in rows]
        yield SummaryJob('member', member['id'], 'member', MEMBER_PROMPT,
                         {'name': member['name'], 'recent_designation': rows[0]['designation'] or 'MP',
                          'text': '\n'.join(lines), 'source_ids': [row['id'] for row in rows]}, member['summary'])


def save_attempt(conn, job, model, status, summary=None, error=None, usage=None):
    """A successful summary and its provenance commit together; failures retain prior text."""
    with conn:
        if status == 'success':
            if not summary:
                raise ValueError('Successful summaries must contain text')
            if job.kind == 'member':
                conn.execute('''INSERT INTO member_summaries(member_id, summary, last_updated)
                    VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(member_id) DO UPDATE SET
                    summary=excluded.summary, last_updated=excluded.last_updated''', (job.entity_id, summary))
            else:
                table = {'section': 'sections', 'bill': 'bills'}[job.kind]
                conn.execute(f'UPDATE {table} SET summary=? WHERE id=?', (summary, job.entity_id))
        conn.execute('''INSERT INTO summary_attempts
            (entity_type, entity_id, input_hash, prompt_key, prompt_version, model,
             status, summary_hash, input_chars, error, usage_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (job.kind, job.entity_id, job.input_hash, job.prompt_key, job.prompt_version, model,
             status, content_hash(summary) if summary else None, job.input_chars, error,
             json.dumps(usage) if usage else None))


def review_job(conn, job, model, input_limit):
    # Read-only review also works before an old database has been migrated.
    has_history = conn.execute("SELECT 1 FROM sqlite_master WHERE name='summary_attempts'").fetchone()
    successful = None
    latest = None
    if has_history:
        latest = conn.execute('''SELECT * FROM summary_attempts WHERE entity_type=? AND entity_id=?
                                ORDER BY id DESC LIMIT 1''', (job.kind, job.entity_id)).fetchone()
        if job.summary:
            successful = conn.execute('''SELECT * FROM summary_attempts
                WHERE entity_type=? AND entity_id=? AND status='success' AND summary_hash=?
                ORDER BY id DESC LIMIT 1''', (job.kind, job.entity_id, content_hash(job.summary))).fetchone()
    reasons = []
    if not job.summary:
        reasons.append('missing')
    elif successful is None:
        reasons.append('provenance_unknown')
    else:
        for key, expected in [('input_hash', job.input_hash), ('prompt_version', job.prompt_version), ('model', model)]:
            if successful[key] != expected:
                reasons.append({'input_hash': 'input_changed', 'prompt_version': 'prompt_changed', 'model': 'model_changed'}[key])
    if job.input_chars > input_limit:
        reasons.append('over_input_limit')
    return {'kind': job.kind, 'id': job.entity_id, 'reasons': reasons,
            'input_chars': job.input_chars,
            'generated_at': successful['created_at'] if successful else None,
            'model': successful['model'] if successful else None,
            'prompt_version': successful['prompt_version'] if successful else None,
            'last_attempt_status': latest['status'] if latest else None}
