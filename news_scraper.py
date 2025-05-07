import requests
import csv
import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime

API_KEY = os.getenv("NEWS_API_KEY")
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")

BASE_URL = "https://newsapi.org/v2/everything"

countries = ["India", "Thailand", "Indonesia", "Vietnam", "Oman", "Pakistan", "China", "Japan", "Korea"]
topics = ["trade", "construction", "shipping", "clinker", "cement", "logistics", "import", "export", "infrastructure"]

def get_news(query):
    params = {
        "q": query,
        "apiKey": API_KEY,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 20
    }
    response = requests.get(BASE_URL, params=params)
    return response.json().get("articles", [])

def send_email(content):
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = "📰 Daily Cement News Summary"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)
        
def main():
    now = datetime.utcnow().strftime("%Y-%m-%d")
    news_summary = f"News Summary for {now}\n\n"
    all_articles = []

    for country in countries:
        for topic in topics:
            query = f"{topic} AND {country}"
            articles = get_news(query)
            for article in articles:
                entry = f"{article['publishedAt']} | {article['title']} | {article['url']}"
                all_articles.append(entry)

    news_summary += "\n".join(all_articles)

    # Optional: Save as CSV too
    filename = f"news_{now}.csv"
    with open(filename, mode="w", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["PublishedAt", "Title", "Source", "URL", "Country", "Topic"])
        for entry in all_articles:
            parts = entry.split(" | ")
            if len(parts) == 3:
                writer.writerow([parts[0], parts[1], "", parts[2], "", ""])

    send_email(news_summary)

if __name__ == "__main__":
    main()
