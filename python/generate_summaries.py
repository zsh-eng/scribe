import asyncio
import logging
import os
import re
import sys

from openai import AsyncOpenAI
from datetime import datetime, timedelta
from db_async import close_pool, execute
from dotenv import load_dotenv

from prompts import PQ_PROMPT, SECTION_PROMPT, BILL_PROMPT, MEMBER_PROMPT

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
AI_SEMAPHORE = asyncio.Semaphore(1)  # Sequential AI requests for rate limiting
AI_COOLDOWN = 2.5                    # Delay in seconds to achieve ~24-30 RPM and respect TPM

async def generate_summary(prompt_template: str, model='llama-3.1-8b-instant') -> str:
    async with AI_SEMAPHORE:
        client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=GROQ_API_KEY,
        )
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": prompt_template}
                ],
            )
            # Add delay to respect 30 RPM limit
            await asyncio.sleep(AI_COOLDOWN)
            
            content = response.choices[0].message.content.strip()
            # Normalize whitespace: replace multiple spaces/tabs/non-breaking spaces 
            # with single space but preserve newlines
            content = re.sub(r'[ \t\xa0]+', ' ', content)
            return content
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            # Still wait on error to avoid rapid-fire failures hitting limits
            await asyncio.sleep(AI_COOLDOWN)
            return None

async def generate_section_summaries_for_session(session_id, only_blanks):
    sections = await execute(
        f'''SELECT id, section_title, content_plain, category, section_type 
           FROM sections    
           WHERE session_id = $1 
             AND length(content_plain) > 20
             AND category != 'bill' 
             AND section_type NOT IN ('BI', 'BP')
             {'AND sections.summary IS NULL' if only_blanks else ''}''',
        session_id,
        fetch=True
    )
    
    if not sections:
        return
        
    logger.info(f"Generating summaries for {len(sections)} sections in session {session_id}")
    
    tasks = []
    for s in sections:
        tasks.append(generate_section_summary(s))
        
        # Batch to avoid hitting rate limits too hard
        if len(tasks) >= 5:
            await asyncio.gather(*tasks)
            tasks = []
            
    if tasks:
        await asyncio.gather(*tasks)

async def generate_section_summary(section):
    prompt = PQ_PROMPT if section['category'] == 'question' else SECTION_PROMPT
    prompt = prompt.format(title=section['section_title'], text=section['content_plain'][:20000])
    
    summary = await generate_summary(prompt)
    
    if summary:
        await execute('UPDATE sections SET summary = $1 WHERE id = $2', summary, section['id'])

async def generate_bill_summaries_for_session(session_id, only_blanks):
    bills = await execute(
        f'''SELECT DISTINCT b.id, b.title 
           FROM bills b
           JOIN sections s ON b.id = s.bill_id
           WHERE s.session_id = $1
           AND s.section_type = 'BP'
           {'AND b.summary IS NULL' if only_blanks else ''}''',
        session_id,
        fetch=True
    )
    
    if not bills:
        return
        
    logger.info(f"Generating summaries for {len(bills)} bills in session {session_id}")
    
    for bill in bills:
        sections = await execute(
            '''SELECT content_plain FROM sections 
               WHERE bill_id = $1 
               ORDER BY section_order''',
            bill['id'],
            fetch=True
        )
        
        if not sections:
            continue
            
        full_text = "\n\n".join([s['content_plain'] for s in sections])
        
        # Skip if text is too short
        if len(full_text) < 500:
            continue
        
        prompt = BILL_PROMPT.format(title=bill['title'], text=full_text[:20000])
        
        summary = await generate_summary(prompt)
        
        if summary:
            await execute('UPDATE bills SET summary = $1 WHERE id = $2', summary, bill['id'])
            logger.info(f"Generated summary for bill {bill['title']}")


async def generate_session_summaries(start_date_str, end_date_str, only_blanks=False):
    start_date = datetime.strptime(start_date_str, '%d-%m-%Y')
    end_date = datetime.strptime(end_date_str, '%d-%m-%Y')
    
    dates = []
    curr = start_date
    while curr <= end_date:
        dates.append(curr.strftime('%d-%m-%Y'))
        curr += timedelta(days=1)
        
    logger.info(f"Summarizing date range: {start_date_str} to {end_date_str} ({len(dates)} days)")
    
    session_ids_to_process = []
    
    rows = await execute(
        'SELECT id FROM sessions WHERE date >= TO_DATE($1, \'DD-MM-YYYY\') AND date <= TO_DATE($2, \'DD-MM-YYYY\')',
        start_date_str, end_date_str,
        fetch=True
    )

    session_ids_to_process = [r['id'] for r in rows]
            
    logger.info(f"Generating summaries for {len(session_ids_to_process)} sessions...")
    
    for sid in session_ids_to_process:
        await generate_section_summaries_for_session(sid, only_blanks)
        await generate_bill_summaries_for_session(sid, only_blanks)

    logger.info("Batch processing complete!")
    await close_pool()

async def generate_member_summaries(only_blanks):
    logger.info('Refreshing member_list_view...')
    await execute('REFRESH MATERIALIZED VIEW CONCURRENTLY member_list_view')

    logger.info("Generating member summaries...")
    if only_blanks:
        members = await execute('''SELECT DISTINCT id, name 
                                    FROM members JOIN member_summaries ON members.id = member_summaries.member_id
                                    WHERE member_summaries.summary IS NULL''', fetch=True)
    else:
        members = await execute('SELECT id, name FROM members', fetch=True)
    
    tasks = []
    
    async def process_member(member):
        activity = await execute(
            '''SELECT s.section_title, s.section_type, m.acronym as ministry,
                      ss.designation, sess.date
               FROM section_speakers ss
               JOIN sections s ON ss.section_id = s.id
               JOIN sessions sess ON s.session_id = sess.id
               LEFT JOIN ministries m ON s.ministry_id = m.id
               WHERE ss.member_id = $1
               ORDER BY sess.date DESC
               LIMIT 20''',
            member['id'],
            fetch=True
        )
            
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
            await execute(
                '''INSERT INTO member_summaries (member_id, summary, last_updated)
                   VALUES ($1, $2, NOW())
                   ON CONFLICT (member_id) DO UPDATE SET summary = EXCLUDED.summary, last_updated = NOW()''',
                member['id'], summary
            )
    
    for m in members:
        tasks.append(process_member(m))
        
        if len(tasks) >= 5:
            await asyncio.gather(*tasks)
            tasks = []
            
    if tasks:
        await asyncio.gather(*tasks)
    logger.info("Member summaries complete")
    await close_pool()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run generate_summaries.py [--sessions] [START_DATE [END_DATE]] [--members] [--only-blank]")
        print("Example: uv run generate_summaries.py --sessions 01-10-2024")
        sys.exit(1)
        
    args = sys.argv[1:]
    flags = [arg for arg in args if arg.startswith('--')]
    
    summarize_sessions = '--sessions' in flags
    summarize_members = '--members' in flags
    only_blank = '--only-blank' in flags # only generate summaries for rows with no summaries
    
    # Exactly one of summarize sessions and summarize_members can be specified i.e. XNOR
    if ((not summarize_sessions) or summarize_members) and (summarize_sessions or (not summarize_members)):
        print("Error: Exactly one of --sessions and --members can be specified")
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

        asyncio.run(generate_session_summaries(start, end, only_blank))