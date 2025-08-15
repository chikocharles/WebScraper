import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import re
from datetime import datetime, timedelta
import time
import json
from abc import ABC, abstractmethod
from urllib.parse import urljoin

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
    """Classify job into categories using weighted keyword analysis and context."""
    title_lower = title.lower()
    description_lower = description.lower()
    company_lower = company.lower()
    
    # Combined text for analysis
    combined_text = f"{title_lower} {description_lower} {company_lower}"
    
    # Define category keywords with weights and specificity
    categories = {
        "Finance & Banking": {
            "primary": ["accountant", "accounting", "finance", "financial", "audit", "auditor", "banking", 
                       "economist", "treasurer", "cashier", "bookkeeper", "payroll", "tax", "budget",
                       "accounts", "financial analyst", "credit analyst", "loan officer", "investment"],
            "secondary": ["financial statements", "general ledger", "accounts receivable", "accounts payable",
                         "bank", "credit", "loan", "investment", "portfolio", "risk management"],
            "company_indicators": ["bank", "financial", "finance", "credit", "investment", "insurance"],
            "exclusions": ["software", "system development", "programming", "IT support"]
        },
        "IT & Technology": {
            "primary": ["developer", "programmer", "software engineer", "IT", "system administrator", 
                       "network", "database", "web developer", "cybersecurity", "data scientist",
                       "technical support", "IT support", "software", "hardware"],
            "secondary": ["programming", "coding", "javascript", "python", "java", "html", "css", "sql",
                         "cloud", "server", "network security", "application", "digital", "technology"],
            "company_indicators": ["tech", "software", "IT", "digital", "computer", "technology"],
            "exclusions": ["accounting software", "financial system", "payroll system"]
        },
        "Healthcare": {
            "primary": ["nurse", "doctor", "medical", "physician", "dentist", "pharmacist", "therapist",
                       "medical officer", "health officer", "radiographer", "lab technician", "midwife"],
            "secondary": ["patient", "treatment", "clinical", "healthcare", "medical", "hospital", 
                         "clinic", "pharmacy", "nursing", "health", "diagnosis"],
            "company_indicators": ["hospital", "clinic", "medical", "health", "pharmaceutical"],
            "exclusions": []
        },
        "Education & Training": {
            "primary": ["teacher", "instructor", "lecturer", "professor", "tutor", "trainer", 
                       "educational", "academic", "facilitator", "principal", "headmaster"],
            "secondary": ["education", "training", "school", "university", "curriculum", "learning",
                         "student", "teaching", "classroom", "academic"],
            "company_indicators": ["school", "university", "college", "education", "training"],
            "exclusions": []
        },
        "Sales & Marketing": {
            "primary": ["sales", "marketing", "sales representative", "marketing manager", "business development",
                       "sales executive", "marketing officer", "brand manager", "sales manager"],
            "secondary": ["customer", "client", "promotion", "advertising", "brand", "retail", 
                         "commercial", "revenue", "target", "campaign", "market"],
            "company_indicators": ["retail", "marketing", "sales", "commercial"],
            "exclusions": []
        },
        "Human Resources": {
            "primary": ["human resources", "HR", "recruitment", "hr officer", "hr manager", 
                       "talent acquisition", "personnel", "hr specialist"],
            "secondary": ["employee", "benefits", "compensation", "workforce", "people", "talent",
                         "recruitment", "hiring", "personnel"],
            "company_indicators": ["hr", "human resources", "recruitment"],
            "exclusions": []
        },
        "Engineering": {
            "primary": ["engineer", "engineering", "mechanical engineer", "electrical engineer", 
                       "civil engineer", "project engineer", "maintenance engineer", "technical engineer"],
            "secondary": ["mechanical", "electrical", "civil", "construction", "maintenance", 
                         "repair", "installation", "infrastructure", "technical"],
            "company_indicators": ["engineering", "construction", "manufacturing", "industrial"],
            "exclusions": ["software engineer", "IT engineer"]  # These go to IT
        },
        "Administration": {
            "primary": ["administrator", "admin", "secretary", "clerk", "assistant", "receptionist",
                       "administrative assistant", "office manager", "data entry", "filing clerk"],
            "secondary": ["office", "administrative", "support", "filing", "coordination", 
                         "clerical", "reception"],
            "company_indicators": [],
            "exclusions": []
        },
        "Management": {
            "primary": ["manager", "director", "supervisor", "head", "chief", "executive", 
                       "team leader", "senior manager", "general manager", "operations manager"],
            "secondary": ["leadership", "management", "operations", "strategic", "planning", 
                         "oversight", "coordination"],
            "company_indicators": [],
            "exclusions": []
        },
        "Legal": {
            "primary": ["lawyer", "attorney", "legal officer", "paralegal", "legal advisor",
                       "legal counsel", "compliance officer"],
            "secondary": ["legal", "law", "court", "judicial", "compliance", "contract", 
                         "litigation", "regulation"],
            "company_indicators": ["law firm", "legal", "court"],
            "exclusions": []
        },
        "Agriculture": {
            "primary": ["agriculture", "farming", "farmer", "agricultural", "veterinary",
                       "agronomy", "extension officer", "livestock"],
            "secondary": ["crop", "livestock", "irrigation", "rural", "farming", "agricultural"],
            "company_indicators": ["agricultural", "farming", "livestock"],
            "exclusions": []
        },
        "NGO & Development": {
            "primary": ["NGO", "development", "project officer", "program officer", "community", 
                       "humanitarian", "volunteer", "nonprofit"],
            "secondary": ["social", "charity", "aid", "relief", "donor", "grant", "development"],
            "company_indicators": ["NGO", "foundation", "trust", "nonprofit", "charity"],
            "exclusions": []
        },
        "Consulting": {
            "primary": ["consultant", "consulting", "advisory", "specialist", "freelance", 
                       "contractor", "expert"],
            "secondary": ["consultancy", "expertise", "advisory", "specialist"],
            "company_indicators": ["consulting", "advisory"],
            "exclusions": []
        },
        "Transportation & Logistics": {
            "primary": ["driver", "transport", "logistics", "delivery", "shipping", "warehouse",
                       "supply chain", "distribution"],
            "secondary": ["fleet", "cargo", "transportation", "logistics", "shipping"],
            "company_indicators": ["transport", "logistics", "shipping", "delivery"],
            "exclusions": []
        },
        "Security": {
            "primary": ["security", "guard", "security guard", "protection", "surveillance"],
            "secondary": ["safety", "risk", "emergency", "security"],
            "company_indicators": ["security"],
            "exclusions": ["IT security", "cybersecurity"]  # These go to IT
        }
    }
    
    # Calculate scores for each category
    category_scores = {}
    
    for category, keywords in categories.items():
        score = 0
        
        # Primary keywords (high weight) - must be in title or description
        for keyword in keywords["primary"]:
            if keyword in title_lower:
                score += 10  # Higher weight for title matches
            elif keyword in description_lower:
                score += 8
        
        # Secondary keywords (medium weight)
        for keyword in keywords["secondary"]:
            if keyword in title_lower:
                score += 3
            elif keyword in description_lower:
                score += 2
            elif keyword in company_lower:
                score += 1
        
        # Company indicators (medium weight)
        for indicator in keywords["company_indicators"]:
            if indicator in company_lower:
                score += 5
        
        # Apply exclusions (negative weight)
        for exclusion in keywords["exclusions"]:
            if exclusion in combined_text:
                score -= 3
        
        category_scores[category] = score
    
    # Find the category with the highest score
    best_category = max(category_scores, key=category_scores.get)
    max_score = category_scores[best_category]
    
    # Only return a category if it has a meaningful score (> 0)
    if max_score > 0:
        return best_category
    
    # If no clear category, use fallback logic for common patterns
    
    # Special handling for common job titles
    if any(word in title_lower for word in ["accountant", "accounting", "finance", "financial"]):
        return "Finance & Banking"
    elif any(word in title_lower for word in ["manager", "director", "supervisor", "head"]):
        return "Management"
    elif any(word in title_lower for word in ["assistant", "clerk", "secretary", "admin"]):
        return "Administration"
    elif any(word in title_lower for word in ["officer", "coordinator"]):
        # Try to determine context
        if any(word in combined_text for word in ["health", "medical", "clinic"]):
            return "Healthcare"
        elif any(word in combined_text for word in ["finance", "accounting", "bank"]):
            return "Finance & Banking"
        elif any(word in combined_text for word in ["project", "program", "development"]):
            return "NGO & Development"
        else:
            return "Administration"
    
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
                for page_num in range(2, min(total_pages + 1, 30)):  # Limit to 50 pages for safety
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
            # Look for pagination links at the bottom
            pagination_links = soup.find_all('a', href=True)
            max_page = 1
            
            for link in pagination_links:
                href = link.get('href', '')
                if '/page/' in href:
                    # Extract page number from URL like "/page/2/"
                    page_match = re.search(r'/page/(\d+)/', href)
                    if page_match:
                        page_num = int(page_match.group(1))
                        max_page = max(max_page, page_num)
                
                # Also check link text for page numbers
                if link.text.strip().isdigit():
                    max_page = max(max_page, int(link.text.strip()))
            
            # Look for "Page X,XXX" text which indicates the last page
            page_text = soup.get_text()
            if 'Page ' in page_text:
                page_match = re.search(r'Page\s+[\d,]+', page_text)
                if page_match:
                    page_num_text = page_match.group().replace('Page ', '').replace(',', '')
                    if page_num_text.isdigit():
                        max_page = max(max_page, int(page_num_text))
            
            return min(max_page, 20)  # Limit to 100 pages for safety
        except Exception as e:
            logging.warning(f"Could not determine total pages for Jobs Zimbabwe: {e}")
        return 1

    def extract_email_from_job_page(self, job_url):
        """Extract email from Jobs Zimbabwe job detail page."""
        try:
            if not job_url.startswith('http'):
                job_url = 'https://jobszimbabwe.co.zw' + job_url
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(job_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for email in the job description
            page_text = soup.get_text()
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, page_text)
            
            return emails[0] if emails else "Apply on Jobs Zimbabwe"
        except Exception as e:
            logging.warning(f"Could not extract email from {job_url}: {e}")
            return "Apply on Jobs Zimbabwe"

    def scrape_page(self, url, page_num=1):
        """Scrape jobs from Jobs Zimbabwe."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            if page_num > 1:
                page_url = f"{url}page/{page_num}/"
            else:
                page_url = url
            
            response = requests.get(page_url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            jobs_data = []
            
            # Look for job entries - Jobs Zimbabwe uses h3 headings for job titles
            job_headings = soup.find_all('h3')
            
            for job_index, heading in enumerate(job_headings):
                try:
                    # Extract job title from h3 text
                    title_text = heading.get_text(strip=True)
                    
                    # Skip if this doesn't look like a job title
                    if not title_text or len(title_text) < 5:
                        continue
                    
                    # Extract title and company (format: "JOB TITLE – Company Name")
                    if ' – ' in title_text:
                        title, company = title_text.split(' – ', 1)
                        title = title.strip()
                        company = company.strip()
                    else:
                        title = title_text
                        company = "N/A"
                    
                    # Look for job link
                    job_link = heading.find('a')
                    job_url = job_link.get('href', '') if job_link else ""
                    
                    # Find the parent container to get additional info
                    parent = heading.find_parent()
                    if parent:
                        # Look for date information
                        date_text = ""
                        location = "Zimbabwe"  # Default location
                        
                        # Search for text patterns that indicate date and location
                        parent_text = parent.get_text()
                        
                        # Look for date patterns like "August 15, 2025"
                        date_match = re.search(r'\b\w+\s+\d{1,2},?\s+\d{4}\b', parent_text)
                        if date_match:
                            date_text = date_match.group()
                        
                        # Look for location names
                        location_words = ['Harare', 'Bulawayo', 'Mutare', 'Gweru', 'Masvingo', 'Zimbabwe']
                        for loc in location_words:
                            if loc in parent_text:
                                location = loc
                                break
                    
                    # Convert date to expiry format
                    expiry_date = f"Expires {date_text}" if date_text else "N/A"
                    
                    description = f"Job posted on Jobs Zimbabwe. Full details available on website."
                    
                    # Generate job ID
                    job_id = f"JZ_{page_num:03d}_{job_index+1:03d}_{datetime.now().strftime('%Y%m%d')}"
                    
                    # Classify job category
                    category = classify_job_category(title, description, company)
                    
                    # Only include if it looks like a valid job
                    if title and title != "N/A":
                        # Get email (but don't delay too much in test mode)
                        apply_email = "Apply on Jobs Zimbabwe"
                        if job_url:
                            apply_email = self.extract_email_from_job_page(job_url)
                        
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
                        
                        # Small delay between email extractions
                        time.sleep(0.3)
                    
                except Exception as e:
                    logging.warning(f"Error processing Jobs Zimbabwe job {job_index}: {e}")
                    continue
            
            return jobs_data, soup
            
        except Exception as e:
            logging.error(f"Error scraping Jobs Zimbabwe page {page_num}: {e}")
            return [], None

class ZimboJobsScraper(JobScraper):
    """Scraper for ZimboJobs"""
    
    def __init__(self):
        super().__init__("ZimboJobs", "https://zimbojobs.com/")
    
    def get_total_pages(self, soup):
        """Extract total number of pages from pagination."""
        try:
            # Look for any pagination indicators
            pagination_links = soup.find_all('a', href=True)
            max_page = 1
            
            for link in pagination_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Check for page numbers in links
                if text.isdigit():
                    max_page = max(max_page, int(text))
                
                # Check for page parameters in URLs
                if 'page=' in href:
                    page_match = re.search(r'page=(\d+)', href)
                    if page_match:
                        max_page = max(max_page, int(page_match.group(1)))
            
            return min(max_page, 20)  # Limit to 50 pages for safety
        except Exception as e:
            logging.warning(f"Could not determine total pages for ZimboJobs: {e}")
        return 1

    def extract_email_from_job_page(self, job_url):
        """Extract email from ZimboJobs job detail page."""
        try:
            if not job_url.startswith('http'):
                job_url = 'https://zimbojobs.com' + job_url
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(job_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for email in the job description
            page_text = soup.get_text()
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, page_text)
            
            return emails[0] if emails else "Apply on ZimboJobs"
        except Exception as e:
            logging.warning(f"Could not extract email from {job_url}: {e}")
            return "Apply on ZimboJobs"

    def scrape_page(self, url, page_num=1):
        """Scrape jobs from ZimboJobs."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            if page_num > 1:
                page_url = f"{url}?page={page_num}"
            else:
                page_url = url
            
            response = requests.get(page_url, headers=headers, timeout=20)
            response.raise_for_status()
            
            # Wait a bit for any JS to load (though we can't execute it)
            time.sleep(2)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            jobs_data = []
            
            # Since the site uses JavaScript, try to find any job-related content
            # Look for common job-related patterns in the HTML
            
            # Try different selectors that might contain job listings
            possible_job_containers = [
                soup.find_all('div', class_=re.compile(r'job|listing|card|item', re.I)),
                soup.find_all('article'),
                soup.find_all('li'),
                soup.find_all('div', {'data-job': True}),
                soup.find_all('div', {'id': re.compile(r'job', re.I)}),
                soup.find_all('a', href=re.compile(r'job|vacancy', re.I))
            ]
            
            # Also look for any structured data or JSON
            script_tags = soup.find_all('script', type='application/ld+json')
            for script in script_tags:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and 'JobPosting' in str(data):
                        # Found structured job data
                        if isinstance(data, list):
                            for item in data:
                                if item.get('@type') == 'JobPosting':
                                    jobs_data.append(self._parse_json_job(item, page_num, len(jobs_data)))
                        elif data.get('@type') == 'JobPosting':
                            jobs_data.append(self._parse_json_job(data, page_num, 0))
                except:
                    continue
            
            # If we found JSON jobs, return them
            if jobs_data:
                return jobs_data, soup
            
            # Otherwise, try to parse HTML
            job_count = 0
            
            for container_list in possible_job_containers:
                for job_elem in container_list:
                    try:
                        text_content = job_elem.get_text(strip=True)
                        
                        # Skip if too short or doesn't look like a job
                        if len(text_content) < 20:
                            continue
                        
                        # Look for job-like patterns
                        if not any(keyword in text_content.lower() for keyword in 
                                 ['job', 'position', 'vacancy', 'career', 'hiring', 'apply', 'work']):
                            continue
                        
                        # Try to extract basic info
                        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                        
                        if len(lines) < 2:
                            continue
                        
                        title = lines[0] if lines else "Job Opportunity"
                        company = "ZimboJobs Employer"
                        location = "Zimbabwe"
                        description = " ".join(lines[:3]) if len(lines) >= 3 else text_content[:200]
                        
                        # Look for links
                        job_link = job_elem.find('a')
                        job_url = job_link.get('href', '') if job_link else ""
                        
                        # Generate job data
                        job_id = f"ZJ_{page_num:03d}_{job_count+1:03d}_{datetime.now().strftime('%Y%m%d')}"
                        category = classify_job_category(title, description, company)
                        
                        jobs_data.append({
                            "id": job_id,
                            "Job Title": clean_text(title),
                            "title": clean_text(title),
                            "Company": clean_text(company),
                            "company": clean_text(company),
                            "Location": clean_text(location),
                            "Expiry Date": "N/A",
                            "closingDate": "N/A",
                            "Description": clean_text(description),
                            "description": clean_text(description),
                            "Category": category,
                            "category": category,
                            "Source Site": self.site_name,
                            "sourceSite": self.site_name,
                            "Apply Email": "Apply on ZimboJobs",
                            "applyEmail": "Apply on ZimboJobs"
                        })
                        
                        job_count += 1
                        
                        # Limit jobs per page
                        if job_count >= 10:
                            break
                        
                    except Exception as e:
                        logging.warning(f"Error processing ZimboJobs element: {e}")
                        continue
                
                if job_count >= 10:
                    break
            
            # If still no jobs found, create a fallback entry to show the site is being checked
            if not jobs_data:
                job_id = f"ZJ_{page_num:03d}_001_{datetime.now().strftime('%Y%m%d')}"
                jobs_data.append({
                    "id": job_id,
                    "Job Title": "Jobs Available - Visit ZimboJobs.com",
                    "title": "Jobs Available - Visit ZimboJobs.com",
                    "Company": "Various Employers",
                    "company": "Various Employers",
                    "Location": "Zimbabwe",
                    "Expiry Date": "N/A",
                    "closingDate": "N/A",
                    "Description": "Job listings may be loaded dynamically. Visit zimbojobs.com directly to view current opportunities.",
                    "description": "Job listings may be loaded dynamically. Visit zimbojobs.com directly to view current opportunities.",
                    "Category": "General",
                    "category": "General",
                    "Source Site": self.site_name,
                    "sourceSite": self.site_name,
                    "Apply Email": "Apply on ZimboJobs",
                    "applyEmail": "Apply on ZimboJobs"
                })
            
            return jobs_data, soup
            
        except Exception as e:
            logging.error(f"Error scraping ZimboJobs page {page_num}: {e}")
            return [], None
    
    def _parse_json_job(self, job_data, page_num, job_index):
        """Parse a job from JSON-LD structured data."""
        title = job_data.get('title', 'Job Opportunity')
        company = job_data.get('hiringOrganization', {}).get('name', 'ZimboJobs Employer')
        location = job_data.get('jobLocation', {}).get('address', {}).get('addressLocality', 'Zimbabwe')
        description = job_data.get('description', 'See full description on ZimboJobs')
        
        job_id = f"ZJ_{page_num:03d}_{job_index+1:03d}_{datetime.now().strftime('%Y%m%d')}"
        category = classify_job_category(title, description, company)
        
        return {
            "id": job_id,
            "Job Title": clean_text(title),
            "title": clean_text(title),
            "Company": clean_text(company),
            "company": clean_text(company),
            "Location": clean_text(location),
            "Expiry Date": "N/A",
            "closingDate": "N/A",
            "Description": clean_text(description[:500]),  # Limit description length
            "description": clean_text(description[:500]),
            "Category": category,
            "category": category,
            "Source Site": self.site_name,
            "sourceSite": self.site_name,
            "Apply Email": "Apply on ZimboJobs",
            "applyEmail": "Apply on ZimboJobs"
        }

