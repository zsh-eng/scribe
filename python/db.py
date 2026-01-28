import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(os.getenv('DATABASE_URL'))

def execute_query(query, params=None, fetch=False):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(query, params)
    
    result = None
    if fetch:
        result = cur.fetchall()
    
    conn.commit()
    cur.close()
    conn.close()
    return result

def find_or_create_member(name):
    result = execute_query(
        'SELECT id FROM members WHERE name = %s',
        (name,),
        fetch=True
    )
    
    if result:
        return result[0]['id']
    
    result = execute_query(
        'INSERT INTO members (name) VALUES (%s) RETURNING id',
        (name,),
        fetch=True
    )
    return result[0]['id']

def find_ministry_by_acronym(acronym):
    result = execute_query(
        'SELECT id FROM ministries WHERE acronym = %s',
        (acronym,),
        fetch=True
    )
    return result[0]['id'] if result else None

def add_section_speaker(section_id, member_id, constituency=None, designation=None):
    execute_query(
        '''INSERT INTO section_speakers (section_id, member_id, constituency, designation)
           VALUES (%s, %s, %s, %s)''',
        (section_id, member_id, constituency, designation)
    )

def add_session_attendance(session_id, member_id, present=True, constituency=None, designation=None):
    execute_query(
        '''INSERT INTO session_attendance (session_id, member_id, present, constituency, designation)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (session_id, member_id) DO UPDATE SET
           present = EXCLUDED.present,
           constituency = EXCLUDED.constituency,
           designation = EXCLUDED.designation''',
        (session_id, member_id, present, constituency, designation)
    )

def find_or_create_bill(title, ministry_id=None, first_reading_date=None, first_reading_session_id=None):
    title = title.strip()
    result = execute_query(
        'SELECT id, first_reading_date, ministry_id FROM bills WHERE title = %s',
        (title,),
        fetch=True
    )
    
    if result:
        bill_id = result[0]['id']
        existing_ministry = result[0]['ministry_id']
        existing_first_reading = result[0]['first_reading_date']
        
        # Update ministry if not set
        if ministry_id and not existing_ministry:
            execute_query(
                'UPDATE bills SET ministry_id = %s WHERE id = %s',
                (ministry_id, bill_id)
            )
        
        # Update first reading info if not set and this is a first reading
        if first_reading_date and not existing_first_reading:
            execute_query(
                '''UPDATE bills SET first_reading_date = TO_DATE(%s, 'DD-MM-YYYY'), 
                   first_reading_session_id = %s
                   WHERE id = %s''',
                (first_reading_date, first_reading_session_id, bill_id)
            )
        return bill_id
    
    # Create new bill
    result = execute_query(
        '''INSERT INTO bills (title, ministry_id, first_reading_date, first_reading_session_id)
           VALUES (%s, %s, TO_DATE(%s, 'DD-MM-YYYY'), %s) RETURNING id''',
        (title, ministry_id, first_reading_date, first_reading_session_id),
        fetch=True
    )
    return result[0]['id']

def refresh_member_list_view():
    """Refresh the materialized view for member list data.
    
    Call this after ingesting new hansard data to update the pre-computed
    member information (constituency, designation, section counts).
    Uses CONCURRENTLY to avoid locking reads during refresh.
    """
    print('Refreshing member_list_view...')
    execute_query('REFRESH MATERIALIZED VIEW CONCURRENTLY member_list_view')
    print('Done!')

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'refresh':
        # Refresh materialized views
        refresh_member_list_view()
    else:
        # Default: test database connection
        try:
            result = execute_query('SELECT NOW()', fetch=True)
            print('Connected to Supabase')
            print(f'Current time: {result[0]["now"]}')
            
            moh = find_ministry_by_acronym('MOH')
            print(f'MOH ministry id: {moh}')
            
            print('\nUsage: python db.py refresh  (to refresh materialized views)')
        except Exception as e:
            print(f'Connection failed: {e}')