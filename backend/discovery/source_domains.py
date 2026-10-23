"""
Known domain → SourceType mappings.

This is a maintainable lookup table used as step 2 of source
classification (after official-source check, before path heuristics).

Hostnames are lowercase, without ``www.`` prefix.
Lookup is O(1) dict access.  Add new domains here as needed.
"""

from .models import SourceType

# ---------------------------------------------------------------
# Master mapping: hostname → SourceType
# ---------------------------------------------------------------

DOMAIN_SOURCE_MAP: dict[str, SourceType] = {}


def _reg(source_type: SourceType, domains: list[str]) -> None:
    """Register a batch of domains under one SourceType."""
    for d in domains:
        DOMAIN_SOURCE_MAP[d.lower()] = source_type


# --- News -------------------------------------------------------
_reg(SourceType.NEWS, [
    # International
    "bbc.com", "bbc.co.uk", "news.bbc.co.uk",
    "cnn.com", "edition.cnn.com",
    "reuters.com", "apnews.com", "aljazeera.com",
    # US
    "nytimes.com", "washingtonpost.com", "usatoday.com",
    "nbcnews.com", "abcnews.go.com", "foxnews.com", "npr.org",
    # Business / Finance
    "bloomberg.com", "cnbc.com", "ft.com", "wsj.com",
    "economist.com", "forbes.com", "businessinsider.com",
    "finance.yahoo.com", "news.yahoo.com",
    "moneycontrol.com", "investopedia.com",
    "investing.com", "in.investing.com",
    "marketwatch.com", "seekingalpha.com",
    # UK
    "theguardian.com", "telegraph.co.uk", "independent.co.uk",
    "sky.com", "news.sky.com", "dailymail.co.uk",
    # India
    "indianexpress.com", "ndtv.com",
    "timesofindia.indiatimes.com", "economictimes.indiatimes.com",
    "hindustantimes.com", "thehindu.com", "livemint.com",
    "financialexpress.com", "scroll.in", "thewire.in",
    "firstpost.com", "news18.com",
    # Tech
    "techcrunch.com", "wired.com", "arstechnica.com",
    "theverge.com", "engadget.com", "zdnet.com", "cnet.com",
    "mashable.com", "thenextweb.com", "venturebeat.com",
    # Fashion / Lifestyle / Sports
    "wwd.com", "vogue.com", "espn.com",
    "bleacherreport.com", "sportingnews.com",
    # General
    "time.com", "huffpost.com", "vice.com", "vox.com",
    "thehill.com", "politico.com",
])

# --- Reddit -----------------------------------------------------
_reg(SourceType.REDDIT, [
    "reddit.com", "old.reddit.com", "np.reddit.com",
    "i.reddit.com", "m.reddit.com", "amp.reddit.com",
])

# --- YouTube ----------------------------------------------------
_reg(SourceType.YOUTUBE, [
    "youtube.com", "m.youtube.com", "youtu.be",
    "music.youtube.com",
])

# --- Blog platforms ---------------------------------------------
_reg(SourceType.BLOG, [
    "medium.com", "substack.com", "wordpress.com",
    "blogger.com", "blogspot.com", "dev.to",
    "hashnode.com", "ghost.org", "tumblr.com",
])

# --- Forums / Q&A ----------------------------------------------
_reg(SourceType.FORUM, [
    "quora.com", "stackoverflow.com", "stackexchange.com",
    "superuser.com", "serverfault.com", "askubuntu.com",
    "xda-developers.com", "xda-forums.com",
    "answers.microsoft.com", "discussions.apple.com",
])

# --- Review sites -----------------------------------------------
_reg(SourceType.REVIEW, [
    "trustpilot.com", "bbb.org", "yelp.com", "tripadvisor.com",
    "g2.com", "capterra.com", "glassdoor.com", "glassdoor.co.in",
    "ambitionbox.com", "consumeraffairs.com", "sitejabber.com",
    "pissedconsumer.com", "runrepeat.com", "voxya.com",
    "mouthshut.com", "complaintsboard.com", "trustradius.com",
    "weartesters.com", "rtings.com",
])

# --- Social media -----------------------------------------------
_reg(SourceType.SOCIAL_MEDIA, [
    "twitter.com", "x.com",
    "facebook.com", "m.facebook.com",
    "instagram.com", "linkedin.com",
    "tiktok.com", "pinterest.com",
    "mastodon.social", "threads.net",
])

# --- E-commerce -------------------------------------------------
_reg(SourceType.ECOMMERCE, [
    # Amazon (major TLDs)
    "amazon.com", "amazon.co.uk", "amazon.in", "amazon.de",
    "amazon.fr", "amazon.ca", "amazon.com.au", "amazon.co.jp",
    "sellercentral.amazon.com", "sellercentral.amazon.in",
    # Others
    "ebay.com", "ebay.co.uk", "ebay.de",
    "flipkart.com", "myntra.com", "ajio.com",
    "etsy.com", "walmart.com", "target.com", "bestbuy.com",
    "alibaba.com", "aliexpress.com",
    "nykaa.com", "meesho.com", "snapdeal.com",
])
