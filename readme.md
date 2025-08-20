*Job Scraper Overview*
This project is a web scraper designed to extract job listings from the Vacancy websites like (https://vacancymail.co.zw/jobs/) and (https://jobszimbabwe.co.zw/). It collects relevant job information from ALL available pages and saves only current job listings (jobs that expire today or in the future) to a CSV file for further analysis or use.

Features
✅ Scrapes job titles, company names, locations, expiry dates, and descriptions from ALL pages (not just the first page)
✅ **NEW**: Automatically detects and scrapes multiple pages to get comprehensive job listings
✅ **NEW**: Filters jobs based on expiry dates - only includes jobs that expire today or later
✅ **NEW**: Displays statistics showing job distribution by location and expiry date
✅ Logs activities and errors to a log file for debugging purposes
✅ Saves the scraped data to timestamped CSV files
✅ Includes respectful delays between page requests to avoid overwhelming the server
✅ Handles various date formats and special characters

Recent Improvements (August 2025)
- **Multi-page scraping**: The scraper now automatically detects and scrapes all available pages, significantly increasing the number of jobs collected (from ~10 to 80+ jobs)
- **Date filtering**: Only jobs with expiry dates on or after today's date are included in the results
- **Enhanced pagination detection**: Improved logic to find all available pages even when pagination info is unclear
- **Statistics display**: Shows breakdown of jobs by location and expiry date
- **Better error handling**: More robust handling of various website structures and edge cases

Requirements
Python 3.x
requests library
BeautifulSoup (part of bs4)
pandas library
datetime (built-in)
time (built-in)

You can install the required libraries using pip:

bash

Copy
pip install requests beautifulsoup4 pandas
Usage
Clone the Repository: If this code is in a Git repository, clone it to your local machine.
bash

Copy
git clone <repository-url>
cd <directory-name>
Run the Scraper: Execute the Python script using the following command:
bash

Copy
python web_scraper.py

The scraper will:
1. Automatically detect how many pages of jobs are available
2. Scrape all pages systematically with respectful delays
3. Filter out expired jobs (keeping only jobs that expire today or later)
4. Display progress and statistics during execution
5. Save results to both a timestamped file and update the main scraped_data.csv

Check Output: After running the script, the scraped job data will be saved in:
- A timestamped file (e.g., `scraped_data_20250807_002057.csv`) 
- The main `scraped_data.csv` file (if not currently open)

You can open these files with any spreadsheet application or text editor.

Log File: Check scraper.log for a detailed log of the scraping process and any errors that may have occurred.

Sample Output
The scraper will display real-time progress and statistics:

```
Starting comprehensive job scraping...
Scraping page 1...
Scraping page 2...
...
Scraped 12 total pages
Successfully scraped 80 current jobs from 12 pages
Data saved to scraped_data_20250807_002057.csv
Jobs filtered to show only those expiring on or after 2025-08-07

Job Statistics:
- Total jobs found: 80
- Jobs by location:
  Harare: 56
  Mutare: 6
  Chipinge: 3
- Jobs by expiry date:
  Expires 08 Aug 2025: 24
  Expires 10 Aug 2025: 10
```

Code Explanation
**Date Filtering**: The script now includes intelligent date parsing that:
- Parses various expiry date formats (e.g., "Expires 24 Aug 2025")
- Compares expiry dates with today's date
- Only includes jobs that haven't expired

**Multi-page Scraping**: The scraper:
- Detects total available pages using multiple methods
- Falls back to sequential page discovery if pagination info is unclear
- Includes respectful 1-second delays between page requests
- Stops when no more jobs are found

**Enhanced Data Processing**: 
- Cleans special characters and normalizes text
- Groups and displays statistics by location and expiry date
- Saves to both timestamped and main CSV files

**Logging Configuration**: The script logs important events and errors to scraper.log with detailed timestamps and information levels.

**Error Handling**: The script includes comprehensive error handling to catch and log exceptions that may occur during the scraping process, ensuring robust operation even when encountering unexpected website changes.


