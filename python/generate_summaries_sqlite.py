import asyncio
import logging
import os
import re
import sys

from google import genai
from datetime import datetime, timedelta
from dotenv import load_dotenv

import db_sqlite as db
from prompts import PQ_PROMPT, SECTION_PROMPT, BILL_PROMPT, MEMBER_PROMPT

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

client = genai.Client()

AI_SEMAPHORE = asyncio.Semaphore(20)  # Can do more parallel with Gemini but keeping safe limit
AI_COOLDOWN = 0.5                    # Adjust to Gemini rate limitations (15 RPM free, higher paid)

async def generate_summary(prompt_template: str, model='gemini-3.7-flash') -> str:
    async with AI_SEMAPHORE:
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt_template,
            )
            
            await asyncio.sleep(AI_COOLDOWN)
            
            if response.text:
                content = response.text.strip()
                # Normalize whitespace: replace multiple spaces/tabs/non-breaking spaces 
                # with single space but preserve newlines
                content = re.sub(r'[ \t\xa0]+', ' ', content)
                return content
            return None
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            await asyncio.sleep(AI_COOLDOWN)
            return None

async def generate_section_summaries_for_sitting(sitting_id, only_blanks):
    conn = db.get_connection()
    cursor = conn.cursor()
    query = '''
        SELECT id, section_title, content_plain, category, section_type 
        FROM sections    
        WHERE sitting_id = ? 
          AND length(content_plain) > 1500
          AND category != 'bill' 
          AND section_type NOT IN ('BI', 'BP')
    '''
    if only_blanks:
        query += ' AND summary IS NULL'
        
    cursor.execute(query, (sitting_id,))
    sections = [dict(row) for row in cursor.fetchall()]
    
    if not sections:
        return
        
    logger.info(f"Generating summaries for {len(sections)} sections in sitting {sitting_id}")
    
    tasks = []
    for s in sections:
        tasks.append(generate_section_summary(s))
        
        if len(tasks) >= 20:
            await asyncio.gather(*tasks)
            tasks = []
            
    if tasks:
        await asyncio.gather(*tasks)

async def generate_section_summary(section):
    prompt = PQ_PROMPT if section['category'] == 'question' else SECTION_PROMPT
    prompt = prompt.format(title=section['section_title'], text=section['content_plain'][:20000])
    
    summary = await generate_summary(prompt)
    
    if summary:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE sections SET summary = ? WHERE id = ?', (summary, section['id']))
        conn.commit()

async def generate_bill_summaries_for_sitting(sitting_id, only_blanks):
    conn = db.get_connection()
    cursor = conn.cursor()
    query = '''
        SELECT DISTINCT b.id, b.title 
        FROM bills b
        JOIN sections s ON b.id = s.bill_id
        WHERE s.sitting_id = ?
        AND s.section_type = 'BP'
    '''
    if only_blanks:
        query += ' AND b.summary IS NULL'
        
    cursor.execute(query, (sitting_id,))
    bills = [dict(row) for row in cursor.fetchall()]
    
    if not bills:
        return
        
    logger.info(f"Generating summaries for {len(bills)} bills in sitting {sitting_id}")
    
    for bill in bills:
        cursor.execute(
            '''SELECT content_plain FROM sections 
               WHERE bill_id = ? 
               ORDER BY section_order''',
            (bill['id'],)
        )
        sections = [row['content_plain'] for row in cursor.fetchall()]
        
        if not sections:
            continue
            
        full_text = "\n\n".join(sections)
        
        if len(full_text) < 1500:
            continue
        
        prompt = BILL_PROMPT.format(title=bill['title'], text=full_text[:20000])
        
        summary = await generate_summary(prompt)
        
        if summary:
            cursor.execute('UPDATE bills SET summary = ? WHERE id = ?', (summary, bill['id']))
            conn.commit()
            logger.info(f"Generated summary for bill {bill['title']}")

