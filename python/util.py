import re

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict

def fetch_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Fetch multiple dates"""
        results = []
        
        start = datetime.strptime(start_date, '%d-%m-%Y')
        end = datetime.strptime(end_date, '%d-%m-%Y')
        
        current = start
        while current <= end:
            date_str = current.strftime('%d-%m-%Y')
            data = self.fetch_by_date(date_str)
            
            if data:
                results.append({
                    'date': date_str,
                    'data': data
                })
            
            current += timedelta(days=1)
        
        return results

def clean_html_for_display(self, html_content: str) -> str:
    # Keep speakers' names in bold
    if not html_content:
        return ""
    
    # Replace common HTML entities
    clean = html_content.replace('&nbsp;', ' ')
    clean = clean.replace('â€™', "'")
    clean = clean.replace('â€"', '—')
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&#39;', "'")
    clean = clean.replace('&quot;', '"')
    
    # Keep <p>, <strong>, <br> tags for formatting
    # Remove other tags
    soup = BeautifulSoup(clean, 'html.parser')
    
    # Convert to formatted text preserving structure
    # This keeps speaker names bold
    return str(soup)
    
def strip_all_html(self, html: str) -> str:
    if not html:
        return ""
    
    clean = re.sub(r'<[^>]+>', '', html)
    clean = clean.replace('&nbsp;', ' ')
    clean = clean.replace('â€™', "'")
    clean = clean.replace('â€"', '—')
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&#39;', "'")
    clean = clean.replace('&quot;', '"')
    clean = re.sub(r'\s+', ' ', clean)
    
    return clean.strip()