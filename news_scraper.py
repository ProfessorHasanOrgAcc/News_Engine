import requests
import csv
import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from .env file (useful for local testing)
load_dotenv()

API_KEY = os.getenv("NEWS_API_KEY")
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")

# Check for missing variables
required_env = [API_KEY, EMAIL_HOST, EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO]
if not all(required_env):
    raise EnvironmentError("Missing one or more required environment variables.")

BASE_URL = "https://newsapi.org/v2/everything"

countries = ["India", "Thailand", "Indonesia", "Vietnam", "Oman", "Pakistan", "China", "Japan", "Korea"]
topics = ["trade", "construction", "shipping", "clinker", "cement", "logistics", "import", "export", "infrastructure"]
    
def get_news(query):
    try:
        response = requests.get(BASE_URL, params={
            "q": query,
            "apiKey": API_KEY,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 20
        })
        response.raise_for_status()
        return response.json().get("articles", [])
    except requests.RequestException as e:
        print(f"Failed to fetch news for query '{query}': {e}")
        return []

def send_email(content):
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = "📰 Daily Cement News Summary"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        print("[INFO] Email sent successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
        
def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    news_summary = f"News Summary for {now}\n\n"
    all_articles = []

    for country in countries:
        for topic in topics:
            query = f"{topic} AND {country}"
            articles = get_news(query)
            for article in articles:
                publishedAt = article.get("publishedAt", "")
                title = article.get("title", "")
                url = article.get("url", "")
                source = article.get("source", {}).get("name", "")
                all_articles.append((publishedAt, title, url, source, country, topic))

    if not all_articles:
        news_summary += "No articles found."
    else:
        for entry in all_articles:
            publishedAt, title, url, _, country, topic = entry
            news_summary += f"{publishedAt} | {title} | {url} ({country}, {topic})\n"
    
    # Save as CSV
    filename = f"news_{now}.csv"
    with open(filename, mode="w", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["PublishedAt", "Title", "Source", "URL", "Country", "Topic"])
        for entry in all_articles:
            writer.writerow(entry)

    send_email(news_summary)

if __name__ == "__main__":
    main()
