import requests
import csv
import os
from datetime import datetime

API_KEY = os.getenv("NEWS_API_KEY")
BASE_URL = "https://newsapi.org/v2/everything"

countries = ["India", "Thailand", "Indonesia", "Vietnam", "Oman", "Pakistan", "China", "Japan", "Korea"]
topics = ["trade", "construction", "shipping", "clinker", "cement", "logistics", "import", "export", "infrastructure"]

def get_news(query):
    params = {
        "q": query,
        "apiKey": API_KEY,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 100
    }
    response = requests.get(BASE_URL, params=params)
    return response.json().get("articles", [])

def main():
    now = datetime.utcnow().strftime("%Y-%m-%d_%H-%M")
    filename = f"news_{now}.csv"
    
    with open(filename, mode="w", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["PublishedAt", "Title", "Source", "URL", "Country", "Topic"])
        
        for country in countries:
            for topic in topics:
                query = f"{topic} AND {country}"
                articles = get_news(query)
                for article in articles:
                    writer.writerow([
                        article.get("publishedAt", ""),
                        article.get("title", ""),
                        article.get("source", {}).get("name", ""),
                        article.get("url", ""),
                        country,
                        topic
                    ])

if __name__ == "__main__":
    main()
