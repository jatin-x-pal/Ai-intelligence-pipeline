"""Comprehensive tests for deterministic HTML cleaning and metadata extraction."""

from __future__ import annotations

from datetime import UTC, datetime

from src.extraction.date_parser import is_fresh, parse_publication_date
from src.extraction.html_cleaner import CleanedDocument, clean_html, estimate_tokens
from src.extraction.metadata import ExtractedMetadata, extract_metadata


class TestEstimateTokens:
    """Tests for deterministic token estimation."""

    def test_empty_text(self) -> None:
        assert estimate_tokens("") == 0
        assert estimate_tokens("   ") == 0

    def test_short_text(self) -> None:
        est = estimate_tokens("Hello world")
        assert est >= 2

    def test_long_text_scaling(self) -> None:
        text = "word " * 1000
        est = estimate_tokens(text)
        assert est >= 1000


class TestCleanHtml:
    """Tests for HTML sanitization and clean text extraction."""

    def test_empty_or_whitespace_html(self) -> None:
        doc = clean_html("", source_url="https://example.com/test")
        assert isinstance(doc, CleanedDocument)
        assert doc.clean_text == ""
        assert doc.source_url == "https://example.com/test"
        assert doc.character_count == 0
        assert doc.word_count == 0
        assert doc.token_estimate == 0

        doc2 = clean_html("   \n\t  ")
        assert doc2.clean_text == ""

    def test_malformed_html_handled_safely(self) -> None:
        malformed = "<html><body><div><p>Paragraph without closing div <p>Another line"
        doc = clean_html(malformed)
        assert "Paragraph without closing div" in doc.clean_text
        assert "Another line" in doc.clean_text

    def test_strips_scripts_and_styles(self) -> None:
        html = """
        <html>
            <head>
                <style>body { color: red; }</style>
                <script>console.log("malicious or tracker");</script>
            </head>
            <body>
                <script>alert("inline script");</script>
                <p>Legitimate content article.</p>
            </body>
        </html>
        """
        doc = clean_html(html)
        assert "Legitimate content article." in doc.clean_text
        assert "color: red" not in doc.clean_text
        assert "console.log" not in doc.clean_text
        assert "alert" not in doc.clean_text

    def test_strips_boilerplate_navigation_and_footer(self) -> None:
        html = """
        <html>
            <body>
                <header><h1>Site Logo and Nav</h1></header>
                <nav><a href="/home">Home</a><a href="/about">About</a></nav>
                <aside><p>Sidebar promotions and banner ads</p></aside>
                <main>
                    <h2>Article Title</h2>
                    <p>This is the essential substantive content about AI engineering.</p>
                </main>
                <footer><p>Copyright 2026 Corporation Inc. All rights reserved.</p></footer>
            </body>
        </html>
        """
        doc = clean_html(html)
        assert "Article Title" in doc.clean_text
        assert "essential substantive content about AI engineering" in doc.clean_text
        assert "Site Logo and Nav" not in doc.clean_text
        assert "Sidebar promotions" not in doc.clean_text
        assert "Copyright 2026" not in doc.clean_text

    def test_strips_accessibility_roles_and_aria_hidden(self) -> None:
        html = """
        <html>
            <body>
                <div role="banner">Skip to main content</div>
                <div role="navigation">Menu Links</div>
                <span aria-hidden="true">Icon decorative</span>
                <p>Clean body paragraph text.</p>
                <div role="contentinfo">Footer Links</div>
            </body>
        </html>
        """
        doc = clean_html(html)
        assert "Clean body paragraph text." in doc.clean_text
        assert "Skip to main content" not in doc.clean_text
        assert "Menu Links" not in doc.clean_text
        assert "Icon decorative" not in doc.clean_text
        assert "Footer Links" not in doc.clean_text

    def test_removes_html_comments(self) -> None:
        html = "<html><body><!-- secret comment --><p>Visible text</p></body></html>"
        doc = clean_html(html)
        assert "Visible text" in doc.clean_text
        assert "secret comment" not in doc.clean_text

    def test_whitespace_normalization_and_paragraphs(self) -> None:
        html = """
        <html>
            <body>
                <p>  Line   one    with   excessive    spaces.  </p>
                <p>Line two.</p>
            </body>
        </html>
        """
        doc = clean_html(html)
        assert doc.clean_text == "Line one with excessive spaces.\n\nLine two."

    def test_metrics_calculation(self) -> None:
        html = "<p>Ten words in this sentence to test accurate word and token calculation.</p>"
        doc = clean_html(html, source_url="https://example.com/item")
        assert doc.word_count == 12
        assert doc.character_count == len(doc.clean_text)
        assert doc.token_estimate > 0
        assert doc.source_url == "https://example.com/item"


