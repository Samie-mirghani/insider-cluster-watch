# jobs/news_sentiment.py
"""
News Sentiment Analysis

Checks recent news headlines for each signal to avoid buying into disasters.

Uses free news sources:
- Google News RSS (free, no API key needed)
- Basic keyword sentiment analysis

Features:
- Red flag detection (lawsuits, fraud, bankruptcy)
- Positive confirmation (upgrades, good news)
- Simple sentiment scoring
"""

import requests
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime, timedelta
import time

# Negative keywords that trigger warnings
NEGATIVE_KEYWORDS = [
    'lawsuit', 'fraud', 'investigation', 'sec probe', 'scandal',
    'bankruptcy', 'chapter 11', 'delisting', 'warning letter',
    'recall', 'fda rejection', 'clinical trial fail', 'miss earnings',
    'layoff', 'restructuring', 'resignation', 'fired', 'stepped down',
    'accounting error', 'restatement', 'guidance cut', 'downgrade',
    'loss', 'plunge', 'crash', 'tumble', 'slump'
]

# Positive keywords
POSITIVE_KEYWORDS = [
    'beat earnings', 'upgraded', 'outperform', 'buy rating', 'raised guidance',
    'strong results', 'record', 'growth', 'expansion', 'acquisition',
    'partnership', 'deal', 'contract', 'approval', 'breakthrough',
    'innovation', 'award', 'winner', 'success', 'soar', 'surge', 'rally'
]

def fetch_google_news(ticker, company_name=None, days_back=3):
    """
    Fetch recent news from Google News RSS feed
    
    Args:
        ticker: Stock ticker symbol
        company_name: Optional company name for better search
        days_back: Number of days to look back
    
    Returns:
        List of news articles with title, link, published date
    """
    try:
        from urllib.parse import quote_plus
        
        # Build search query
        if company_name:
            search_query = f"{company_name} {ticker} stock"
        else:
            search_query = f"{ticker} stock"
        
        # Encode query and build Google News RSS feed URL
        encoded_query = quote_plus(search_query)
        url = f"https://news.google.com/rss/search?q={encoded_query}+when:{days_back}d&hl=en-US&gl=US&ceid=US:en"
        
        # Parse RSS feed
        feed = feedparser.parse(url)
        
        articles = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        for entry in feed.entries[:10]:  # Limit to 10 most recent
            try:
                pub_date = datetime(*entry.published_parsed[:6])
                
                if pub_date >= cutoff_date:
                    articles.append({
                        'title': entry.title,
                        'link': entry.link,
                        'published': pub_date,
                        'source': entry.get('source', {}).get('title', 'Unknown')
                    })
            except:
                continue
        
        return articles
    
    except Exception as e:
        print(f"   ⚠️  Error fetching news for {ticker}: {e}")
        return []

def analyze_sentiment(articles):
    """
    Analyze sentiment of news articles using keyword matching
    
    Returns:
        dict with sentiment, negative_flags, positive_flags, and score
    """
    if not articles:
        return {
            'sentiment': 'NEUTRAL',
            'score': 0,
            'negative_flags': [],
            'positive_flags': [],
            'article_count': 0
        }
    
    negative_count = 0
    positive_count = 0
    negative_flags = []
    positive_flags = []
    
    for article in articles:
        title_lower = article['title'].lower()
        
        # Check for negative keywords
        for keyword in NEGATIVE_KEYWORDS:
            if keyword in title_lower:
                negative_count += 1
                if keyword not in negative_flags:
                    negative_flags.append(keyword)
        
        # Check for positive keywords
        for keyword in POSITIVE_KEYWORDS:
            if keyword in title_lower:
                positive_count += 1
                if keyword not in positive_flags:
                    positive_flags.append(keyword)
    
    # Calculate sentiment score (-10 to +10)
    score = positive_count - negative_count
    
    # Determine overall sentiment
    if score <= -3:
        sentiment = 'VERY_NEGATIVE'
    elif score < 0:
        sentiment = 'NEGATIVE'
    elif score == 0:
        sentiment = 'NEUTRAL'
    elif score <= 2:
        sentiment = 'POSITIVE'
    else:
        sentiment = 'VERY_POSITIVE'
    
    return {
        'sentiment': sentiment,
        'score': score,
        'negative_flags': negative_flags,
        'positive_flags': positive_flags,
        'article_count': len(articles)
    }

