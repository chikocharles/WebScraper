import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import re
from datetime import datetime, timedelta
import time
import json
from abc import ABC, abstractmethod

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

class JobScraper(ABC):
    """Abstract base class for job scrapers."""
    
    def __init__(self, site_name, base_url):
        self.site_name = site_name
        self.base_url = base_url
    
    @abstractmethod
    def scrape_page(self, url, page_num=1):
        """Scrape jobs from a specific page."""
        pass
    
    @abstractmethod
    def get_total_pages(self, soup):
        """Extract total number of pages from pagination."""
        pass
    
    @abstractmethod
    def extract_email_from_job_page(self, job_url):
        """Extract email address from individual job detail page."""
        pass
    
    def scrape_jobs(self, test_mode=False):
        """Main function to scrape all jobs from all pages."""
        logging.info(f"Starting job scraping for {self.site_name}...")
        print(f"Scraping {self.site_name}...")
        
        all_jobs_data = []
        
        try:
            # First, get the first page to determine total pages
            first_page_jobs, first_page_soup = self.scrape_page(self.base_url, 1)
            if first_page_soup is None:
                logging.error(f"Failed to scrape first page of {self.site_name}")
                return []
            
            all_jobs_data.extend(first_page_jobs)
            
            # If in test mode, stop after first page
            if test_mode:
                total_pages = 1
            else:
                total_pages = self.get_total_pages(first_page_soup)
            
            # Scrape remaining pages
            if not test_mode and total_pages > 1:
                for page_num in range(2, min(total_pages + 1, 50)):  # Limit to 50 pages for safety
                    time.sleep(1)  # Be respectful
                    page_jobs, _ = self.scrape_page(self.base_url, page_num)
                    all_jobs_data.extend(page_jobs)
            
            logging.info(f"Scraped {len(all_jobs_data)} jobs from {self.site_name}")
            print(f"  -> {len(all_jobs_data)} jobs from {self.site_name}")
            
            return all_jobs_data
            
        except Exception as e:
            logging.error(f"Error scraping {self.site_name}: {e}")
            print(f"Error scraping {self.site_name}: {e}")
            return []

class VacancyMailScraper(JobScraper):
    """Scraper for vacancymail.co.zw"""
    
    def __init__(self):
        super().__init__("VacancyMail", "https://vacancymail.co.zw/jobs/?ordering=later")
    
    def get_total_pages(self, soup):
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
                
        except Exception as e:
            logging.warning(f"Could not determine total pages: {e}")
        
        return 1  # Default to 1 page if can't determine

    def extract_email_from_job_page(self, job_url):
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

    def scrape_page(self, url, page_num=1):
        """Scrape jobs from a specific page of VacancyMail."""
        if page_num > 1:
            # Check if URL already has parameters
            separator = "&" if "?" in url else "?"
            page_url = f"{url}{separator}page={page_num}"
        else:
            page_url = url
        
        try:
            response = requests.get(page_url)
            response.encoding = 'utf-8'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            job_listings = soup.find_all('a', class_='job-listing')
            
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
                    apply_email = self.extract_email_from_job_page(job_url) if job_url else "N/A"
                    
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
                        "Source Site": self.site_name,
                        "sourceSite": self.site_name,
                        "Apply Email": apply_email,
                        "applyEmail": apply_email
                    })
                    
                    # Add a small delay to be respectful when scraping individual job pages
                    time.sleep(0.5)
                else:
                    expired_count += 1
            
            return jobs_data, soup
            
        except Exception as e:
            logging.error(f"Error scraping page {page_num} of {self.site_name}: {e}")
            return [], None

