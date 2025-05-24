import requests
import csv
import smtplib
import os
import pandas as pd
import random
import time
import json
import pickle
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pytrends.request import TrendReq
from stem import Signal
from stem.control import Controller
from newspaper import Article
from collections import defaultdict
from collections import deque
import nltk

CACHE_DIR = "news_cache"
os.makedirs(CACHE_DIR, exist_ok=True)  # Ensures the directory exists
CACHE_FILENAME = "current.pkl"
MAX_CACHE_SIZE = 1000

def get_quarter(date_obj):
    return (date_obj.month - 1) // 3 + 1

# Set the path if the environment variable is defined
if 'NLTK_DATA' in os.environ:
    nltk.data.path.append(os.environ['NLTK_DATA'])

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
if not country_phrase_map:
    raise ValueError("No phrases loaded. Ensure 'phrases.txt' contains valid entries.")
countries = list(country_phrase_map.keys())


# Initialize pytrends with Tor
proxy_list = ['socks5h://127.0.0.1:9050']
pytrends = TrendReq(proxies=proxy_list, timeout=(20, 40))  # (connect, read)
#---------------------------------------------------------------------------------------------------------------------------
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
#---------------------------------------------------------------------------------------------------------------------------
# Externalized country code loading
def load_country_codes(filepath="country_codes.json"):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] {filepath} not found.")
        return {}
#---------------------------------------------------------------------------------------------------------------------------
def get_top_trending_queries(limit=100, max_checks=100):
    max_retries = 3
    scores = []
    queries = [f"{country} {phrase}" for country, phrase_list in country_phrase_map.items() for phrase in phrase_list]

    # Randomize queries
    random.shuffle(queries)

    # Load country codes from external file
    country_code_map = load_country_codes()
    
    # Define the proxies here (for use with both pytrends and requests)
    proxies = {'http': 'socks5h://127.0.0.1:9050', 'https': 'socks5h://127.0.0.1:9050'}

    for idx, query in enumerate(queries[:max_checks]):
        print(f"[INFO] Checking {idx+1}/{max_checks} → {query}")

        # Extract country from query prefix (assumes first word is country name)
        matched_country = next((c for c in country_code_map if query.lower().startswith(c.lower())), None)
        geo_code = country_code_map.get(matched_country, "")

        
        retries = 0
        while retries < max_retries:
            try:
                pytrends.build_payload([query], timeframe='now 1-d', geo=geo_code)
                interest = pytrends.interest_over_time()
                
                # Check if interest data exists and has positive values
                if not interest.empty and interest[query].sum() > 0:
                    avg_score = interest[query].mean()
                    scores.append((query, avg_score))
                    print(f"[INFO] {query} ⟶ {avg_score:.2f} (geo={geo_code})")
                else:
                    print(f"[INFO] {query} has no trend data in {geo_code or 'global'}")
                break # exit retry loop on success
            
            except Exception as e:
                # Check if 429 error in the exception message or type (adjust as needed)
                if '429' in str(e) or 'Too Many Requests' in str(e):
                    retries += 1
                    print(f"[WARN] Rate limited on {query}, rotating IP and retrying ({retries}/{max_retries})...")
                    rotate_tor_ip()
                    ip = requests.get('http://httpbin.org/ip', proxies=proxies).json()
                    print("[DEBUG] Current IP via Tor:", ip)
                    time.sleep(random.uniform(10, 25))  # wait a bit before retrying
                else:
                    print(f"[WARN] {query} failed: {e}")
                    break  # some other error, exit retry loop
        
        # Random delay
        time.sleep(random.uniform(10, 25))
        
        # Rotate Tor IP every 10 queries
        if (idx + 1) % 10 == 0:
            rotate_tor_ip()
            ip = requests.get('http://httpbin.org/ip', proxies=proxies).json()
            print("[DEBUG] Current IP via Tor:", ip)
    
    sorted_queries = sorted(scores, key=lambda x: x[1], reverse=True)[:limit]
    return [q for q, _ in sorted_queries]

#---------------------------------------------------------------------------------------------------------------------------
def get_news(query):
    # Limit to past n days
    from_date = (datetime.utcnow() - timedelta(days=15)).strftime("%Y-%m-%d")
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
        try:
            article.nlp()
            return article.summary
        except:
            return article.text[:400]
    except Exception as e:
        print(f"[WARN] Failed to summarize article: {url} | Reason: {e}")
        return None
