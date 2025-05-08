# News_Engine
News Scraper for Cement Industry Trends
This project scrapes trending news related to the cement industry, including topics like export tariffs, fuel price hikes, cement subsidies, and more. It fetches data from various sources, processes it, and sends out a daily email summary.

# Features
- Fetches trending queries using Google Trends (via pytrends).
- Collects news articles using the NewsAPI.
- Scrapes news related to the cement industry, including specific countries (e.g., Thailand, Japan, Pakistan).
- Saves the data to a CSV file for further analysis.
- Sends a daily email summary with the top news articles.

# Prerequisites
- To run this project locally, you need:
- Python 3.x
- An active NewsAPI key for fetching news data.
- A valid email configuration for sending daily reports.

# Installation
1. Clone this repository ` git clone https://github.com/your-username/news-scraper.git `
   
2. Navigate into the project directory ` cd news-scraper `
   
3. Install the required dependencies ` pip install -r requirements.txt `
   
4. Create a .env file in the project root with your environment variables. Example:
` NEWS_API_KEY=your_news_api_key 
 EMAIL_HOST=smtp.your-email-provider.com 
 EMAIL_PORT=587 
 EMAIL_USER=your-email@example.com 
 EMAIL_PASSWORD=your-email-password 
 EMAIL_TO=recipient-email@example.com `
   
Replace the placeholders with your actual credentials.

# Usage
## Running Locally
To run the script locally and fetch the latest news:
- Make sure your .env file is set up correctly.
  
- Run the script ` python news_scraper.py `
  This will fetch the top trending queries, collect news articles, save them in a CSV file, and send an email with the daily summary.

## Running via GitHub Actions
This project is set up to run daily via GitHub Actions at 1 AM UTC. The action will:
  - Scrape news articles related to the cement industry.
  - Save the data in a CSV file.
  - Send a daily email summary.
The schedule is configured using cron jobs. You can also manually trigger the workflow via the GitHub Actions tab.

# License
This project is licensed under the MIT License.

