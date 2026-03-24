"""Tests for deterministic HTML text extraction."""

from services.extraction.page_text_extractor import extract_visible_text


def test_extract_visible_text_removes_navigation_footer_and_tracking_noise():
    html = """
    <html>
      <head>
        <title>ExampleCorp</title>
        <script>window.analytics = true;</script>
      </head>
      <body>
        <nav>
          <a href="/pricing">Pricing</a>
          <a href="/product">Product</a>
        </nav>
        <section>
          <h1>Customer success platform</h1>
          <p>ExampleCorp helps SaaS companies improve adoption.</p>
        </section>
        <div class="tracking-banner">Track every click</div>
        <footer>
          <a href="/privacy">Privacy</a>
        </footer>
      </body>
    </html>
    """

    result = extract_visible_text(html)

    assert result == "Customer success platform ExampleCorp helps SaaS companies improve adoption."


def test_extract_visible_text_removes_menu_like_sections_by_class_name():
    html = """
    <html>
      <body>
        <div class="main-menu">
          <a href="/features">Features</a>
          <a href="/security">Security</a>
        </div>
        <main>
          <p>Built for product-led teams.</p>
          <p>Free trial available.</p>
        </main>
      </body>
    </html>
    """

    result = extract_visible_text(html)

    assert result == "Built for product-led teams. Free trial available."


def test_extract_visible_text_keeps_header_hero_copy_when_not_navigation():
    html = """
    <html>
      <body>
        <header class="hero-shell">
          <h1>AI customer success platform</h1>
          <p>Built for onboarding, renewals, and customer health.</p>
        </header>
        <nav>
          <a href="/pricing">Pricing</a>
        </nav>
      </body>
    </html>
    """

    result = extract_visible_text(html)

    assert result == "AI customer success platform Built for onboarding, renewals, and customer health."


def test_extract_visible_text_supports_deterministic_truncation():
    html = """
    <html>
      <body>
        <main>
          <p>Customer success platform for SaaS teams.</p>
          <p>Improves onboarding and renewal workflows.</p>
        </main>
      </body>
    </html>
    """

    result = extract_visible_text(html, max_chars=35)

    assert result == "Customer success platform for SaaS"
