import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import re
from datetime import datetime, timedelta
import time
import json

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
                href = link.get('href', '')
                
                # Check visible digit links
                if link_text.isdigit():
                    max_page = max(max_page, int(link_text))
                
                # Check for "Last" links
                elif 'last' in link_text.lower() and href:
                    page_match = re.search(r'page[=\/](\d+)', href)
                    if page_match:
                        max_page = max(max_page, int(page_match.group(1)))
                
                # Check for page numbers in href even if text is not a digit (like "…" links)
                elif href and 'page=' in href:
                    page_match = re.search(r'page=(\d+)', href)
                    if page_match:
                        page_num = int(page_match.group(1))
                        max_page = max(max_page, page_num)
                        
            logging.info(f"Detected maximum page number from pagination: {max_page}")
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

def classify_job_category(title, description, company):
    """Classify job into categories based on title, description, and company."""
    title_lower = title.lower()
    description_lower = description.lower()
    company_lower = company.lower()
    
    # Define category keywords
    categories = {
        "Healthcare": [
            "nurse", "doctor", "medical", "health", "hospital", "clinic", "pharmacy", "pharmacist",
            "therapist", "healthcare", "dentist", "physician", "clinical", "patient", "treatment",
            "medical officer", "health officer", "nursing", "midwife", "radiographer", "lab technician"
        ],
        "IT & Technology": [
            "developer", "programmer", "software", "IT", "system", "network", "database", "web",
            "technology", "computer", "digital", "cyber", "data", "analyst", "technical", "engineer",
            "coding", "programming", "javascript", "python", "java", "html", "css"
        ],
        "Education & Training": [
            "teacher", "instructor", "education", "training", "academic", "school", "university",
            "lecturer", "professor", "tutor", "educational", "curriculum", "learning", "student",
            "teaching", "trainer", "facilitator"
        ],
        "Finance & Banking": [
            "accountant", "finance", "banking", "financial", "audit", "budget", "accounting",
            "economist", "treasurer", "cashier", "credit", "loan", "investment", "tax",
            "bookkeeper", "payroll"
        ],
        "Sales & Marketing": [
            "sales", "marketing", "market", "customer", "client", "business development", "promotion",
            "advertising", "brand", "retail", "commercial", "revenue", "target", "campaign"
        ],
        "Human Resources": [
            "human resources", "HR", "recruitment", "talent", "personnel", "employee", "payroll",
            "benefits", "compensation", "training coordinator", "people", "workforce"
        ],
        "Engineering": [
            "engineer", "engineering", "mechanical", "electrical", "civil", "construction", "architect",
            "technical", "maintenance", "repair", "installation", "infrastructure", "project engineer"
        ],
        "Administration": [
            "administrator", "admin", "secretary", "clerk", "assistant", "receptionist", "office",
            "administrative", "coordinator", "support", "data entry", "filing"
        ],
        "Management": [
            "manager", "director", "supervisor", "head", "chief", "executive", "leadership", "team lead",
            "senior", "management", "operations", "strategic", "planning", "CEO", "COO", "CFO"
        ],
        "Agriculture": [
            "agriculture", "farming", "farmer", "agricultural", "crop", "livestock", "veterinary",
            "agronomy", "irrigation", "rural", "extension officer"
        ],
        "Legal": [
            "lawyer", "legal", "attorney", "law", "court", "judicial", "legal officer", "paralegal",
            "compliance", "contract", "litigation"
        ],
        "NGO & Development": [
            "NGO", "development", "community", "social", "humanitarian", "volunteer", "nonprofit",
            "charity", "aid", "relief", "donor", "grant", "project officer"
        ],
        "Consulting": [
            "consultant", "consulting", "advisory", "expert", "specialist", "freelance", "contractor",
            "consultancy", "expertise"
        ],
        "Transportation & Logistics": [
            "driver", "transport", "logistics", "delivery", "shipping", "warehouse", "supply chain",
            "distribution", "fleet", "cargo"
        ],
        "Security": [
            "security", "guard", "protection", "safety", "surveillance", "risk", "emergency"
        ],
        "Other": []  # Default category
    }
    
    # Check each category
    for category, keywords in categories.items():
        if category == "Other":
            continue
            
        for keyword in keywords:
            if (keyword in title_lower or 
                keyword in description_lower or 
                keyword in company_lower):
                return category
    
    return "Other"

