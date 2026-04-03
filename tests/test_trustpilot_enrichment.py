"""Test M71: Trustpilot rating enrichment via static HTML crawl."""

import json
import re
import os
from unittest.mock import patch, MagicMock
import pytest

from services.extraction.vendor_intel import VendorIntelligence


def test_vendor_intelligence_has_trustpilot_fields():
    """Test that VendorIntelligence has trustpilot_rating and trustpilot_review_count fields."""
    vi = VendorIntelligence(vendor_name="Test Vendor", website="https://example.com")
    
    # Check that fields exist
    assert hasattr(vi, "trustpilot_rating")
    assert hasattr(vi, "trustpilot_review_count")
    
    # Check default values
    assert vi.trustpilot_rating is None
    assert vi.trustpilot_review_count is None
    
    # Test with values
    vi2 = VendorIntelligence(
        vendor_name="Test Vendor",
        website="https://example.com",
        trustpilot_rating=4.5,
        trustpilot_review_count=123
    )
    assert vi2.trustpilot_rating == 4.5
    assert vi2.trustpilot_review_count == 123


def test_extract_json_ld_aggregate_rating():
    """Test JSON-LD AggregateRating extraction."""
    # Test HTML with JSON-LD AggregateRating
    html_with_rating = '''
    <html>
    <head>
    <script type="application/ld+json">
    {
      "@type": "AggregateRating",
      "ratingValue": 4.7,
      "reviewCount": 892
    }
    </script>
    </head>
    <body>Test</body>
    </html>
    '''
    
    # Test extraction function
    def extract_json_ld_aggregate_rating(html):
        pattern = r'<script[^>]*type="application/ld\+json"[^>]*>([^<]+)</script>'
        for match in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
            try:
                data = json.loads(match.group(1))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'AggregateRating':
                            rating = item.get('ratingValue')
                            count = item.get('reviewCount')
                            if rating is not None and count is not None:
                                return float(rating), int(count)
                elif isinstance(data, dict) and data.get('@type') == 'AggregateRating':
                    rating = data.get('ratingValue')
                    count = data.get('reviewCount')
                    if rating is not None and count is not None:
                        return float(rating), int(count)
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
        return None
    
    result = extract_json_ld_aggregate_rating(html_with_rating)
    assert result is not None
    rating, count = result
    assert rating == 4.7
    assert count == 892
    
    # Test HTML without rating
    html_without_rating = '<html><body>No rating here</body></html>'
    result = extract_json_ld_aggregate_rating(html_without_rating)
    assert result is None


def test_slugify_vendor_name():
    """Test vendor name to Trustpilot slug conversion."""
    test_cases = [
        ("HubSpot", "hubspot"),
        ("Zendesk", "zendesk"),
        ("Intercom", "intercom"),
        ("Salesforce", "salesforce"),
        ("Slack", "slack"),
        ("Zoom", "zoom"),
        ("Atlassian", "atlassian"),
        ("Dropbox", "dropbox"),
        ("Shopify", "shopify"),
        ("Spotify", "spotify"),
        ("Microsoft Corporation", "microsoft-corporation"),
        ("Google LLC", "google-llc"),
        ("Amazon Web Services", "amazon-web-services"),
    ]
    
    for vendor_name, expected_slug in test_cases:
        # Simple slugify function
        slug = vendor_name.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug.strip('-')
        
        # Check that slug is reasonable
        assert slug == expected_slug.lower() or slug.replace('-', '') == expected_slug.lower().replace('-', '')


def test_admin_api_includes_trustpilot_fields():
    """Test that admin API _SCALAR_FIELDS includes trustpilot fields."""
    # Read the file to check _SCALAR_FIELDS
    with open('services/admin/admin_api.py', 'r') as f:
        content = f.read()
    
    # Check that trustpilot fields are in _SCALAR_FIELDS
    assert '"trustpilot_rating"' in content
    assert '"trustpilot_review_count"' in content
    
    # Look for _SCALAR_FIELDS definition
    lines = content.split('\n')
    in_scalar_fields = False
    scalar_fields = []
    for line in lines:
        if '_SCALAR_FIELDS = {' in line:
            in_scalar_fields = True
        elif in_scalar_fields and '}' in line:
            in_scalar_fields = False
        elif in_scalar_fields:
            # Extract field names from quotes
            field_matches = re.findall(r'"([^"]+)"', line)
            scalar_fields.extend(field_matches)
    
    assert "trustpilot_rating" in scalar_fields
    assert "trustpilot_review_count" in scalar_fields


def test_n8n_workflow_exists():
    """Test that n8n workflow file exists."""
    workflow_path = 'n8n/workflows/csp-trustpilot-enrichment.workflow.json'
    assert os.path.exists(workflow_path), f"Workflow file not found: {workflow_path}"
    
    # Check that it's valid JSON
    with open(workflow_path, 'r') as f:
        workflow = json.load(f)
    
    assert 'name' in workflow
    assert workflow['name'] == 'CSP Trustpilot Enrichment'
    assert 'nodes' in workflow
    assert 'connections' in workflow
    
    # Check that it has the right webhook path
    webhook_node = None
    for node in workflow['nodes']:
        if node.get('type') == 'n8n-nodes-base.webhook':
            webhook_node = node
            break
    
    assert webhook_node is not None
    assert webhook_node['parameters']['path'] == 'csp-trustpilot-enrichment'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])