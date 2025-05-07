import requests
import csv
import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime, timezone
from dotenv import load_dotenv
from pytrends.request import TrendReq
import time

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

countries = ["Thailand", "Indonesia", "Vietnam", "Oman", "Pakistan", "China", "Japan"]
phrases = [
    "limestone export regulation",
    "blast furnace slag trade",
    "gypsum export tariff",
    "clinker logistics bottleneck",
    "cement domestic consumption",
    "cement input shortage",
    "limestone mining permit",
    "cement energy subsidy",
    "clinker production cost policy",
    "fuel price hike cement",
    "port congestion clinker export",
    "rail transport clinker delay"
]

# Initialize pytrends
pytrends = TrendReq(hl='en-US', tz=360)

def get_top_trending_queries(limit=25, sleep_seconds=1, max_checks=50):
    scores = []
    checked = 0
    queries = []
    
    # Generate combinations with countries and phrases
    for country in countries:
        for phrase in phrases:
            query = f"{phrase} {country}"
            queries.append(query)

    for query in queries:
        try:
            pytrends.build_payload([query], timeframe='now 1-d')
            interest = pytrends.interest_over_time()
            checked += 1
            if not interest.empty:
                avg_score = interest[query].mean()
                scores.append((query, avg_score))
        except Exception as e:
            print(f"[WARN] Skipping query '{query}': {e}")
        time.sleep(sleep_seconds)
        if checked >= max_checks:
            break

    # Sorting all queries based on their trend scores and getting the top N
    sorted_queries = sorted(scores, key=lambda x: x[1], reverse=True)[:limit]
    
    # Adjusting the phrases by dropping less popular words dynamically
    adjusted_queries = []
    for query, _ in sorted_queries:
        words = query.split()
        filtered_words = [word for word in words if is_popular_word(word)]  # Only keep popular words
        adjusted_query = " ".join(filtered_words)
        adjusted_queries.append(adjusted_query)
    
    return adjusted_queries

def get_news(query):
    try:
        response = requests.get(BASE_URL, params={
            "q": query,
            "apiKey": API_KEY,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 4
        })
        response.raise_for_status()
        return response.json().get("articles", [])
    except requests.RequestException as e:
        print(f"Failed to fetch news for query '{query}': {e}")
        return []

# Helper function to determine if a word should be kept (e.g., based on its current trend score)
def is_popular_word(word):
    # Implement a scoring mechanism for each word (this can be a more sophisticated model, like checking its overall trend score)
    # For simplicity, we're going to keep words that appear more than a threshold number of times in top queries
    popular_threshold = 2  # Example threshold: if word appears more than 3 times in trending queries, it's considered popular
    word_count = sum(word in query for query, _ in get_top_trending_queries())  # Count how often word appears in top queries
    
    return word_count >= popular_threshold

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
        
# Main execution function
def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    news_summary = f"News Summary for {now}\n"
    all_articles = []

    # Get the top 25 trending queries with adjusted phrases
    top_queries = get_top_trending_queries(limit=25)
    country_articles = {country: [] for country in countries}

    # Fetch news for the top trending queries
    for query in top_queries:
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

    # Organize news summaries by country
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