class JobsZimbabweScraper(JobScraper):
    """Scraper for Jobs Zimbabwe"""
    
    def __init__(self):
        super().__init__("Jobs Zimbabwe", "https://jobszimbabwe.co.zw/")
    
    def get_total_pages(self, soup):
        """Extract total number of pages from pagination."""
        try:
            pagination = soup.find('nav', class_='np') or soup.find('div', class_='np')
            if pagination:
                page_links = pagination.find_all('a')
                max_page = 1
                for link in page_links:
                    if link.text.strip().isdigit():
                        max_page = max(max_page, int(link.text.strip()))
                return min(max_page, 15)  # Limit to 15 pages
        except Exception as e:
            logging.warning(f"Could not determine total pages for Indeed: {e}")
        return 1

    def extract_email_from_job_page(self, job_url):
        """Indeed doesn't typically expose emails directly."""
        return "Apply on Indeed"

    def scrape_page(self, url, page_num=1):
        """Scrape jobs from Job Zimbabwe."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            if page_num > 1:
                page_url = f"{url}?start={10 * (page_num - 1)}"
            else:
                page_url = url
            
            response = requests.get(page_url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Indeed job card selectors
            job_listings = soup.find_all('div', class_='jobsearch-SerpJobCard') or soup.find_all('div', class_='job_seen_beacon')
            
            jobs_data = []
            
            for job_index, job in enumerate(job_listings):
                try:
                    title_elem = job.find('h2', class_='title') or job.find('a', attrs={'data-jk': True})
                    title = title_elem.text.strip() if title_elem else "N/A"
                    
                    company_elem = job.find('span', class_='company') or job.find('a', class_='turnstileLink')
                    company = company_elem.text.strip() if company_elem else "N/A"
                    
                    location_elem = job.find('div', class_='recJobLoc') or job.find('div', class_='companyLocation')
                    location = location_elem.text.strip() if location_elem else "Zimbabwe"
                    
                    summary_elem = job.find('div', class_='summary')
                    description = summary_elem.text.strip() if summary_elem else "See full description on Indeed"
                    
                    expiry_date = "N/A"
                    
                    job_id = f"ID_{page_num:03d}_{job_index+1:03d}_{datetime.now().strftime('%Y%m%d')}"
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
                        "Source Site": self.site_name,
                        "sourceSite": self.site_name,
                        "Apply Email": "Apply on Jobs Zimbabwe",
                        "applyEmail": "Apply on Jobs Zimbabwe"
                    })
                    
                except Exception as e:
                    logging.warning(f"Error processing Jobs Zimbabwe job {job_index}: {e}")
                    continue
            
            return jobs_data, soup
        except Exception as e:
            logging.error(f"Error scraping Jobs Zimbabwe page {page_num}: {e}")
            return [], None

class ZimboJobsScraper(JobScraper):
    """Scraper for Zimbo Jobs"""
    
    def __init__(self):
        super().__init__("Jobs Zimbabwe", "https://zimbojobs.com/jobs")
    
    def get_total_pages(self, soup):
        """Extract total number of pages from pagination."""
        try:
            pagination = soup.find('nav', class_='np') or soup.find('div', class_='np')
            if pagination:
                page_links = pagination.find_all('a')
                max_page = 1
                for link in page_links:
                    if link.text.strip().isdigit():
                        max_page = max(max_page, int(link.text.strip()))
                return min(max_page, 15)  # Limit to 15 pages
        except Exception as e:
            logging.warning(f"Could not determine total pages for Indeed: {e}")
        return 1

    def extract_email_from_job_page(self, job_url):
        """Indeed doesn't typically expose emails directly."""
        return "ZimboJobs.com"

    def scrape_page(self, url, page_num=1):
        """Scrape jobs from Zimbo Jobs."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            if page_num > 1:
                page_url = f"{url}?start={10 * (page_num - 1)}"
            else:
                page_url = url
            
            response = requests.get(page_url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Indeed job card selectors
            job_listings = soup.find_all('div', class_='jobsearch-SerpJobCard') or soup.find_all('div', class_='job_seen_beacon')
            
            jobs_data = []
            
            for job_index, job in enumerate(job_listings):
                try:
                    title_elem = job.find('h2', class_='title') or job.find('a', attrs={'data-jk': True})
                    title = title_elem.text.strip() if title_elem else "N/A"
                    
                    company_elem = job.find('span', class_='company') or job.find('a', class_='turnstileLink')
                    company = company_elem.text.strip() if company_elem else "N/A"
                    
                    location_elem = job.find('div', class_='recJobLoc') or job.find('div', class_='companyLocation')
                    location = location_elem.text.strip() if location_elem else "Zimbabwe"
                    
                    summary_elem = job.find('div', class_='summary')
                    description = summary_elem.text.strip() if summary_elem else "See full description on Indeed"
                    
                    expiry_date = "N/A"
                    
                    job_id = f"ID_{page_num:03d}_{job_index+1:03d}_{datetime.now().strftime('%Y%m%d')}"
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
                        "Source Site": self.site_name,
                        "sourceSite": self.site_name,
                        "Apply Email": "Apply on ZimboJobs",
                        "applyEmail": "Apply on ZimboJobs"
                    })
                    
                except Exception as e:
                    logging.warning(f"Error processing Zimbo Jobs {job_index}: {e}")
                    continue
            
            return jobs_data, soup
            
        except Exception as e:
            logging.error(f"Error scraping Zimbo Jobs {page_num}: {e}")
            return [], None

def scrape_multiple_sites(test_mode=False):
    """Main function to scrape jobs from multiple websites."""
    logging.info("Starting multi-site job scraping...")
    print("Starting multi-site job scraping...")
    if test_mode:
        print("** RUNNING IN TEST MODE - FIRST PAGE ONLY **")
    
    # Initialize scrapers for different job sites
    scrapers = [
        VacancyMailScraper(),
        JobsZimbabweScraper(),
        ZimboJobsScraper(),
    ]
    
    all_jobs_data = []
    site_stats = {}
    
    for scraper in scrapers:
        try:
            jobs = scraper.scrape_jobs(test_mode)
            all_jobs_data.extend(jobs)
            site_stats[scraper.site_name] = len(jobs)
            
            # Add delay between different sites
            time.sleep(2)
            
        except Exception as e:
            logging.error(f"Failed to scrape {scraper.site_name}: {e}")
            print(f"Failed to scrape {scraper.site_name}: {e}")
            site_stats[scraper.site_name] = 0
    
    if not all_jobs_data:
        logging.warning("No jobs found from any site.")
        print("No jobs found from any site.")
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
    categories = df['Category'].value_counts()
    sources = df['Source Site'].value_counts()
    
    # Email statistics
    email_success = len(df[df['Apply Email'] != 'N/A'])
    email_total = len(df)
    email_rate = (email_success / email_total * 100) if email_total > 0 else 0
    
    logging.info(f"Successfully scraped {total_jobs} current jobs from {len(scrapers)} sites")
    logging.info(f"Data saved to {filename} and {json_filename} at {pd.Timestamp.now()}")
    logging.info(f"Jobs filtered to show only those expiring on or after {current_date}")
    logging.info(f"Email extraction success rate: {email_success}/{email_total} ({email_rate:.1f}%)")
    logging.info(f"Jobs by site: {site_stats}")
    
    print(f"Successfully scraped {total_jobs} current jobs from {len(scrapers)} sites")
    print(f"Data saved to:")
    print(f"  CSV: {filename}")
    print(f"  JSON: {json_filename}")
    print(f"Jobs filtered to show only those expiring on or after {current_date}")
    print(f"Email extraction: {email_success}/{email_total} jobs ({email_rate:.1f}% success rate)")
    print(f"\nJobs by Source:")
    for site, count in site_stats.items():
        print(f"  {site}: {count} jobs")
    print(f"\nJob Statistics:")
    print(f"- Total jobs found: {total_jobs}")
    print(f"- Jobs by location:")
    for location, count in locations.head(5).items():
        print(f"  {location}: {count}")
    print(f"- Jobs by category:")
    for category, count in categories.head(5).items():
        print(f"  {category}: {count}")
    if not test_mode:
        print(f"- Jobs by expiry date:")
        for expiry, count in df_summary.head(5).items():
            print(f"  {expiry}: {count}")

# Legacy function for backward compatibility
def scrape_jobs(test_mode=False):
    """Legacy function - calls the new multi-site scraper."""
    return scrape_multiple_sites(test_mode)

if __name__ == "__main__":
    logging.info("Starting the web scraper...")
    print("Starting the web scraper...")
    
    # Check if running in test mode
    import sys
    test_mode = "--test" in sys.argv or "test" in sys.argv
    
    scrape_jobs(test_mode=test_mode)  # Call the function to execute scraping