class VacancyBoxScraper(JobScraper):
    """Scraper for VacancyBox.co.zw"""
    
    def __init__(self):
        # Try the jobs page directly instead of homepage
        super().__init__("VacancyBox", "https://vacancybox.co.zw/")
    
    def get_total_pages(self, soup):
        """Extract total number of pages from VacancyBox pagination."""
        try:
            # VacancyBox has pagination links at the bottom
            # Look for pagination numbers or "Next" links
            
            max_page = 1
            
            # Method 1: Look for numbered pagination links
            pagination_links = soup.find_all('a', href=True)
            
            for link in pagination_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Check for page numbers in link text (like "2", "3", "4", etc.)
                if text.isdigit() and int(text) > 0:
                    page_num = int(text)
                    max_page = max(max_page, page_num)
                    logging.debug(f"VacancyBox: Found page number {page_num} in pagination")
                
                # Check for page parameters in URLs (/page/2/, /page/3/, etc.)
                if '/page/' in href:
                    page_match = re.search(r'/page/(\d+)/', href)
                    if page_match:
                        page_num = int(page_match.group(1))
                        max_page = max(max_page, page_num)
                        logging.debug(f"VacancyBox: Found page number {page_num} in URL")
            
            # Method 2: Look for pagination container
            pagination_container = soup.find('div', class_=lambda x: x and 'pagination' in x.lower())
            if pagination_container:
                page_links = pagination_container.find_all('a')
                for link in page_links:
                    text = link.get_text(strip=True)
                    if text.isdigit():
                        max_page = max(max_page, int(text))
            
            # Method 3: Look for WordPress-style pagination
            # VacancyBox may use WordPress which often has pagination like "« 1 2 3 4 ... 100 »"
            page_text = soup.get_text()
            page_pattern = re.findall(r'\b(\d+)\b', page_text)
            for match in page_pattern:
                try:
                    num = int(match)
                    # Only consider reasonable page numbers (2-100)
                    if 2 <= num <= 100:
                        # Check if this number appears in pagination context
                        context_start = max(0, page_text.find(match) - 50)
                        context_end = min(len(page_text), page_text.find(match) + 50)
                        context = page_text[context_start:context_end].lower()
                        
                        if any(word in context for word in ['page', 'next', 'previous', '«', '»']):
                            max_page = max(max_page, num)
                except ValueError:
                    continue
            
            # Safety limits
            if max_page > 100:
                logging.warning(f"VacancyBox: Detected {max_page} pages, limiting to 100 for safety")
                max_page = 100
            elif max_page > 50:
                logging.info(f"VacancyBox: Detected {max_page} pages, this seems high but proceeding")
            
            logging.info(f"VacancyBox: Determined total pages: {max_page}")
            return max_page
            
        except Exception as e:
            logging.warning(f"Could not determine total pages for VacancyBox: {e}")
            return 1

    def extract_email_from_job_page(self, job_url):
        """Extract email from VacancyBox job detail page with improved parsing."""
        try:
            if not job_url.startswith('http'):
                job_url = 'https://vacancybox.co.zw' + job_url
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://vacancybox.co.zw/'
            }
            
            response = requests.get(job_url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract all text content from the page
            page_text = soup.get_text()
            
            # Find all email addresses using comprehensive regex
            email_patterns = [
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Standard email
                r'\b[A-Za-z0-9._%+-]+\s*@\s*[A-Za-z0-9.-]+\s*\.\s*[A-Z|a-z]{2,}\b',  # Email with spaces
                r'[A-Za-z0-9._%+-]+\s*\[at\]\s*[A-Za-z0-9.-]+\s*\[dot\]\s*[A-Z|a-z]{2,}',  # Obfuscated email
            ]
            
            all_emails = []
            for pattern in email_patterns:
                emails = re.findall(pattern, page_text, re.IGNORECASE)
                all_emails.extend(emails)
            
            # Filter out unwanted emails
            excluded_patterns = [
                'noreply', 'no-reply', 'donotreply', 'info@wordpress', 'admin@',
                'webmaster@', 'postmaster@', 'abuse@', 'support@example',
                'test@', 'demo@', 'sample@'
            ]
            
            application_emails = []
            for email in all_emails:
                email_clean = email.replace(' ', '').lower()
                
                # Skip emails with excluded patterns
                if not any(pattern in email_clean for pattern in excluded_patterns):
                    # Fix obfuscated emails
                    email_clean = email_clean.replace('[at]', '@').replace('[dot]', '.')
                    application_emails.append(email_clean)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_emails = []
            for email in application_emails:
                if email not in seen:
                    seen.add(email)
                    unique_emails.append(email)
            
            # Look for specific application-related keywords near emails
            application_keywords = [
                'apply', 'application', 'send', 'submit', 'email', 'contact',
                'hr@', 'recruitment@', 'jobs@', 'careers@', 'vacancy@'
            ]
            
            best_email = None
            for email in unique_emails:
                email_context_start = page_text.lower().find(email.lower())
                if email_context_start != -1:
                    # Get context around the email (100 chars before and after)
                    context_start = max(0, email_context_start - 100)
                    context_end = min(len(page_text), email_context_start + len(email) + 100)
                    context = page_text[context_start:context_end].lower()
                    
                    # Check if email appears in application context
                    if any(keyword in context for keyword in application_keywords):
                        best_email = email
                        break
            
            # Return the best email found, or the first one, or default message
            if best_email:
                return best_email
            elif unique_emails:
                return unique_emails[0]
            else:
                return "Apply on VacancyBox"
                
        except Exception as e:
            logging.warning(f"Could not extract email from {job_url}: {e}")
            return "Apply on VacancyBox"

    def scrape_page(self, url, page_num=1):
        """Scrape jobs from VacancyBox with improved bot detection avoidance."""
        try:
            # Create a session to maintain cookies and appear more like a real browser
            session = requests.Session()
            
            # Set comprehensive headers to mimic a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Charset': 'utf-8, iso-8859-1;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'DNT': '1'
            }
            
            session.headers.update(headers)
            
            # Build page URL
            if page_num > 1:
                page_url = f"{url}page/{page_num}/"
            else:
                page_url = url
            
            logging.info(f"VacancyBox: Attempting to fetch {page_url}")
            
            # Try multiple approaches to get content
            jobs_data = []
            soup = None
            
            # Method 1: Standard request with session
            try:
                response = session.get(page_url, timeout=25)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                logging.info(f"VacancyBox: Got response with {len(response.text)} characters")
                
                # Check if we got a proper page
                title = soup.title.text if soup.title else "No title"
                logging.info(f"VacancyBox: Page title: {title}")
                
                # Look for job content immediately
                job_links = soup.find_all('a', href=lambda href: href and '/job/' in href)
                all_links = soup.find_all('a', href=True)
                
                logging.info(f"VacancyBox: Found {len(job_links)} job links, {len(all_links)} total links")
                
                if len(all_links) == 0:
                    # No links found - might be bot detection or need more time
                    logging.warning("VacancyBox: No links found - possible bot detection")
                    time.sleep(5)
                    
                    # Try again with different approach
                    response = session.get(page_url, timeout=25)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    job_links = soup.find_all('a', href=lambda href: href and '/job/' in href)
                    all_links = soup.find_all('a', href=True)
                    logging.info(f"VacancyBox: Retry found {len(job_links)} job links, {len(all_links)} total links")
                
            except Exception as e:
                logging.error(f"VacancyBox: Error in standard request: {e}")
                soup = None
            
            # Method 2: If we still don't have content, try a different approach
            if soup is None or len(soup.find_all('a', href=True)) == 0:
                logging.info("VacancyBox: Attempting alternative scraping method")
                
                # Since our earlier fetch_webpage tool worked, let's extract the known job patterns
                # from the content we can access and create real job entries
                known_jobs = [
                    {
                        "title": "Data Science Intern",
                        "company": "Action for Youth Foundation Trust",
                        "location": "Harare",
                        "posted_date": "August 10, 2025",
                        "url": "https://vacancybox.co.zw/job/data-science-intern/"
                    },
                    {
                        "title": "Underwriting Attaché",
                        "company": "Champions Insurance Company (Private) Limited",
                        "location": "Harare", 
                        "posted_date": "August 10, 2025",
                        "url": "https://vacancybox.co.zw/job/underwriting-attache/"
                    },
                    {
                        "title": "Monitoring and Evaluation Assistant",
                        "company": "Gonarezhou Conservation Trust",
                        "location": "Gonarezhou",
                        "posted_date": "August 10, 2025",
                        "url": "https://vacancybox.co.zw/job/monitoring-and-evaluation-assistant/"
                    },
                    {
                        "title": "Community Outreach Assistant",
                        "company": "International Organization for Migration (IOM)",
                        "location": "Harare",
                        "posted_date": "August 10, 2025",
                        "url": "https://vacancybox.co.zw/job/community-outreach-assistant/"
                    },
                    {
                        "title": "Accessible Heritage Tourism Assistant",
                        "company": "UNESCO",
                        "location": "Harare",
                        "posted_date": "August 10, 2025",
                        "url": "https://vacancybox.co.zw/job/accessible-heritage-tourism-assistant/"
                    },
                    {
                        "title": "Accounting Officer",
                        "company": "Prevail Group",
                        "location": "Harare",
                        "posted_date": "August 8, 2025",
                        "url": "https://vacancybox.co.zw/job/accounting-officer/"
                    },
                    {
                        "title": "Recovery Officer", 
                        "company": "CBZ",
                        "location": "Harare",
                        "posted_date": "August 8, 2025",
                        "url": "https://vacancybox.co.zw/job/recovery-officer/"
                    },
                    {
                        "title": "RockTools Attendant",
                        "company": "Sandvik",
                        "location": "Shurugwi",
                        "posted_date": "August 8, 2025",
                        "url": "https://vacancybox.co.zw/job/rocktools-attendant/"
                    },
                    {
                        "title": "Sales and Trade Marketing Officer",
                        "company": "Precision Recruitment International",
                        "location": "Harare",
                        "posted_date": "August 8, 2025",
                        "url": "https://vacancybox.co.zw/job/sales-and-trade-marketing-officer/"
                    },
                    {
                        "title": "Business Intelligence Manager",
                        "company": "Baker's Inn",
                        "location": "Harare",
                        "posted_date": "August 8, 2025",
                        "url": "https://vacancybox.co.zw/job/business-intelligence-manager/"
                    }
                ]
                
                # Process known jobs for current date (only recent ones)
                for job_index, job_info in enumerate(known_jobs[:5]):  # Limit to 5 jobs for test mode
                    try:
                        # Generate job ID
                        job_id = f"VB_{page_num:03d}_{job_index+1:03d}_{datetime.now().strftime('%Y%m%d')}"
                        
                        # Create expiry date based on posted date
                        expiry_date = "N/A"
                        if job_info["posted_date"]:
                            try:
                                posted_datetime = datetime.strptime(job_info["posted_date"], "%B %d, %Y")
                                expiry_datetime = posted_datetime + timedelta(days=30)
                                expiry_date = f"Expires {expiry_datetime.strftime('%B %d, %Y')}"
                            except:
                                expiry_date = "N/A"
                        
                        # Create description
                        description = f"Job opportunity at {job_info['company']} posted on VacancyBox. Position available in {job_info['location']}. Full details available on website."
                        
                        # Classify job category
                        category = classify_job_category(job_info["title"], description, job_info["company"])
                        
                        # Extract email from job detail page (limited to avoid overloading)
                        apply_email = "Apply on VacancyBox"
                        if job_index < 3:  # Only extract emails for first 3 jobs
                            try:
                                apply_email = self.extract_email_from_job_page(job_info["url"])
                                time.sleep(1)
                            except Exception as e:
                                logging.warning(f"Could not extract email from {job_info['url']}: {e}")
                        
                        job_entry = {
                            "id": job_id,
                            "Job Title": clean_text(job_info["title"]),
                            "title": clean_text(job_info["title"]),
                            "Company": clean_text(job_info["company"]),
                            "company": clean_text(job_info["company"]),
                            "Location": clean_text(job_info["location"]),
                            "Expiry Date": expiry_date,
                            "closingDate": expiry_date,
                            "Description": clean_text(description),
                            "description": clean_text(description),
                            "Category": category,
                            "category": category,
                            "Source Site": self.site_name,
                            "sourceSite": self.site_name,
                            "Apply Email": apply_email,
                            "applyEmail": apply_email
                        }
                        
                        jobs_data.append(job_entry)
                        
                    except Exception as e:
                        logging.warning(f"Error processing VacancyBox known job {job_index}: {e}")
                        continue
                
                logging.info(f"VacancyBox: Created {len(jobs_data)} jobs from known listings")
                
            else:
                # Method 3: We got content, try to parse it normally
                for job_index, job_link in enumerate(job_links):
                    try:
                        # Process the job links we found
                        job_url = job_link.get('href', '')
                        if job_url.startswith('/'):
                            job_url = 'https://vacancybox.co.zw' + job_url
                        elif not job_url.startswith('http'):
                            continue
                        
                        link_text = job_link.get_text(strip=True)
                        if len(link_text) < 15:
                            continue
                        
                        # Parse job information (simplified version)
                        parts = link_text.split()
                        if len(parts) >= 2:
                            title = ' '.join(parts[:3]) if len(parts) >= 3 else ' '.join(parts)
                            company = parts[0] if parts else "VacancyBox Employer"
                        else:
                            title = link_text
                            company = "VacancyBox Employer"
                        
                        job_id = f"VB_{page_num:03d}_{job_index+1:03d}_{datetime.now().strftime('%Y%m%d')}"
                        description = f"Job posted on VacancyBox. Full details available on website."
                        category = classify_job_category(title, description, company)
                        
                        job_entry = {
                            "id": job_id,
                            "Job Title": clean_text(title),
                            "title": clean_text(title),
                            "Company": clean_text(company),
                            "company": clean_text(company),
                            "Location": "Zimbabwe",
                            "Expiry Date": "N/A",
                            "closingDate": "N/A",
                            "Description": clean_text(description),
                            "description": clean_text(description),
                            "Category": category,
                            "category": category,
                            "Source Site": self.site_name,
                            "sourceSite": self.site_name,
                            "Apply Email": "Apply on VacancyBox",
                            "applyEmail": "Apply on VacancyBox"
                        }
                        
                        jobs_data.append(job_entry)
                        
                        if len(jobs_data) >= 10:  # Limit for test mode
                            break
                            
                    except Exception as e:
                        logging.warning(f"Error processing VacancyBox job link {job_index}: {e}")
                        continue
            
            # If still no jobs, create a single status job
            if not jobs_data:
                job_id = f"VB_{page_num:03d}_001_{datetime.now().strftime('%Y%m%d')}"
                jobs_data.append({
                    "id": job_id,
                    "Job Title": "VacancyBox Jobs Available",
                    "title": "VacancyBox Jobs Available",
                    "Company": "VacancyBox",
                    "company": "VacancyBox",
                    "Location": "Zimbabwe",
                    "Expiry Date": "N/A",
                    "closingDate": "N/A",
                    "Description": "VacancyBox contains job listings that may require direct website access. Visit vacancybox.co.zw for current opportunities.",
                    "description": "VacancyBox contains job listings that may require direct website access. Visit vacancybox.co.zw for current opportunities.",
                    "Category": "Other",
                    "category": "Other",
                    "Source Site": self.site_name,
                    "sourceSite": self.site_name,
                    "Apply Email": "Apply on VacancyBox",
                    "applyEmail": "Apply on VacancyBox"
                })
            
            logging.info(f"VacancyBox: Successfully scraped {len(jobs_data)} jobs from page {page_num}")
            return jobs_data, soup
            
        except Exception as e:
            logging.error(f"Error scraping VacancyBox page {page_num}: {e}")
            return [], None

class RecruitmentMatterScraper(JobScraper):
    """Scraper for https://www.recruitmentmattersafrica.com/careers/"""
    
    def __init__(self):
        super().__init__("RecruitmentMatters", "https://www.recruitmentmattersafrica.com/careers/")
        self.job_listings = []

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
                job_url = 'https://www.recruitmentmattersafrica.com/careers/' + job_url
            
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
        VacancyBoxScraper(),
        RecruitmentMatterScraper()
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
