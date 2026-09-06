"""Generate explicitly selected summaries, or review their provenance without API calls."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import sqlite3

from dotenv import load_dotenv
from google import genai

import db_sqlite as db
from summary_jobs import (DEFAULT_INPUT_LIMIT, DEFAULT_MODEL, sitting_jobs, member_jobs,
                          review_job, save_attempt)

logger = logging.getLogger(__name__)


async def run_jobs(conn, jobs, *, model=DEFAULT_MODEL, input_limit=DEFAULT_INPUT_LIMIT,
                   regenerate=False, client=None, cooldown=0.5):
    """No automatic regeneration on source, prompt or model changes."""
    counts = Counter()
    owned_client = None
    semaphore = asyncio.Semaphore(20)
    selected = []
    for job in jobs:
        if job.summary and not regenerate:
            counts['existing'] += 1
        elif job.input_chars > input_limit:
            save_attempt(conn, job, model, 'blocked', error='over_input_limit')
            counts['blocked'] += 1
            logger.warning('%s %s exceeds input limit (%s > %s); no request made',
                           job.kind, job.entity_id, job.input_chars, input_limit)
        else:
            selected.append(job)
    if selected and client is None:
        load_dotenv()
        owned_client = client = genai.Client()

    async def generate(job):
        async with semaphore:
            try:
                response = await client.aio.models.generate_content(model=model, contents=job.prompt)
                summary = re.sub(r'[ \t\xa0]+', ' ', (response.text or '').strip())
                if not summary:
                    raise ValueError('empty_response')
            except Exception as exc:
                # Store a safe error class, not provider response bodies or credentials.
                save_attempt(conn, job, model, 'failed', error=type(exc).__name__)
                logger.error('Summary failed for %s %s: %s', job.kind, job.entity_id, type(exc).__name__)
                counts['failed'] += 1
            else:
                metadata = getattr(response, 'usage_metadata', None)
                usage = {name: getattr(metadata, name, None) for name in (
                    'prompt_token_count', 'cached_content_token_count', 'candidates_token_count',
                    'thoughts_token_count', 'total_token_count')}
                save_attempt(conn, job, model, 'success', summary=summary, usage=usage)
                counts['success'] += 1
            finally:
                await asyncio.sleep(cooldown)

    try:
        for offset in range(0, len(selected), 20):
            await asyncio.gather(*(generate(job) for job in selected[offset:offset + 20]))
    finally:
        if owned_client is not None:
            await owned_client.aio.aclose()
            owned_client.close()
    logger.info('Summary results: %s', json.dumps(dict(counts), sort_keys=True))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--sittings', nargs='+', metavar='DD-MM-YYYY')
    scope.add_argument('--members', action='store_true')
    parser.add_argument('--review', action='store_true', help='Read-only JSONL review; no LLM requests')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--only-blank', action='store_true', help='Default: only generate missing summaries')
    mode.add_argument('--regenerate', action='store_true', help='Explicitly replace summaries in the selected scope')
    parser.add_argument('--id', action='append', help='Restrict scope to exact entity IDs; repeatable')
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--max-input-chars', type=int, default=DEFAULT_INPUT_LIMIT,
                        help='Skip larger prompts instead of truncating them; raise explicitly if needed')
    args = parser.parse_args()
    if args.max_input_chars < 1:
        parser.error('--max-input-chars must be positive')
    if args.sittings:
        if len(args.sittings) not in (1, 2):
            parser.error('--sittings accepts a start date and optional end date')
        try:
            start = datetime.strptime(args.sittings[0], '%d-%m-%Y').strftime('%Y-%m-%d')
            end = datetime.strptime(args.sittings[-1], '%d-%m-%Y').strftime('%Y-%m-%d')
        except ValueError:
            parser.error('Dates must use DD-MM-YYYY')
        if start > end:
            parser.error('Start date must be on or before end date')
    if args.review:
        conn = sqlite3.connect(Path(db.DB_PATH).resolve().as_uri() + '?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
    else:
        db.init_db()
        conn = db.get_connection()
    try:
        jobs = list(member_jobs(conn) if args.members else sitting_jobs(conn, start, end))
        if args.id:
            missing = set(args.id) - {job.entity_id for job in jobs}
            if missing:
                parser.error('IDs not found in eligible scope: ' + ', '.join(sorted(missing)))
            jobs = [job for job in jobs if job.entity_id in args.id]
        if args.review:
            for job in jobs:
                print(json.dumps(review_job(conn, job, args.model, args.max_input_chars)))
            return 0
        counts = asyncio.run(run_jobs(conn, jobs, model=args.model, input_limit=args.max_input_chars,
                                      regenerate=args.regenerate))
        return 1 if counts['failed'] else 0
    finally:
        if args.review:
            conn.close()
        else:
            db.close_connection()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    raise SystemExit(main())
