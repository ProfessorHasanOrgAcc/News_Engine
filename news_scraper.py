import requests
import csv
import smtplib
import os
import time
from email.mime.text import MIMEText
from datetime import datetime, timezone
from dotenv import load_dotenv
from pytrends.request import TrendReq
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd

# Load environment variables
load_dotenv()

API_KEY = os.getenv("NEWS_API_KEY")
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")

# Validate env
required_env = [API_KEY, EMAIL_HOST, EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO]
if not all(required_env):
    raise EnvironmentError("Missing one or more required environment variables.")

BASE_URL = "https://newsapi.org/v2/everything"

countries = ["Thailand", "Indonesia", "Vietnam", "Oman", "Pakistan", "China", "Japan"]
phrases = [
    "limestone export regulation", "blast furnace slag trade", "gypsum export tariff",
    "clinker logistics bottleneck", "cement domestic consumption", "cement input shortage",
    "limestone mining permit", "cement energy subsidy", "clinker production cost policy",
    "fuel price hike cement", "port congestion clinker export", "rail transport clinker delay"
]

# Setup Pytrends
pytrends = TrendReq(hl='en-US', tz=360)

# Setup retry-enabled session for NewsAPI
session = requests.Session()
retries = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

def get_top_trending_queries(limit=25, sleep_seconds=1, max_checks=50):
    scores = []
    seen_queries = set()
    query_country_map = {}
    checked = 0

    for country in countries:
        for phrase in phrases:
            query = f"{phrase} {country}"
            if query not in seen_queries:
                seen_queries.add(query)
                query_country_map[query] = country

    for query in seen_queries:
        try:
            pytrends.build_payload([query], timeframe='now 1-d')
            df = pytrends.interest_over_time()

            # Workaround for FutureWarning (Pandas fillna)
            if not df.empty:
                df = df.infer_objects(copy=False)
                if query in df.columns:
                    avg_score = df[query].mean()
                    scores.append((query, avg_score))
        except Exception as e:
            print(f"[WARN] Skipping query '{query}': {e}")
        time.sleep(sleep_seconds)
        checked += 1
        if checked >= max_checks:
            break

    sorted_queries = sorted(scores, key=lambda x: x[1], reverse=True)[:limit]
    return sorted_queries, query_country_map

def get_news(query):
    try:
        response = session.get(BASE_URL, params={
            "q": query,
            "apiKey": API_KEY,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 4
        }, timeout=10)
        response.raise_for_status()
        return response.json().get("articles", [])
    except requests.RequestException as e:
        print(f"[ERROR] Failed to fetch news for '{query}': {e}")
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
    news_summary = f"🗓️ News Summary for {now}\n"
    all_articles = []
    country_articles = {country: [] for country in countries}

    top_queries, query_country_map = get_top_trending_queries(limit=25)

    for query, _ in top_queries:
        country = query_country_map.get(query, "Unknown")
        topic = query.replace(country, "").strip()
        articles = get_news(query)

        for article in articles:
            publishedAt = article.get("publishedAt", "")
            title = article.get("title", "")
            url = article.get("url", "")
            source = article.get("source", {}).get("name", "")
            entry = (publishedAt, title, source, url, country, topic)
            country_articles[country].append(entry)
            all_articles.append(entry)

    # Build summary per country
    for country in countries:
        entries = country_articles[country][:3]
        news_summary += f"\n📍 {country}\n"
        if entries:
            for idx, entry in enumerate(entries, 1):
                publishedAt, title, _, url, _, topic = entry
                news_summary += f"  {idx}. [{topic}] {publishedAt} | {title}\n     {url}\n"
        else:
            news_summary += "  No news found.\n"

    # Save to CSV
    filename = f"news_{now}.csv"
    with open(filename, mode="w", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["PublishedAt", "Title", "Source", "URL", "Country", "Topic"])
        for entry in all_articles:
            writer.writerow(entry)

    send_email(news_summary)

if __name__ == "__main__":
    # Fix for pandas FutureWarning globally if needed
    pd.set_option('future.no_silent_downcasting', True)
    main()
