import requests
from bs4 import BeautifulSoup
import re

response = requests.get('https://vacancymail.co.zw/jobs/?ordering=later')
soup = BeautifulSoup(response.text, 'html.parser')

print("Checking for pagination elements...")

pagination = soup.find('ul', class_='pagination') or soup.find('div', class_='pagination') or soup.find('nav', class_='pagination')

if pagination:
    print('Found pagination element')
    page_links = pagination.find_all('a')
    print(f'Found {len(page_links)} pagination links')
    max_page = 1
    for i, link in enumerate(page_links):
        link_text = link.get_text(strip=True)
        href = link.get('href', '')
        print(f'Link {i}: text="{link_text}", href="{href}"')
        if link_text.isdigit():
            max_page = max(max_page, int(link_text))
            print(f'  -> Found page number: {link_text}')
    print(f'Max page detected from pagination: {max_page}')
else:
    print('No pagination element found')

# Check for next links
next_link = soup.find('a', string=re.compile(r'next', re.I)) or soup.find('a', class_=re.compile(r'next', re.I))
if next_link:
    print(f'Found next link: {next_link}')
else:
    print('No next link found')

print("\nLet's also check what the get_total_pages function would return...")

def get_total_pages(soup):
    try:
        pagination = soup.find('ul', class_='pagination') or soup.find('div', class_='pagination') or soup.find('nav', class_='pagination')
        
        if pagination:
            page_links = pagination.find_all('a')
            max_page = 1
            for link in page_links:
                link_text = link.get_text(strip=True)
                if link_text.isdigit():
                    max_page = max(max_page, int(link_text))
                elif 'last' in link_text.lower() and link.get('href'):
                    href = link.get('href')
                    page_match = re.search(r'page[=\/](\d+)', href)
                    if page_match:
                        max_page = max(max_page, int(page_match.group(1)))
            return max_page
        
        page_info = soup.find(string=re.compile(r'page\s+\d+\s+of\s+(\d+)', re.I))
        if page_info:
            match = re.search(r'of\s+(\d+)', page_info, re.I)
            if match:
                return int(match.group(1))
        
        next_link = soup.find('a', string=re.compile(r'next', re.I)) or soup.find('a', class_=re.compile(r'next', re.I))
        if next_link:
            return 5
            
    except Exception as e:
        print(f'Error: {e}')
    
    return 1

result = get_total_pages(soup)
print(f'get_total_pages() returned: {result}')