class TestExtractMetadata:
    """Tests for deterministic metadata extraction."""

    def test_empty_html_metadata(self) -> None:
        meta = extract_metadata("", source_url="https://example.com/doc")
        assert isinstance(meta, ExtractedMetadata)
        assert meta.source_url == "https://example.com/doc"
        assert meta.title is None
        assert meta.canonical_url is None
        assert meta.description is None
        assert meta.author is None
        assert meta.site_name is None
        assert meta.opengraph == {}
        assert meta.twitter == {}
        assert meta.meta_tags == {}
        assert meta.json_ld == []

    def test_title_hierarchy(self) -> None:
        # Standard title tag takes priority
        html1 = "<html><head><title>Page Title Tag</title><meta property='og:title' content='OG Title' /></head></html>"
        assert extract_metadata(html1).title == "Page Title Tag"

        # Fallback to og:title
        html2 = "<html><head><meta property='og:title' content='OG Title' /></head></html>"
        assert extract_metadata(html2).title == "OG Title"

        # Fallback to twitter:title
        html3 = "<html><head><meta name='twitter:title' content='Twitter Title' /></head></html>"
        assert extract_metadata(html3).title == "Twitter Title"

        # Fallback to h1
        html4 = "<html><body><h1>H1 Header Title</h1><p>Body</p></body></html>"
        assert extract_metadata(html4).title == "H1 Header Title"

    def test_canonical_url_extraction(self) -> None:
        html1 = "<html><head><link rel='canonical' href='https://example.com/canonical' /></head></html>"
        assert extract_metadata(html1).canonical_url == "https://example.com/canonical"

        html2 = "<html><head><meta property='og:url' content='https://example.com/og-url' /></head></html>"
        assert extract_metadata(html2).canonical_url == "https://example.com/og-url"

    def test_meta_descriptions_and_authors(self) -> None:
        html = """
        <html>
            <head>
                <meta name="description" content="Meta tag description text." />
                <meta name="author" content="Alice Smith" />
                <meta property="og:site_name" content="TechNews AI" />
                <meta property="og:type" content="article" />
                <meta name="twitter:card" content="summary_large_image" />
            </head>
        </html>
        """
        meta = extract_metadata(html)
        assert meta.description == "Meta tag description text."
        assert meta.author == "Alice Smith"
        assert meta.site_name == "TechNews AI"
        assert meta.opengraph.get("og:type") == "article"
        assert meta.twitter.get("twitter:card") == "summary_large_image"

    def test_json_ld_extraction_single_and_array(self) -> None:
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "JobPosting",
                    "title": "Staff AI Engineer",
                    "hiringOrganization": {
                        "@type": "Organization",
                        "name": "Anthropic"
                    }
                }
                </script>
                <script type="application/ld+json">
                [
                    {
                        "@context": "https://schema.org",
                        "@type": "NewsArticle",
                        "headline": "Breakthrough in Reasoning Models"
                    }
                ]
                </script>
            </head>
        </html>
        """
        meta = extract_metadata(html)
        assert len(meta.json_ld) == 2
        assert meta.json_ld[0]["@type"] == "JobPosting"
        assert meta.json_ld[0]["title"] == "Staff AI Engineer"
        assert meta.json_ld[1]["@type"] == "NewsArticle"
        assert meta.json_ld[1]["headline"] == "Breakthrough in Reasoning Models"

    def test_json_ld_graph_unfolding(self) -> None:
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@graph": [
                        {"@type": "Organization", "name": "DeepMind"},
                        {"@type": "SoftwareApplication", "name": "AlphaFold"}
                    ]
                }
                </script>
            </head>
        </html>
        """
        meta = extract_metadata(html)
        assert len(meta.json_ld) == 2
        names = [item.get("name") for item in meta.json_ld]
        assert "DeepMind" in names
        assert "AlphaFold" in names

    def test_json_ld_corrupted_json_handled_safely(self) -> None:
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                { corrupted invalid json syntax ...
                </script>
                <script type="application/ld+json">
                {"@type": "ValidItem", "name": "Recovered"}
                </script>
            </head>
        </html>
        """
        meta = extract_metadata(html)
        assert len(meta.json_ld) == 1
        assert meta.json_ld[0]["name"] == "Recovered"

    def test_never_invents_missing_data(self) -> None:
        html = "<html><body><p>Unadorned text without head or metadata</p></body></html>"
        meta = extract_metadata(html)
        assert meta.title is None
        assert meta.canonical_url is None
        assert meta.description is None
        assert meta.author is None
        assert meta.site_name is None
        assert meta.opengraph == {}
        assert meta.twitter == {}
        assert meta.json_ld == []


class TestDateParserIntegration:
    """Tests verifying date_parser extraction pathways."""

    def test_json_ld_date(self) -> None:
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@context": "https://schema.org", "datePublished": "2026-09-09T14:30:00+00:00"}
        </script>
        </head></html>
        """
        dt = parse_publication_date(html)
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 9
        assert dt.day == 9

    def test_meta_article_date(self) -> None:
        html = """
        <html><head>
        <meta property="article:published_time" content="2026-09-10T08:00:00Z" />
        </head></html>
        """
        dt = parse_publication_date(html)
        assert dt is not None
        assert dt.tzinfo is not None

    def test_time_tag_date(self) -> None:
        html = "<html><body><time>2026-09-10T12:00:00+00:00</time></body></html>"
        dt = parse_publication_date(html)
        assert dt is not None
        assert dt.hour == 12

    def test_relative_date(self) -> None:
        ref = datetime(2026, 9, 10, 15, 0, 0, tzinfo=UTC)
        html = "<html><body>Published 3 hours ago by Tech Reporter</body></html>"
        dt = parse_publication_date(html, reference=ref)
        assert dt is not None
        assert dt.hour == 12

    def test_freshness_check(self) -> None:
        now = datetime(2026, 9, 10, 20, 0, 0, tzinfo=UTC)
        recent = datetime(2026, 9, 10, 5, 0, 0, tzinfo=UTC)
        stale = datetime(2026, 9, 8, 20, 0, 0, tzinfo=UTC)

        assert is_fresh(recent, reference=now) is True
        assert is_fresh(stale, reference=now) is False
        assert is_fresh(None, reference=now) is False
