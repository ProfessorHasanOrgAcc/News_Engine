import requests
import csv
import smtplib
import os
import pandas as pd
import random
import time
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pytrends.request import TrendReq
from stem import Signal
from stem.control import Controller
import nltk
nltk.download('punkt')
from newspaper import Article
from collections import defaultdict
#---------------------------------------------------------------------------------------------------------------------------
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

# List the required environment variables
required_env = ["NEWS_API_KEY", "EMAIL_HOST", "EMAIL_PORT", "EMAIL_USER", "EMAIL_PASSWORD", "EMAIL_TO"]

# Check for missing variables
missing_vars = [var for var in required_env if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(f"Missing the following environment variables: {', '.join(missing_vars)}")

BASE_URL = "https://newsapi.org/v2/everything"


#---------------------------------------------------------------------------------------------------------------------------
def load_country_phrases(filepath="phrases.txt"):
    country_phrase_map = defaultdict(list)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if ':' in line:
                    country, phrase_str = line.strip().split(":", 1)
                    phrases = [p.strip() for p in phrase_str.split(",") if p.strip()]
                    country_phrase_map[country.strip()].extend(phrases)
    except FileNotFoundError:
        print(f"[ERROR] Could not find {filepath}.")
    return country_phrase_map
#---------------------------------------------------------------------------------------------------------------------------

# Load country-phrase mapping
country_phrase_map = load_country_phrases()
countries = list(country_phrase_map.keys())


# Initialize pytrends with Tor
proxy_list = ['socks5h://127.0.0.1:9050']
pytrends = TrendReq(proxies=proxy_list, timeout=(20, 40))  # (connect, read)

#---------------------------------------------------------------------------------------------------------------------------
def get_current_tor_ip(timeout=10):
    proxies = {'http': 'socks5h://127.0.0.1:9050', 'https': 'socks5h://127.0.0.1:9050'}
    
    try:
        return requests.get('http://httpbin.org/ip', proxies=proxies, timeout=timeout).json()['origin']
    except Exception as e:
        print(f"[WARN] Failed to fetch current IP: {e}")
        return None
#---------------------------------------------------------------------------------------------------------------------------
def rotate_tor_ip(max_retries=5, wait_time=10):
    old_ip = get_current_tor_ip()
    if old_ip is None:
        print("[WARN] Cannot fetch old IP, skipping validation.")
    
    for attempt in range(max_retries):
        with Controller.from_port(port=9051) as controller:
            controller.authenticate(password="no_hurry_in_2025")
            controller.signal(Signal.NEWNYM)
        print(f"[INFO] Sent NEWNYM signal. Waiting {wait_time}s...")
        time.sleep(wait_time)
        
        new_ip = get_current_tor_ip()
        if old_ip and new_ip and new_ip != old_ip:
            print(f"[INFO] IP rotated successfully: {old_ip} → {new_ip}")
            return
        elif new_ip == old_ip:
            print(f"[WARN] IP did not change. Retrying... ({attempt + 1}/{max_retries})")
            time.sleep(5)
        else:
            print(f"[WARN] New IP not detected. Retrying... ({attempt + 1}/{max_retries})")

    print("[ERROR] Failed to rotate Tor IP after max retries.")
    raise Exception("Tor IP rotation failed.")
#---------------------------------------------------------------------------------------------------------------------------
def get_top_trending_queries(limit=100, max_checks=100):
    scores = []
    queries = [f"{country} {phrase}" for country, phrase_list in country_phrase_map.items() for phrase in phrase_list]
    
    # Randomize queries
    random.shuffle(queries)
    
    # Define the proxies here (for use with both pytrends and requests)
    proxies = {'http': 'socks5h://127.0.0.1:9050', 'https': 'socks5h://127.0.0.1:9050'}

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
        time.sleep(random.uniform(5, 10))
        
        # Rotate Tor IP every 5 queries
        if (idx + 1) % 5 == 0:
            rotate_tor_ip()
            ip = requests.get('http://httpbin.org/ip', proxies=proxies).json()
            print("[DEBUG] Current IP via Tor:", ip)
    
    sorted_queries = sorted(scores, key=lambda x: x[1], reverse=True)[:limit]
    return [q for q, _ in sorted_queries]

#---------------------------------------------------------------------------------------------------------------------------
def get_news(query):
    # Limit to past n days
    from_date = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
    to_date = datetime.utcnow().strftime("%Y-%m-%d")
    
    try:
        response = requests.get(BASE_URL, params={
            "q": query,
            "apiKey": API_KEY,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 2,
            "from": from_date,
            "to": to_date
        })
        response.raise_for_status()
        return response.json().get("articles", [])
    except requests.RequestException as e:
        print(f"Error: Failed to fetch news for '{query}': {e}")
        return []
#---------------------------------------------------------------------------------------------------------------------------
def summarize_article(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        article.nlp()
        return article.summary
    except Exception as e:
        print(f"[WARN] Failed to summarize article: {url} | Reason: {e}")
        return None
#---------------------------------------------------------------------------------------------------------------------------
def send_email(content):
    msg = MIMEText(content, "html", "utf-8")
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
#---------------------------------------------------------------------------------------------------------------------------
def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    news_summary = f"""
    <html>
      <body>
        <h2>🗓 News Summary for {now}</h2>
        <p>
          <h3>This is an automated mail generated to inform the user regarding key market insights.</h3>
        </p>
    """
    all_articles = []
    country_articles = {country: [] for country in countries}

    # Get the top 25 trending queries
    top_queries = get_top_trending_queries(limit=100)

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
    
            summary = summarize_article(url)
            entry = (publishedAt, title, url, source, matched_country, topic, summary or "")
    
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
                publishedAt, title, url, _, _, topic, summary = entry
                news_summary += f"""
                    <p>
                      <strong>{idx}. <b>{title}</b></strong><br>
                      [{topic}] {publishedAt}<br>
                      🔗 <a href="{url}">{url}</a><br>
                """
                if summary:
                    news_summary += f"      📝 {summary}<br>"
                news_summary += "</p>"
        else:
            news_summary += "<p>No news found.</p>"

    # Save as CSV
    filename = f"news_{now}.csv"
    with open(filename, mode="w", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["PublishedAt", "Title", "Source", "URL", "Country", "Topic", "Summary"])
        for entry in all_articles:
            writer.writerow(entry)

    # Send the email
    send_email(news_summary)

if __name__ == "__main__":
    main()
