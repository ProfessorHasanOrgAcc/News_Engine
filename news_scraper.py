import requests
import csv
import smtplib
import os
import pandas as pd
import random
import time
import requests
from email.mime.text import MIMEText
from datetime import datetime, timezone
from dotenv import load_dotenv
from pytrends.request import TrendReq
from stem import Signal
from stem.control import Controller

# Load environment variables from .env file (useful for local testing)
load_dotenv()

# Set pandas option to suppress future warnings
pd.set_option('future.no_silent_downcasting', True)



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

countries = ["Thailand", "Indonesia", "Vietnam", "Oman", "Pakistan", "China", "Japan"]
phrases = ["limestone export regulation", "clinker export tariff", "bulk shipping", "cement domestic consumption", 
           "cement input shortage", "cement energy subsidy", "energy policy", "fuel price hike", "port congestion"]


# Initialize pytrends with Tor
proxy_list = ['socks5h://127.0.0.1:9050']
pytrends = TrendReq(proxies=proxies, timeout=(10, 25))  # (connect, read)


def rotate_tor_ip():
    with Controller.from_port(port=9051) as controller:
        controller.authenticate(password="tor_secret_2025")
        controller.signal(Signal.NEWNYM)
    print("[INFO] Tor IP rotated.")

def get_top_trending_queries(limit=25, max_checks=70):
    scores = []
    queries = [f"{phrase} {country}" for country in countries for phrase in phrases]
    
    # Randomize queries
    random.shuffle(queries)
    
    for idx, query in enumerate(queries[:max_checks]):
        print(f"[INFO] Checking {idx+1}/{max_checks} → {query}")
        
        try:
            pytrends.build_payload([query], timeframe='now 1-d')
            interest = pytrends.interest_over_time()
            
            if not interest.empty:
                avg_score = interest[query].mean()
                scores.append((query, avg_score))
                print(f"[INFO] {query} ⟶ {avg_score:.2f}")
            
        except Exception as e:
            print(f"[WARN] {query} failed: {e}")
        
        # Random delay
        time.sleep(random.uniform(10, 25))
        
        # Rotate Tor IP every 10 queries
        if (idx + 1) % 10 == 0:
            rotate_tor_ip()
            ip = requests.get('http://httpbin.org/ip', proxies=proxies).json()
            print("[DEBUG] Current IP via Tor:", ip)
    
    sorted_queries = sorted(scores, key=lambda x: x[1], reverse=True)[:limit]
    return [q for q, _ in sorted_queries]


def get_news(query):
    try:
        response = requests.get(BASE_URL, params={
            "q": query,
            "apiKey": API_KEY,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 3
        })
        response.raise_for_status()
        return response.json().get("articles", [])
    except requests.RequestException as e:
        print(f"Error: Failed to fetch news for '{query}': {e}")
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
    news_summary = f" 🗓 News Summary for {now}\n"
    all_articles = []
    country_articles = {country: [] for country in countries}

    # Get the top 25 trending queries
    top_queries = get_top_trending_queries(limit=25)

    # Fetch news for the top trending queries
    for query in top_queries:
        # Fetching news
        articles = get_news(query)
        matched_country = next((c for c in countries if c.lower() in query.lower()), "Unknown")
        for article in articles:
            publishedAt = article.get("publishedAt", "")
            title = article.get("title", "")
            url = article.get("url", "")
            source = article.get("source", {}).get("name", "")
            topic = query.replace(matched_country, '').strip()
            entry = (publishedAt, title, url, source, matched_country, topic)
            country_articles[matched_country].append(entry)
            all_articles.append(entry)
        
        # Adding random delay between requests (between 1 and 3 seconds)
        time.sleep(random.uniform(1, 3))

    # Organizing news summaries by country
    for country in countries:
        news_summary += f"\n{country}\n"
        entries = country_articles[country]
        if entries:
            for idx, entry in enumerate(entries, 1):
                publishedAt, title, url, _, _, topic = entry
                news_summary += f"  {idx}. [{topic}] {publishedAt} | {title} | {url}\n"
        else:
            news_summary += "  No news found.\n"

    # Save as CSV
    filename = f"news_{now}.csv"
    with open(filename, mode="w", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["PublishedAt", "Title", "Source", "URL", "Country", "Topic"])
        for entry in all_articles:
            writer.writerow(entry)

    # Send the email
    send_email(news_summary)

if __name__ == "__main__":
    main()