#---------------------------------------------------------------------------------------------------------------------------
def send_email(content):
    
    recipients = [email.strip() for email in EMAIL_TO.split(",") if email.strip()]
    msg = MIMEText(content, "html", "utf-8")
    msg["Subject"] = "📰 Daily Cement News Summary"
    msg["From"] = EMAIL_USER
    msg["To"] = ", ".join(recipients)

    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        print("[INFO] Email sent successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
#---------------------------------------------------------------------------------------------------------------------------
def update_and_filter_news_cache(new_articles):

    os.makedirs(CACHE_DIR, exist_ok=True)
    print(f"[Debug] Saving cache to: {cache_path}")
    cache_path = os.path.join(CACHE_DIR, CACHE_FILENAME)

    # Load existing cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                cache = pickle.load(f)
        except (pickle.UnpicklingError, EOFError, FileNotFoundError):
            corrupt_path = cache_path + ".corrupt"
            shutil.move(cache_path, corrupt_path)
            print(f"[Warning] Corrupted cache moved to: {corrupt_path}")
            cache = []
    else:
        cache = []

    now = datetime.now()
    current_year = now.year
    current_quarter = get_quarter(now)

    # Separate entries by quarter-year
    quarters = {}  # key: (year, quarter), value: list of entries
    for entry in cache:
        
        date_str = entry[0]  # e.g. "2025-05-22"
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue  # Skip malformed entries
        q = get_quarter(date_obj)
        key = (date_obj.year, q)
        quarters.setdefault(key, []).append(entry)
 
    # Determine which quarters to archive
    def quarter_less(a, b):
        if a[0] < b[0]:
            return True
        elif a[0] == b[0]:
            return a[1] < b[1]
        return False

    if current_quarter == 1:
        threshold = (current_year - 1, 4)
    else:
        threshold = (current_year, current_quarter - 1)

    # Archive quarters older than threshold
    to_keep = []
    for q_key, entries in quarters.items():
        if quarter_less(q_key, threshold):
            # Archive these entries
            archive_year, archive_quarter = q_key
            archive_file = f"Q{archive_quarter}-{archive_year}.pkl"
            archive_path = os.path.join(CACHE_DIR, archive_file)
            try:
                if os.path.exists(archive_path):
                    with open(archive_path, "rb") as af:
                        archive_data = pickle.load(af)
                else:
                    archive_data = []
            except (pickle.UnpicklingError, EOFError):
                archive_data = []
            archive_data.extend(entries)
            with open(archive_path, "wb") as af:
                pickle.dump(archive_data, af)
        else:
            # Keep these entries in cache
            to_keep.extend(entries)

    cache = to_keep

    recent_urls = set(entry[4] for entry in cache[-MAX_CACHE_SIZE:])
    filtered_articles = [entry for entry in new_articles if entry[4] not in recent_urls]

    # Update cache with new entries
    cache.extend(filtered_articles)
    with open(cache_path, "wb") as f:
        pickle.dump(cache, f)

    return filtered_articles
#---------------------------------------------------------------------------------------------------------------------------
def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    news_summary = f"""
    <html>
      <body>
        <h1>🗓 News Summary for {now}</h1>
        <p style="font-size: 14px; color: #555;">
          This automated mail is generated to inform the user regarding key market insights. _Nabil.Hasan<br>
        </p>
      </body>
     </html>
    """
    raw_articles = []

    # Step 1: Get top queries
    top_queries = get_top_trending_queries(limit=100)

    # Step 2: Fetch news articles for each query
    for query in top_queries:
        articles = get_news(query)
        matched_country = next((c for c in countries if c.lower() in query.lower()), "Unknown")
        topic = query.replace(matched_country, '').strip()

        for article in articles:
            publishedAt = article.get("publishedAt", "")[:10]
            title = article.get("title", "")
            url = article.get("url", "")
            raw_articles.append((publishedAt, matched_country, topic, title, url))

        time.sleep(random.uniform(1, 3))  # polite delay between requests

    # Step 3: Filter and update cache
    filtered_articles = update_and_filter_news_cache(raw_articles)

    # Step 4: Summarize and organize news by country
    country_articles = {country: [] for country in countries}
    for article in filtered_articles:
        date, country, topic, title, url = article
        summary = summarize_article(url)
        entry = (date, title, url, "", country, topic, summary)
        country_articles[country].append(entry)

    # Step 5: Build email HTML
    for country in countries:
        news_summary += f"""\n <h2>{country} </h2>\n"""
        entries = country_articles[country]
        if entries:
            for idx, entry in enumerate(entries, 1):
                publishedAt, title, url, _, _, topic, summary = entry
                news_summary += f"""
                    <p>
                      <h3>{idx}. {title} </h3>
                      [{topic}] {publishedAt}<br>
                      🔗 <a href="{url}" style="font-size: 0.9em; color: #555;">Read full article</a><br>
                """
                if summary:
                    news_summary += f"      📝 {summary}<br>"
                news_summary += "</p>"
        else:
            news_summary += "<p>Fresh news unavailable</p>"

    # Step 6: Send the email
    send_email(news_summary)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"""
        <html>
          <body>
            <h2>🚨 Script Failure</h2>
            <p><strong>Error:</strong> {str(e)}</p>
            <p>Please check logs or code for debugging.</p>
          </body>
        </html>
        """
        send_email(error_msg)
        raise