def check_news_for_signal(ticker, company_name=None):
    """
    Check recent news for a signal ticker
    
    Returns:
        dict with news analysis and recommendation
    """
    print(f"   📰 Checking news for {ticker}...")
    
    articles = fetch_google_news(ticker, company_name, days_back=3)
    
    if not articles:
        return {
            'ticker': ticker,
            'has_news': False,
            'sentiment': 'UNKNOWN',
            'recommendation': 'PROCEED',
            'reason': 'No recent news found',
            'articles': []
        }
    
    analysis = analyze_sentiment(articles)

    # Format sentiment display text for emails
    formatted_sentiment = analysis['sentiment'].replace('_', ' ').title()
    
    # Determine recommendation
    if analysis['sentiment'] in ['VERY_NEGATIVE', 'NEGATIVE']:
        if len(analysis['negative_flags']) >= 2:
            recommendation = 'AVOID'
            reason = f"Multiple red flags: {', '.join(analysis['negative_flags'][:3])}"
        else:
            recommendation = 'CAUTION'
            reason = f"Negative news detected: {', '.join(analysis['negative_flags'])}"
    elif analysis['sentiment'] == 'VERY_POSITIVE':
        recommendation = 'STRONG_BUY'
        reason = f"Positive news: {', '.join(analysis['positive_flags'][:2])}"
    elif analysis['sentiment'] == 'POSITIVE':
        recommendation = 'PROCEED'
        reason = f"Some positive news: {', '.join(analysis['positive_flags'][:2])}"
    else:
        recommendation = 'PROCEED'
        reason = 'Neutral news sentiment'
    
    return {
        'ticker': ticker,
        'has_news': True,
        'sentiment': analysis['sentiment'],
        'sentiment_display': formatted_sentiment,
        'score': analysis['score'],
        'recommendation': recommendation,
        'reason': reason,
        'negative_flags': analysis['negative_flags'],
        'positive_flags': analysis['positive_flags'],
        'article_count': analysis['article_count'],
        'articles': articles[:5]  # Top 5 articles
    }

def check_news_for_signals(cluster_df):
    """
    Check news for all signals in a cluster DataFrame
    
    Adds news_sentiment, news_recommendation columns
    """
    if cluster_df.empty:
        return cluster_df
    
    print(f"\n📰 Checking news sentiment for {len(cluster_df)} signals...")
    
    news_results = []
    
    for _, signal in cluster_df.iterrows():
        ticker = signal['ticker']
        
        # Rate limiting - be respectful
        time.sleep(1)
        
        news = check_news_for_signal(ticker)
        news_results.append(news)
    
    # Add to DataFrame
    cluster_df['news_sentiment'] = [n['sentiment'] for n in news_results]
    cluster_df['news_recommendation'] = [n['recommendation'] for n in news_results]
    cluster_df['news_reason'] = [n['reason'] for n in news_results]
    cluster_df['news_articles'] = [n['articles'] for n in news_results]
    
    # Print summary
    avoid_count = sum(1 for n in news_results if n['recommendation'] == 'AVOID')
    caution_count = sum(1 for n in news_results if n['recommendation'] == 'CAUTION')
    
    if avoid_count > 0:
        print(f"   ⚠️  {avoid_count} signal(s) marked AVOID due to negative news")
    if caution_count > 0:
        print(f"   ⚠️  {caution_count} signal(s) marked CAUTION due to news")
    
    print(f"   ✅ News sentiment analysis complete")
    
    return cluster_df

def format_news_for_email(news_info):
    """
    Format news information for email display
    
    Returns HTML and plain text versions
    """
    if not news_info or not news_info.get('has_news'):
        return "", ""
    
    sentiment = news_info['sentiment']
    
    # Emoji based on sentiment
    emoji_map = {
        'VERY_NEGATIVE': '🔴',
        'NEGATIVE': '⚠️',
        'NEUTRAL': '➖',
        'POSITIVE': '✅',
        'VERY_POSITIVE': '🟢'
    }
    
    emoji = emoji_map.get(sentiment, '📰')
    
    # HTML version
    html = f'<div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0;">'
    html += f'<div style="font-size: 12px; font-weight: 600; color: #666; margin-bottom: 5px;">'
    html += f'{emoji} Recent News (72hrs): {sentiment}'
    html += f'</div>'
    
    if news_info.get('articles'):
        html += '<div style="font-size: 11px; color: #555;">'
        for article in news_info['articles'][:3]:
            html += f'• {article["title"][:80]}...<br/>'
        html += '</div>'
    
    html += f'<div style="font-size: 11px; color: #777; margin-top: 5px;">'
    html += f'{news_info.get("reason", "")}'
    html += '</div></div>'
    
    # Plain text version
    text = f"\n📰 Recent News: {sentiment}\n"
    if news_info.get('articles'):
        for article in news_info['articles'][:3]:
            text += f"  • {article['title'][:80]}...\n"
    text += f"  {news_info.get('reason', '')}\n"
    
    return html, text

if __name__ == "__main__":
    # Test news sentiment
    test_ticker = "NVDA"
    result = check_news_for_signal(test_ticker)
    
    print(f"\nNews Check for {test_ticker}:")
    print(f"Sentiment: {result['sentiment']}")
    print(f"Recommendation: {result['recommendation']}")
    print(f"Reason: {result['reason']}")
    print(f"\nTop headlines:")
    for article in result['articles'][:3]:
        print(f"  • {article['title']}")