def extract_email_from_job_page(job_url):
    """Extract email address from individual job detail page."""
    try:
        # Make URL absolute if it's relative
        if job_url.startswith('/'):
            job_url = 'https://vacancymail.co.zw' + job_url
        
        response = requests.get(job_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract all text from the page
        page_text = soup.get_text()
        
        # Find email addresses using regex
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, page_text)
        
        if emails:
            # Return the first email found (usually the application email)
            return emails[0]
        else:
            return "N/A"
            
    except Exception as e:
        logging.warning(f"Could not extract email from {job_url}: {e}")
        return "N/A"

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
        
        logging.info(f"Found {len(job_listings)} job listings on page {page_num}")
        
        jobs_data = []
        expired_count = 0
        for job_index, job in enumerate(job_listings):
            title = job.find('h3', class_='job-listing-title').text.strip() if job.find('h3', class_='job-listing-title') else "N/A"
            company = job.find('h4', class_='job-listing-company').text.strip() if job.find('h4', class_='job-listing-company') else "N/A"
            
            # Extract job detail URL for email extraction
            job_url = job.get('href', '')
            
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
                # Extract email from job detail page
                logging.info(f"Extracting email for job: {title[:50]}...")
                apply_email = extract_email_from_job_page(job_url) if job_url else "N/A"
                
                # Generate unique ID for the job
                job_id = f"VM_{page_num:03d}_{job_index+1:03d}_{datetime.now().strftime('%Y%m%d')}"
                
                # Classify job category
                category = classify_job_category(title, description, company)
                
                jobs_data.append({
                    "id": job_id,
                    "Job Title": clean_text(title),
                    "title": clean_text(title),
                    "Company": clean_text(company),
                    "company": clean_text(company),
                    "Location": clean_text(location),
                    "Expiry Date": clean_text(expiry_date),
                    "closingDate": clean_text(expiry_date),
                    "Description": clean_text(description),
                    "description": clean_text(description),
                    "Category": category,
                    "category": category,
                    "Source Site": "vacancymail.co.zw",
                    "sourceSite": "vacancymail.co.zw",
                    "Apply Email": apply_email,
                    "applyEmail": apply_email
                })
                
                # Add a small delay to be respectful when scraping individual job pages
                time.sleep(0.5)
            else:
                expired_count += 1
                logging.info(f"Skipping expired job: {title} (expires: {expiry_date})")
        
        logging.info(f"Page {page_num}: {len(jobs_data)} current jobs, {expired_count} expired jobs")
        if len(jobs_data) > 0:
            print(f"  -> {len(jobs_data)} current jobs (with emails), {expired_count} expired jobs")
        else:
            print(f"  -> {len(jobs_data)} current jobs, {expired_count} expired jobs")
        
        return jobs_data, soup
        
    except Exception as e:
        logging.error(f"Error scraping page {page_num}: {e}")
        return [], None

