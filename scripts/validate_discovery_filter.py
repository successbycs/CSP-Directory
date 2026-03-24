#!/usr/bin/env python3
"""
Validate the discovery quality filter for M38.

Tests that the filter correctly rejects:
- Blog posts (medium.com, substack.com)
- Review articles (g2.com, capterra.com, trustradius.com)
- Error pages / interstitials (403 forbidden, just a moment)
- Reddit threads (reddit.com)
- Aggregator sites (getapp.com, alternativeto.net)
- Job boards (glassdoor.com, builtin.com)
- Analyst firms (gartner.com, forrester.com)

And correctly keeps real vendor domains.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.discovery.apify_sources import _should_keep_google_search_result
from services.config.load_config import load_pipeline_config

config = load_pipeline_config().discovery

# --- Test cases ---
SHOULD_REJECT = [
    # Review/aggregator sites
    {"url": "https://www.g2.com/categories/customer-success", "title": "Best Customer Success Software 2024", "description": "Read reviews of customer success tools"},
    {"url": "https://www.capterra.com/customer-success-software/", "title": "Top Customer Success Platforms - Capterra", "description": "Compare customer success solutions"},
    {"url": "https://www.trustradius.com/customer-success", "title": "Customer Success Software Reviews", "description": "See what real users say"},
    {"url": "https://www.getapp.com/customer-management-software/", "title": "GetApp: Compare Customer Success Tools", "description": "Find the best software"},
    {"url": "https://alternativeto.net/software/gainsight/", "title": "Gainsight alternatives - AlternativeTo", "description": "Find alternatives to customer success platforms"},
    # Reddit
    {"url": "https://www.reddit.com/r/CustomerSuccess/", "title": "CustomerSuccess subreddit - reddit", "description": "Community discussion about customer success"},
    # Medium/blog
    {"url": "https://medium.com/best-cs-platforms-2024", "title": "10 Best Customer Success Platforms 2024", "description": "Review article about CS tools"},
    # Analyst/research
    {"url": "https://www.gartner.com/en/customer-experience/insights/customer-success", "title": "Gartner Research on Customer Success", "description": "Market analysis"},
    {"url": "https://www.forrester.com/research/customer-success/", "title": "The Forrester Wave: Customer Success", "description": "Analyst report"},
    # Job boards
    {"url": "https://www.glassdoor.com/Jobs/customer-success-manager-jobs.htm", "title": "Customer Success Manager Jobs - Glassdoor", "description": "Find CSM job listings"},
    # Interstitial/error
    {"url": "https://somevendor.com/login", "title": "Just a moment... | Cloudflare", "description": "403 forbidden access denied"},
    # Listicle without product signals
    {"url": "https://somesite.com/blog/top-10-cs-platforms", "title": "Top 10 Customer Success Platforms Reviewed", "description": "We reviewed and compared the best tools"},
]

SHOULD_KEEP = [
    # Real vendor homepages with CS signals
    {"url": "https://www.gainsight.com/", "title": "Gainsight | Customer Success Platform", "description": "Gainsight helps companies drive customer retention and revenue through a customer success platform"},
    {"url": "https://www.churnzero.com/", "title": "ChurnZero | Customer Success Software", "description": "Real-time customer success platform for SaaS businesses. Reduce churn and drive expansion revenue"},
    {"url": "https://www.totango.com/", "title": "Totango | Customer Success Platform", "description": "Customer success software that helps teams manage customer health scores and playbooks"},
    {"url": "https://www.vitally.io/", "title": "Vitally | Customer Success Platform", "description": "CS platform built for high-growth SaaS. Track health scores, automate playbooks, and manage renewals"},
    {"url": "https://www.planhat.com/", "title": "Planhat | Customer Platform", "description": "Customer success software with health scoring, onboarding automation, and NPS tracking"},
    {"url": "https://www.catalyst.io/", "title": "Catalyst | Customer Success Software", "description": "Customer success platform for proactive retention and expansion revenue management"},
]

def run_filter_test(cases: list[dict], expected_keep: bool) -> dict:
    """Run all test cases and return results."""
    results = []
    for case in cases:
        item = {
            "url": case["url"],
            "title": case["title"],
            "description": case.get("description", ""),
        }
        result = _should_keep_google_search_result(case["url"], item, config)
        results.append({
            "url": case["url"],
            "title": case["title"][:60],
            "kept": result,
            "expected_kept": expected_keep,
            "pass": result == expected_keep,
        })
    return results

print("Running M38 discovery quality filter validation...")
print("=" * 60)

reject_results = run_filter_test(SHOULD_REJECT, expected_keep=False)
keep_results = run_filter_test(SHOULD_KEEP, expected_keep=True)

all_results = reject_results + keep_results
passed = sum(1 for r in all_results if r["pass"])
failed = sum(1 for r in all_results if not r["pass"])

print(f"\nFilter validation: {passed}/{len(all_results)} passed")
print("\n--- REJECT tests (should be filtered out) ---")
for r in reject_results:
    status = "PASS" if r["pass"] else "FAIL"
    action = "rejected" if not r["kept"] else "kept (WRONG)"
    print(f"  [{status}] {action}: {r['title'][:55]}")

print("\n--- KEEP tests (should pass through) ---")
for r in keep_results:
    status = "PASS" if r["pass"] else "FAIL"
    action = "kept" if r["kept"] else "rejected (WRONG)"
    print(f"  [{status}] {action}: {r['title'][:55]}")

if failed > 0:
    print(f"\nFAILED: {failed} test(s) did not pass.")
    for r in all_results:
        if not r["pass"]:
            print(f"  - {r['url']} (kept={r['kept']}, expected_kept={r['expected_kept']})")
    sys.exit(1)

print(f"\nAll {passed} tests passed.")

# Output proof artifact data
proof = {
    "milestone_id": "M38",
    "test_summary": {
        "total": len(all_results),
        "passed": passed,
        "failed": failed,
        "reject_tests": {"total": len(reject_results), "passed": sum(1 for r in reject_results if r["pass"])},
        "keep_tests": {"total": len(keep_results), "passed": sum(1 for r in keep_results if r["pass"])},
    },
    "filter_config": {
        "denylisted_domains_count": len(config.junk_domain_denylist),
        "article_path_hints_count": len(config.article_path_hints),
        "content_hints_count": len(config.content_hints),
    },
    "reject_results": reject_results,
    "keep_results": keep_results,
}
print("\nProof data:")
print(json.dumps(proof, indent=2))