async def generate_sitting_summaries(start_date_str, end_date_str, only_blanks=False):
    start_date = datetime.strptime(start_date_str, '%d-%m-%Y')
    end_date = datetime.strptime(end_date_str, '%d-%m-%Y')
    
    dates = []
    curr = start_date
    while curr <= end_date:
        dates.append(curr.strftime('%Y-%m-%d'))
        curr += timedelta(days=1)
        
    logger.info(f"Summarizing date range: {start_date_str} to {end_date_str} ({len(dates)} days)")
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    iso_start = start_date.strftime('%Y-%m-%d')
    iso_end = end_date.strftime('%Y-%m-%d')
    
    cursor.execute(
        'SELECT id FROM sittings WHERE date >= ? AND date <= ?',
        (iso_start, iso_end)
    )
    sitting_ids_to_process = [row['id'] for row in cursor.fetchall()]
            
    logger.info(f"Generating summaries for {len(sitting_ids_to_process)} sittings...")
    
    for sid in sitting_ids_to_process:
        await generate_section_summaries_for_sitting(sid, only_blanks)
        await generate_bill_summaries_for_sitting(sid, only_blanks)

    logger.info("Batch processing complete!")
    db.close_connection()

async def generate_member_summaries(only_blanks):
    logger.info("Generating member summaries...")
    
    conn = db.get_connection()
    cursor = conn.cursor()
    # Only summarise members from the current (latest) parliament
    current_parl_filter = '''
        AND m.id IN (
            SELECT DISTINCT sa.member_id FROM sitting_attendance sa
            JOIN sittings s ON sa.sitting_id = s.id
            WHERE s.parliament = (SELECT MAX(parliament) FROM sittings)
        )
    '''
    if only_blanks:
        cursor.execute(f'''
            SELECT DISTINCT m.id, m.name 
            FROM members m
            JOIN member_summaries ms ON m.id = ms.member_id
            WHERE ms.summary IS NULL
            {current_parl_filter}
        ''')
    else:
        cursor.execute(f'''
            SELECT id, name FROM members m
            WHERE 1=1 {current_parl_filter}
        ''')
    members = [dict(row) for row in cursor.fetchall()]
    
    tasks = []
    
    async def process_member(member):
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT s.section_title, s.section_type, min.acronym as ministry,
                      ss.designation, sess.date
               FROM section_speakers ss
               JOIN sections s ON ss.section_id = s.id
               JOIN sittings sess ON s.sitting_id = sess.id
               LEFT JOIN ministries min ON s.ministry_id = min.id
               WHERE ss.member_id = ?
               ORDER BY sess.date DESC
               LIMIT 20''',
            (member['id'],)
        )
        activity = [dict(row) for row in cursor.fetchall()]
            
        if not activity:
            return
            
        activity_lines = []
        recent_designation = activity[0]['designation'] or "MP"
        
        for a in activity:
            ministry = f"[{a['ministry']}] " if a['ministry'] else ""
            activity_lines.append(f"- {a['date']}: {ministry}{a['section_title']}")
        
        context = "\n".join(activity_lines)
        prompt = MEMBER_PROMPT.format(name=member['name'], recent_designation=recent_designation, text=context)

        summary = await generate_summary(prompt)
        
        if summary:
            cursor.execute(
                '''INSERT INTO member_summaries (member_id, summary, last_updated)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(member_id) DO UPDATE SET 
                   summary = excluded.summary, 
                   last_updated = CURRENT_TIMESTAMP''',
                (member['id'], summary)
            )
            conn.commit()
    
    for m in members:
        tasks.append(process_member(m))
        
        if len(tasks) >= 20:
            await asyncio.gather(*tasks)
            tasks = []
            
    if tasks:
        await asyncio.gather(*tasks)
    
    logger.info("Member summaries complete")
    db.close_connection()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run generate_summaries_sqlite.py [--sittings] [START_DATE [END_DATE]] [--members] [--only-blank]")
        print("Example: uv run generate_summaries_sqlite.py --sittings 01-10-2024")
        sys.exit(1)
        
    args = sys.argv[1:]
    flags = [arg for arg in args if arg.startswith('--')]
    
    summarize_sittings = '--sittings' in flags
    summarize_members = '--members' in flags
    only_blank = '--only-blank' in flags
    
    if ((not summarize_sittings) or summarize_members) and (summarize_sittings or (not summarize_members)):
        print("Error: Exactly one of --sittings and --members can be specified")
        sys.exit(1)
    
    if summarize_members:
        asyncio.run(generate_member_summaries(only_blank))
    else:
        dates = [arg for arg in args if not arg.startswith('--')]
        if len(dates) < 1:
            print("Error: Start date required")
            sys.exit(1)
    
        start = dates[0]
        end = dates[1] if len(dates) > 1 else start

        asyncio.run(generate_sitting_summaries(start, end, only_blank))
