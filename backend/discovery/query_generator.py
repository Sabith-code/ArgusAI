"""
Query generator for brand discovery.

Produces a balanced set of search queries — positive, neutral, negative, and
crisis-adjacent — to avoid sampling bias toward any single sentiment.

Template set approved by project owner (8 templates, no "scandal").
"""

from typing import List


# Approved query templates.
# Each template embeds the brand name in quotes for exact-match intent.
# Note: OR syntax behaviour varies across SearXNG engines.  The exact query
# string is preserved and logged with every result for provenance.
QUERY_TEMPLATES: List[dict] = [
    {
        "category": "bare_brand",
        "template": '"{brand}"',
    },
    {
        "category": "news",
        "template": '"{brand}" news',
    },
    {
        "category": "reviews",
        "template": '"{brand}" review OR reviews',
    },
    {
        "category": "complaints",
        "template": '"{brand}" complaint OR problem OR issue',
    },
    {
        "category": "praise",
        "template": '"{brand}" praise OR great OR excellent',
    },
    {
        "category": "announcements",
        "template": '"{brand}" announcement OR launch OR release',
    },
    {
        "category": "discussion",
        "template": '"{brand}" discussion OR opinions OR thoughts',
    },
    {
        "category": "controversy",
        "template": '"{brand}" controversy OR backlash',
    },
]


def generate_queries(brand: str) -> List[dict]:
    """
    Generate the full set of search queries for a given brand name.

    Args:
        brand: The brand name to search for (e.g. "Nike").

    Returns:
        List of dicts, each with:
          - category (str): descriptive label for the query type
          - query (str): the exact search string to send to SearXNG
    """
    queries = []
    for tmpl in QUERY_TEMPLATES:
        query_str = tmpl["template"].replace("{brand}", brand)
        queries.append({
            "category": tmpl["category"],
            "query": query_str,
        })
    return queries