def scrape_jobs(test_mode=False):
    """Main function to scrape all jobs from all pages, filtering by expiry date."""
    logging.info("Starting comprehensive job scraping...")
    print("Starting comprehensive job scraping...")
    if test_mode:
        print("** RUNNING IN TEST MODE - FIRST PAGE ONLY **")
    
    base_url = "https://vacancymail.co.zw/jobs/?ordering=later"
    all_jobs_data = []
    
    try:
        # First, get the first page to determine total pages
        first_page_jobs, first_page_soup = scrape_page(base_url, 1)
        if first_page_soup is None:
            logging.error("Failed to scrape first page")
            return
        
        all_jobs_data.extend(first_page_jobs)
        
        # If in test mode, stop after first page
        if test_mode:
            total_pages = 1
        else:
            total_pages = get_total_pages(first_page_soup)
        
        # If we couldn't determine total pages but got a full page of jobs,
        # try to scrape more pages until we find no more jobs
        jobs_per_page = len(first_page_soup.find_all('a', class_='job-listing'))
        if not test_mode and total_pages == 1 and jobs_per_page >= 10:  # Assume 10+ jobs per page means there might be more
            logging.info("Couldn't determine total pages, will search for additional pages...")
            print("Searching for additional pages...")
            
            page_num = 2
            while page_num <= 15:  # Increased safety limit since there might be more pages with ordering=later
                time.sleep(1)
                page_jobs, page_soup = scrape_page(base_url, page_num)
                
                # Check if there are actual job listings on the page (regardless of date filtering)
                if page_soup and page_soup.find_all('a', class_='job-listing'):
                    # There are job listings, add any current ones to our data
                    all_jobs_data.extend(page_jobs)
                    total_pages = page_num
                    page_num += 1
                else:
                    # No job listings found on this page, we've reached the end
                    logging.info(f"No more job listings found on page {page_num}, stopping search")
                    print(f"No more job listings found on page {page_num}, stopping search")
                    break
        else:
            # Scrape remaining pages using detected total
            if not test_mode:
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
        
        # Ensure 'N/A' values are properly handled (not converted to NaN)
        df = df.fillna('N/A')
        
        # Reorder columns for CSV output
        csv_columns = ['Job Title', 'Company', 'Location', 'Category', 'Expiry Date', 'Description', 'Source Site', 'Apply Email']
        df_csv = df[csv_columns]
        
        # Save to CSV with timestamp to avoid conflicts
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'scraped_data_{timestamp}.csv'
        df_csv.to_csv(filename, index=False, na_rep='N/A')
        
        # Create JSON data with the specified structure
        json_data = []
        for job in all_jobs_data:
            json_job = {
                "id": job["id"],
                "title": job["title"],
                "company": job["company"],
                "description": job["description"],
                "category": job["category"],
                "sourceSite": job["sourceSite"],
                "applyEmail": job["applyEmail"],
                "closingDate": job["closingDate"]
            }
            json_data.append(json_job)
        
        # Save JSON file
        json_filename = f'scraped_data_{timestamp}.json'
        with open(json_filename, 'w', encoding='utf-8') as json_file:
            json.dump(json_data, json_file, indent=2, ensure_ascii=False)
        
        logging.info(f"JSON data saved to {json_filename}")
        
        # Also save as the main scraped_data.csv for compatibility
        try:
            df_csv.to_csv('scraped_data.csv', index=False, na_rep='N/A')
            # Also save main JSON file
            with open('scraped_data.json', 'w', encoding='utf-8') as json_file:
                json.dump(json_data, json_file, indent=2, ensure_ascii=False)
            logging.info("Also saved as scraped_data.csv and scraped_data.json")
        except PermissionError:
            logging.warning("Could not overwrite main files (files may be open)")
        
        total_jobs = len(all_jobs_data)
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Display some statistics
        df_summary = df.groupby('Expiry Date').size().sort_values(ascending=False)
        locations = df['Location'].value_counts()
        
        # Email statistics
        email_success = len(df[df['Apply Email'] != 'N/A'])
        email_total = len(df)
        email_rate = (email_success / email_total * 100) if email_total > 0 else 0
        
        logging.info(f"Successfully scraped {total_jobs} current jobs from {total_pages} pages")
        logging.info(f"Data saved to {filename} and {json_filename} at {pd.Timestamp.now()}")
        logging.info(f"Jobs filtered to show only those expiring on or after {current_date}")
        logging.info(f"Email extraction success rate: {email_success}/{email_total} ({email_rate:.1f}%)")
        logging.info(f"Top locations: {locations.head(3).to_dict()}")
        
        print(f"Successfully scraped {total_jobs} current jobs from {total_pages} pages")
        print(f"Data saved to:")
        print(f"  CSV: {filename}")
        print(f"  JSON: {json_filename}")
        print(f"Jobs filtered to show only those expiring on or after {current_date}")
        print(f"Email extraction: {email_success}/{email_total} jobs ({email_rate:.1f}% success rate)")
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
    
    # Check if running in test mode
    import sys
    test_mode = "--test" in sys.argv
    
    scrape_jobs(test_mode=test_mode)  # Call the function to execute scraping