import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import re
from datetime import datetime, timedelta
import time

# Configure logging
logging.basicConfig(
    filename='scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def clean_text(text):
    """Clean text by removing special characters and normalizing whitespace."""
    if not isinstance(text, str):
        return text
    text = text.replace('\u2013', '-')  # en dash
    text = text.replace('\u2014', '-')  # em dash
    text = text.replace('\u2018', "'").replace('\u2019', "'")  # curly single quotes
    text = text.replace('\u201c', '"').replace('\u201d', '"')  # curly double quotes
    text = text.replace('\u2026', '')  # ellipsis
    text = re.sub(r'[^\x00-\x7F]+', '', text)  # remove any remaining non-ASCII
    return text.strip()

def parse_expiry_date(expiry_text):
    """Parse expiry date text and return datetime object."""
    if not expiry_text or expiry_text == "N/A":
        return None
    
    try:
        # Extract date from text like "Expires 24 Aug 2025"
        if "expires" in expiry_text.lower():
            date_part = expiry_text.lower().replace("expires", "").strip()
            # Handle different date formats
            if re.match(r'\d{1,2}\s+\w+\s+\d{4}', date_part):
                return datetime.strptime(date_part, '%d %b %Y')
            elif re.match(r'\d{1,2}\s+\w+\s+\d{2}', date_part):
                return datetime.strptime(date_part, '%d %b %y')
    except Exception as e:
        logging.warning(f"Could not parse date: {expiry_text} - {e}")
    
    return None

def is_job_current(expiry_text):
    """Check if job expiry date is today or in the future."""
    expiry_date = parse_expiry_date(expiry_text)
    if expiry_date is None:
        return True  # Include jobs with no expiry date
    
    today = datetime.now().date()
    return expiry_date.date() >= today

def get_total_pages(soup):
    """Extract total number of pages from pagination."""
    try:
        # Look for pagination elements - try multiple approaches
        pagination = soup.find('ul', class_='pagination') or soup.find('div', class_='pagination') or soup.find('nav', class_='pagination')
        
        if pagination:
            # Find all page links and get the highest number
            page_links = pagination.find_all('a')
            max_page = 1
            for link in page_links:
                link_text = link.get_text(strip=True)
                if link_text.isdigit():
                    max_page = max(max_page, int(link_text))
                # Also check for "Next" or "Last" links
                elif 'last' in link_text.lower() and link.get('href'):
                    href = link.get('href')
                    page_match = re.search(r'page[=\/](\d+)', href)
                    if page_match:
                        max_page = max(max_page, int(page_match.group(1)))
            return max_page
        
        # Alternative: look for "Page X of Y" text
        page_info = soup.find(string=re.compile(r'page\s+\d+\s+of\s+(\d+)', re.I))
        if page_info:
            match = re.search(r'of\s+(\d+)', page_info, re.I)
            if match:
                return int(match.group(1))
        
        # Check for "Next" button or link to determine if there are more pages
        next_link = soup.find('a', string=re.compile(r'next', re.I)) or soup.find('a', class_=re.compile(r'next', re.I))
        if next_link:
            return 5  # Conservative estimate if we can't determine exact number
            
    except Exception as e:
        logging.warning(f"Could not determine total pages: {e}")
    
    return 1  # Default to 1 page if can't determine

def scrape_page(url, page_num=1):
    """Scrape jobs from a specific page."""
    if page_num > 1:
        # Check if URL already has parameters
        separator = "&" if "?" in url else "?"
        page_url = f"{url}{separator}page={page_num}"
    else:
        page_url = url
    
    try:
        logging.info(f"Scraping page {page_num}: {page_url}")
        print(f"Scraping page {page_num}...")
        
        response = requests.get(page_url)
        response.encoding = 'utf-8'
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        job_listings = soup.find_all('a', class_='job-listing')
        
        jobs_data = []
        for job in job_listings:
            title = job.find('h3', class_='job-listing-title').text.strip() if job.find('h3', class_='job-listing-title') else "N/A"
            company = job.find('h4', class_='job-listing-company').text.strip() if job.find('h4', class_='job-listing-company') else "N/A"
            
            # Extract location and expiry date from the job listing footer
            footer = job.find('div', class_='job-listing-footer')
            if footer:
                # Location is typically the first <li> after the location icon
                location_icon = footer.find('i', class_='icon-material-outline-location-on')
                location = location_icon.find_parent('li').text.strip() if location_icon else "N/A"
                
                # Expiry date is typically the <li> with the expiry icon
                expiry_icon = footer.find('i', class_='icon-material-outline-access-time')
                expiry_date = expiry_icon.find_parent('li').text.strip() if expiry_icon else "N/A"
            else:
                location = "N/A"
                expiry_date = "N/A"

            description = job.find('p', class_='job-listing-text').text.strip() if job.find('p', class_='job-listing-text') else "N/A"
            
            # Only include jobs that haven't expired
            if is_job_current(expiry_date):
                jobs_data.append({
                    "Job Title": clean_text(title),
                    "Company": clean_text(company),
                    "Location": clean_text(location),
                    "Expiry Date": clean_text(expiry_date),
                    "Description": clean_text(description)
                })
            else:
                logging.info(f"Skipping expired job: {title} (expires: {expiry_date})")
        
        return jobs_data, soup
        
    except Exception as e:
        logging.error(f"Error scraping page {page_num}: {e}")
        return [], None

def scrape_jobs():
    """Main function to scrape all jobs from all pages, filtering by expiry date."""
    logging.info("Starting comprehensive job scraping...")
    print("Starting comprehensive job scraping...")
    
    base_url = "https://vacancymail.co.zw/jobs/?ordering=later"
    all_jobs_data = []
    
    try:
        # First, get the first page to determine total pages
        first_page_jobs, first_page_soup = scrape_page(base_url, 1)
        if first_page_soup is None:
            logging.error("Failed to scrape first page")
            return
        
        all_jobs_data.extend(first_page_jobs)
        total_pages = get_total_pages(first_page_soup)
        
        # If we couldn't determine total pages but got a full page of jobs,
        # try to scrape more pages until we find no more jobs
        jobs_per_page = len(first_page_soup.find_all('a', class_='job-listing'))
        if total_pages == 1 and jobs_per_page >= 10:  # Assume 10+ jobs per page means there might be more
            logging.info("Couldn't determine total pages, will search for additional pages...")
            print("Searching for additional pages...")
            
            page_num = 2
            while page_num <= 50:  # Increased safety limit since there might be more pages with ordering=later
                time.sleep(1)
                page_jobs, page_soup = scrape_page(base_url, page_num)
                
                if not page_jobs or (page_soup and not page_soup.find_all('a', class_='job-listing')):
                    # No more jobs found, stop searching
                    break
                    
                all_jobs_data.extend(page_jobs)
                total_pages = page_num
                page_num += 1
        else:
            # Scrape remaining pages using detected total
            for page_num in range(2, total_pages + 1):
                # Add delay between requests to be respectful to the server
                time.sleep(1)
                
                page_jobs, _ = scrape_page(base_url, page_num)
                all_jobs_data.extend(page_jobs)
        
        logging.info(f"Scraped {total_pages} total pages")
        print(f"Scraped {total_pages} total pages")
        
        if not all_jobs_data:
            logging.warning("No current job listings found.")
            print("No current job listings found.")
            return
        
        # Store data in a DataFrame
        df = pd.DataFrame(all_jobs_data)
        
        # Save to CSV with timestamp to avoid conflicts
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'scraped_data_{timestamp}.csv'
        df.to_csv(filename, index=False)
        
        # Also save as the main scraped_data.csv for compatibility
        try:
            df.to_csv('scraped_data.csv', index=False)
            logging.info("Also saved as scraped_data.csv")
        except PermissionError:
            logging.warning("Could not overwrite scraped_data.csv (file may be open)")
        
        total_jobs = len(all_jobs_data)
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Display some statistics
        df_summary = df.groupby('Expiry Date').size().sort_values(ascending=False)
        locations = df['Location'].value_counts()
        
        logging.info(f"Successfully scraped {total_jobs} current jobs from {total_pages} pages")
        logging.info(f"Data saved to {filename} at {pd.Timestamp.now()}")
        logging.info(f"Jobs filtered to show only those expiring on or after {current_date}")
        logging.info(f"Top locations: {locations.head(3).to_dict()}")
        
        print(f"Successfully scraped {total_jobs} current jobs from {total_pages} pages")
        print(f"Data saved to {filename}")
        print(f"Jobs filtered to show only those expiring on or after {current_date}")
        print(f"\nJob Statistics:")
        print(f"- Total jobs found: {total_jobs}")
        print(f"- Jobs by location:")
        for location, count in locations.head(5).items():
            print(f"  {location}: {count}")
        print(f"- Jobs by expiry date:")
        for expiry, count in df_summary.head(5).items():
            print(f"  {expiry}: {count}")

    except Exception as e:
        logging.error(f"Error occurred during scraping: {e}")
        print(f"Error occurred during scraping: {e}")

if __name__ == "__main__":
    logging.info("Starting the web scraper...")
    print("Starting the web scraper...")
    scrape_jobs()  # Call the function to execute scraping