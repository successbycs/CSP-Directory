"""Vendor intelligence extraction schema.

This module defines the schema used to represent extracted vendor intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from services.extraction.identity import (
    normalize_email_address as _normalize_email_address,
    normalize_email_list as _normalize_email_list,
    normalize_phone_number as _normalize_phone_number,
    normalize_phone_numbers as _normalize_phone_numbers,
    normalize_vendor_website as _normalize_vendor_website,
    normalize_website_url as _normalize_website_url,
)

CANONICAL_LIFECYCLE_STAGES = [
    "Sign",
    "Onboard",
    "Activate",
    "Adopt",
    "Support",
    "Expand",
    "Renew",
    "Advocate",
]

LIFECYCLE_STAGE_RULES = [
    (
        "Sign",
        [
            "call summary",
            "call summaries",
            "conversational intelligence",
            "conversation intelligence",
            "handoff",
            "meeting note",
            "meeting notes",
            "meeting summary",
            "meeting summaries",
            "notetaker",
            "sales to cs handoff",
            "sales-to-cs handoff",
        ],
    ),
    (
        "Onboard",
        [
            "implementation portal",
            "implementation portals",
            "onboarding automation",
            "professional services automation",
            "psa",
            "time to value",
            "time-to-value",
        ],
    ),
    (
        "Activate",
        [
            "adoption nudge",
            "adoption nudges",
            "guided onboarding",
            "in app guidance",
            "in-app guidance",
            "product walkthrough",
            "product walkthroughs",
            "user education",
            "walkthrough",
            "walkthroughs",
        ],
    ),
    (
        "Adopt",
        [
            "customer health",
            "health score",
            "health scoring",
            "playbook automation",
            "sentiment analysis",
            "signal to playbook",
            "signal-to-playbook",
            "usage analytics",
            "usage signals",
        ],
    ),
    (
        "Support",
        [
            "agent assist",
            "case deflection",
            "case routing",
            "help desk",
            "knowledge base",
            "support automation",
            "support copilot",
            "support platform",
            "ticket triage",
        ],
    ),
    (
        "Expand",
        [
            "cross sell",
            "cross-sell",
            "expansion revenue",
            "stakeholder mapping",
            "upsell",
        ],
    ),
    (
        "Renew",
        [
            "churn",
            "churn prediction",
            "forecasting",
            "renewal",
            "renewal automation",
            "renewals",
            "risk alert",
            "risk alerts",
        ],
    ),
    (
        "Advocate",
        [
            "case studies",
            "case study",
            "nps",
            "reference management",
            "reference program",
            "voice of customer",
            "voc",
        ],
    ),
]

USE_CASE_RULES = [
    (["sales to cs handoff", "sales-to-cs handoff", "meeting summary", "meeting summaries"], "sales-to-cs handoff"),
    (["conversational intelligence", "conversation intelligence", "call summary", "call summaries"], "meeting intelligence"),
    (["onboarding automation", "implementation portal", "implementation portals"], "onboarding"),
    (["time to value", "time-to-value"], "time to value"),
    (["in-app guidance", "in app guidance", "user education", "product walkthrough", "product walkthroughs"], "product activation"),
    (["adoption nudge", "adoption nudges", "guided onboarding"], "adoption guidance"),
    (["health score", "health scoring", "customer health"], "health scoring"),
    (["usage analytics", "usage signals"], "usage analytics"),
    (["sentiment analysis"], "sentiment analysis"),
    (["signal to playbook", "signal-to-playbook", "playbook automation"], "playbook automation"),
    (["support automation", "support platform", "help desk", "agent assist"], "support automation"),
    (["ticket triage", "case routing", "case deflection"], "ticket triage"),
    (["knowledge base"], "knowledge base"),
    (["upsell", "cross-sell", "cross sell", "expansion revenue"], "expansion"),
    (["stakeholder mapping"], "stakeholder mapping"),
    (["renewal automation", "renewal", "renewals"], "renewal management"),
    (["churn", "churn prediction", "risk alert", "risk alerts"], "churn prevention"),
    (["nps", "voice of customer", "voc"], "voice of customer"),
    (["reference management", "reference program", "case study", "case studies"], "customer advocacy"),
]

VALUE_STATEMENT_RULES = [
    (["sales to cs handoff", "sales-to-cs handoff", "meeting summaries", "meeting summary"], "improve handoff"),
    (["speed time to value", "speeds time to value", "time to value", "time-to-value"], "speed time to value"),
    (["reduce churn", "reduces churn", "churn prediction", "risk alert", "risk alerts"], "reduce churn"),
    (["improve adoption", "improves adoption", "in-app guidance", "in app guidance", "user education", "product walkthrough", "product walkthroughs"], "improve adoption"),
    (["improve customer health", "improving customer health", "customer health", "health score", "health scoring"], "improve customer health"),
    (["support automation", "help desk", "agent assist", "ticket triage", "case deflection"], "reduce support workload"),
    (["automate workflows", "automates workflows", "signal to playbook", "signal-to-playbook", "playbook automation"], "automate workflows"),
    (["onboarding automation", "implementation portal", "implementation portals"], "automate onboarding"),
    (["increase retention", "increasing retention", "renewal automation", "renewal", "renewals"], "increase retention"),
    (["upsell", "cross-sell", "cross sell", "expansion revenue"], "grow expansion revenue"),
    (["forecasting", "renewal automation", "risk alert", "risk alerts"], "improve renewal forecasting"),
    (["nps", "voice of customer", "voc", "reference management", "case study", "case studies"], "strengthen customer advocacy"),
]

ICP_RULES = [
    (["for saas companies", "saas companies", "for modern saas teams"], "SaaS companies"),
    (["for b2b startups", "b2b startups", "for b2b software teams"], "B2B startups"),
    (["for product-led teams", "product-led teams", "for product led teams", "product led teams"], "product-led teams"),
    (["for customer success teams", "customer success teams", "built for customer success teams"], "customer success teams"),
    (["for support teams", "support teams", "built for support teams"], "support teams"),
    (["for revenue teams", "revenue teams", "for revenue operations teams"], "revenue teams"),
]

PRICING_RULES = [
    (["per seat"], "per seat"),
    (["per user"], "per user"),
    (["per month", "/month", "monthly"], "per month"),
    (["per year", "/year", "annually"], "per year"),
    (["contact sales", "custom pricing"], "contact sales"),
]

CASE_STUDY_RULES = [
    (["case study", "case studies"], "case study"),
    (["customer story", "customer stories"], "customer story"),
]

CANONICAL_INTEGRATION_CATEGORIES = [
    "crm",
    "csp",
    "pm",
    "workflow",
    "email/calendar",
    "communication",
    "support",
    "warehouse",
    "other",
]

INTEGRATION_CATEGORY_RULES = [
    (["crm", "customer relationship management", "salesforce", "hubspot", "pipedrive", "dynamics 365"], "crm"),
    (
        [
            "customer success platform",
            "customer success platforms",
            "gainsight",
            "totango",
            "churnzero",
            "vitally",
            "custify",
            "planhat",
            "catalyst",
        ],
        "csp",
    ),
    (
        [
            "project management",
            "issue tracking",
            "ticket planning",
            "jira",
            "asana",
            "linear",
            "clickup",
            "monday",
            "trello",
        ],
        "pm",
    ),
    (
        [
            "workflow automation",
            "automation platform",
            "integration platform",
            "zapier",
            "make.com",
            "workato",
            "tray.io",
            "n8n",
        ],
        "workflow",
    ),
    (
        [
            "email integration",
            "calendar integration",
            "gmail",
            "google calendar",
            "outlook",
            "office 365",
            "microsoft 365",
            "calendly",
        ],
        "email/calendar",
    ),
    (["slack", "microsoft teams", "chat integration", "team chat"], "communication"),
    (["zendesk", "intercom", "freshdesk", "help scout", "servicenow", "service now", "ticketing"], "support"),
    (
        [
            "data warehouse",
            "warehouse",
            "snowflake",
            "bigquery",
            "redshift",
            "databricks",
            "segment",
        ],
        "warehouse",
    ),
]

INTEGRATION_BRAND_RULES = [
    ("Salesforce", "crm", ["salesforce", "sales cloud"]),
    ("HubSpot", "crm", ["hubspot"]),
    ("Microsoft Dynamics 365", "crm", ["microsoft dynamics", "dynamics 365"]),
    ("Pipedrive", "crm", ["pipedrive"]),
    ("Gainsight", "csp", ["gainsight"]),
    ("Totango", "csp", ["totango"]),
    ("ChurnZero", "csp", ["churnzero", "churn zero"]),
    ("Vitally", "csp", ["vitally"]),
    ("Custify", "csp", ["custify"]),
    ("Planhat", "csp", ["planhat"]),
    ("Catalyst", "csp", ["catalyst"]),
    ("Jira", "pm", ["jira"]),
    ("Asana", "pm", ["asana"]),
    ("Linear", "pm", ["linear"]),
    ("ClickUp", "pm", ["clickup", "click up"]),
    ("Monday.com", "pm", ["monday.com", "monday"]),
    ("Trello", "pm", ["trello"]),
    ("Zapier", "workflow", ["zapier"]),
    ("Make", "workflow", ["make.com"]),
    ("Workato", "workflow", ["workato"]),
    ("Tray.io", "workflow", ["tray.io", "tray"]),
    ("n8n", "workflow", ["n8n"]),
    ("Gmail", "email/calendar", ["gmail", "google mail"]),
    ("Google Calendar", "email/calendar", ["google calendar"]),
    ("Outlook", "email/calendar", ["outlook", "microsoft outlook"]),
    ("Office 365", "email/calendar", ["office 365", "microsoft 365"]),
    ("Calendly", "email/calendar", ["calendly"]),
    ("Slack", "communication", ["slack"]),
    ("Microsoft Teams", "communication", ["microsoft teams"]),
    ("Zendesk", "support", ["zendesk"]),
    ("Intercom", "support", ["intercom"]),
    ("Freshdesk", "support", ["freshdesk"]),
    ("Help Scout", "support", ["help scout", "helpscout"]),
    ("ServiceNow", "support", ["servicenow", "service now"]),
    ("Snowflake", "warehouse", ["snowflake"]),
    ("BigQuery", "warehouse", ["bigquery", "big query"]),
    ("Redshift", "warehouse", ["redshift"]),
    ("Databricks", "warehouse", ["databricks"]),
    ("Segment", "warehouse", ["segment"]),
    # Analytics / product intelligence (from n8n node catalog)
    ("Amplitude", "analytics", ["amplitude"]),
    ("Mixpanel", "analytics", ["mixpanel"]),
    ("Pendo", "analytics", ["pendo"]),
    ("FullStory", "analytics", ["fullstory", "full story"]),
    ("Heap", "analytics", ["heap analytics", "heap"]),
    ("Google Analytics", "analytics", ["google analytics", "ga4"]),
    ("Hotjar", "analytics", ["hotjar"]),
    ("PostHog", "analytics", ["posthog", "post hog"]),
    # Conversation intelligence
    ("Gong", "conversation_intelligence", ["gong"]),
    ("Chorus", "conversation_intelligence", ["chorus.ai", "chorus"]),
    ("Clari", "conversation_intelligence", ["clari"]),
    # Sales engagement / outreach
    ("Outreach", "sales_engagement", ["outreach"]),
    ("Salesloft", "sales_engagement", ["salesloft", "sales loft"]),
    ("Apollo", "sales_engagement", ["apollo.io", "apollo"]),
    # Marketing automation
    ("Marketo", "marketing", ["marketo", "marketo engage"]),
    ("Pardot", "marketing", ["pardot", "salesforce marketing cloud account engagement"]),
    ("Mailchimp", "marketing", ["mailchimp"]),
    ("HubSpot Marketing", "marketing", ["hubspot marketing", "hubspot email"]),
    ("ActiveCampaign", "marketing", ["activecampaign", "active campaign"]),
    ("Brevo", "marketing", ["brevo", "sendinblue"]),
    # Transactional email / messaging
    ("SendGrid", "email_infra", ["sendgrid", "send grid"]),
    ("Twilio", "email_infra", ["twilio"]),
    ("Postmark", "email_infra", ["postmark"]),
    ("Resend", "email_infra", ["resend"]),
    # Billing / subscriptions
    ("Stripe", "billing", ["stripe"]),
    ("Chargebee", "billing", ["chargebee", "charge bee"]),
    ("Recurly", "billing", ["recurly"]),
    ("Paddle", "billing", ["paddle"]),
    ("Zuora", "billing", ["zuora"]),
    # Collaboration / docs
    ("Notion", "docs", ["notion"]),
    ("Confluence", "docs", ["confluence", "atlassian confluence"]),
    ("Google Docs", "docs", ["google docs"]),
    ("Coda", "docs", ["coda.io", "coda"]),
    # Spreadsheet / data entry
    ("Google Sheets", "spreadsheet", ["google sheets"]),
    ("Airtable", "spreadsheet", ["airtable"]),
    ("Smartsheet", "spreadsheet", ["smartsheet"]),
    # BI / reporting
    ("Tableau", "bi", ["tableau"]),
    ("Looker", "bi", ["looker", "google looker"]),
    ("Power BI", "bi", ["power bi", "microsoft power bi", "powerbi"]),
    ("Metabase", "bi", ["metabase"]),
    ("Domo", "bi", ["domo"]),
    # Video / async
    ("Zoom", "video", ["zoom"]),
    ("Loom", "video", ["loom"]),
    ("Webex", "video", ["webex", "cisco webex"]),
    # Customer support (extended)
    ("Front", "support", ["front", "front app"]),
    ("Kustomer", "support", ["kustomer"]),
    ("Gorgias", "support", ["gorgias"]),
    ("Gladly", "support", ["gladly"]),
    ("Dixa", "support", ["dixa"]),
    # Survey
    ("Qualtrics", "survey", ["qualtrics"]),
    ("SurveyMonkey", "survey", ["surveymonkey", "survey monkey"]),
    ("Typeform", "survey", ["typeform"]),
    ("Delighted", "survey", ["delighted"]),
    ("AskNicely", "survey", ["asknicely", "ask nicely"]),
    # Code / DevOps (common in PLG / developer-led CS)
    ("GitHub", "devops", ["github"]),
    ("GitLab", "devops", ["gitlab"]),
    ("Jira Service Management", "devops", ["jira service management", "jira service desk"]),
    # CDP / enrichment
    ("Clearbit", "enrichment", ["clearbit"]),
    ("ZoomInfo", "enrichment", ["zoominfo", "zoom info"]),
    ("6sense", "enrichment", ["6sense"]),
    ("Demandbase", "enrichment", ["demandbase"]),
]

KNOWN_INTEGRATIONS = [canonical_name for canonical_name, _category, _aliases in INTEGRATION_BRAND_RULES]

SUPPORT_SIGNAL_RULES = [
    (["help center", "help centre", "help-center"], "help center"),
    (["knowledge base", "knowledge-base"], "knowledge base"),
    (["support portal", "support center", "support-centre"], "support portal"),
    (["community forum", "community support"], "community"),
    (["academy", "training"], "training"),
]

COMPLIANCE_RULES = [
    (["soc 2", "soc2", "soc ii"], "SOC 2"),
    (["iso 27001", "iso27001"], "ISO 27001"),
    (["iso 27701", "iso27701"], "ISO 27701"),
    (["iso 9001", "iso9001"], "ISO 9001"),
    (["hipaa"], "HIPAA"),
    (["gdpr"], "GDPR"),
    (["ccpa"], "CCPA"),
    (["trust center", "trust centre"], "Trust Center"),
    (["security review", "security questionnaire"], "Security Review"),
]

CUSTOMER_PATTERNS = [
    r"trusted by ([A-Z][A-Za-z0-9&.-]+(?:,\s*[A-Z][A-Za-z0-9&.-]+){0,4})",
    r"customers include ([A-Z][A-Za-z0-9&.-]+(?:,\s*[A-Z][A-Za-z0-9&.-]+){0,4})",
    r"used by ([A-Z][A-Za-z0-9&.-]+(?:,\s*[A-Z][A-Za-z0-9&.-]+){0,4})",
    r"how ([A-Z][A-Za-z0-9&.-]+) uses",
    # M49: additional case-study page patterns
    r"(?:join|like|including)\s+([A-Z][A-Za-z0-9&.-]+(?:,\s*[A-Z][A-Za-z0-9&.-]+){0,4})\s+(?:who|that|and)",
    r"(?:read|see|view)\s+how\s+([A-Z][A-Za-z0-9&.-]+)\s+",
    r"([A-Z][A-Za-z0-9&.-]+)\s+(?:reduced|increased|improved|cut|saved|grew|achieved|deployed|uses|used)\s",
    r"case study[:\s]+([A-Z][A-Za-z0-9&.-]+)",
    r"customer story[:\s]+([A-Z][A-Za-z0-9&.-]+)",
    r"([A-Z][A-Za-z0-9&.-]+)\s+(?:chose|selected|implemented|adopted)\s+",
]
STRONG_CS_RELEVANCE_HINTS = [
    "customer success",
    "customer success teams",
    "customer onboarding",
    "customer health",
    "health score",
    "health scoring",
    "implementation portal",
    "implementation portals",
    "in-app guidance",
    "onboarding automation",
    "playbook automation",
    "renewal automation",
    "sales to cs handoff",
    "sales-to-cs handoff",
    "stakeholder mapping",
    "support automation",
    "ticket triage",
    "time to value",
    "time-to-value",
    "usage analytics",
    "voice of customer",
]


@dataclass
class VendorIntelligence:
    vendor_name: str
    website: str
    source: str = ""
    mission: str = ""
    usp: str = ""
    icp: list[str] = field(default_factory=list)
    icp_buyer: list[dict[str, Any]] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    lifecycle_stages: list[str] = field(default_factory=list)
    pricing: list[str] = field(default_factory=list)
    free_trial: bool | None = None
    soc2: bool | None = None
    compliance: list[str] = field(default_factory=list)
    founded: str = ""
    products: list[dict[str, Any]] = field(default_factory=list)
    leadership: list[dict[str, Any]] = field(default_factory=list)
    ceo_name: str = ""
    ceo_linkedin: str = ""
    hq_address: str = ""
    phone_numbers: list[str] = field(default_factory=list)
    contact_emails: list[str] = field(default_factory=list)
    company_hq: str = ""
    contact_email: str = ""
    contact_page_url: str = ""
    demo_url: str = ""
    help_center_url: str = ""
    support_url: str = ""
    about_url: str = ""
    team_url: str = ""
    developer_docs_url: str = ""
    integration_categories: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    integration_taxonomy: list[dict[str, Any]] = field(default_factory=list)
    external_enrichment: list[dict[str, Any]] = field(default_factory=list)
    support_signals: list[str] = field(default_factory=list)
    case_studies: list[str] = field(default_factory=list)
    case_study_signals: list[str] = field(default_factory=list)
    case_study_details: list[dict[str, Any]] = field(default_factory=list)
    testimonials: list[dict[str, Any]] = field(default_factory=list)
    blog_posts: list[dict[str, Any]] = field(default_factory=list)
    customers: list[str] = field(default_factory=list)
    value_statements: list[str] = field(default_factory=list)
    confidence: str = ""
    source_urls: list[str] = field(default_factory=list)
    evidence_urls: list[str] = field(default_factory=list)
    directory_fit: str = ""
    directory_category: str = ""
    include_in_directory: bool | None = None
    llm_directory_fit: str = ""
    llm_directory_category: str = ""
    llm_include_in_directory: bool | None = None
    directory_decision_source: str = ""
    directory_reasoning: list[str] = field(default_factory=list)
    # M61: new enrichment fields
    youtube_channel_url: str = field(default="")
    funding_stage: str = field(default="")
    total_funding: str = field(default="")
    use_case_details: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize structured buyer-persona enrichment into a stable list-of-dicts shape."""
        self.website = normalize_vendor_website(self.website)
        self.icp_buyer = normalize_icp_buyer_profiles(self.icp_buyer)
        self.products = normalize_product_profiles(self.products)
        self.leadership = normalize_leadership_profiles(self.leadership)
        self.ceo_name = self.ceo_name.strip() or _extract_ceo_name(self.leadership)
        self.ceo_linkedin = self.ceo_linkedin.strip() or _extract_ceo_linkedin_from_leadership(self.leadership)
        self.hq_address = self.hq_address.strip() or self.company_hq.strip()
        self.company_hq = self.company_hq.strip() or self.hq_address
        self.phone_numbers = normalize_phone_numbers(self.phone_numbers)
        self.contact_emails = normalize_email_list(self.contact_emails)
        if self.contact_email:
            self.contact_email = normalize_email_address(self.contact_email)
            if self.contact_email and self.contact_email not in self.contact_emails:
                self.contact_emails.insert(0, self.contact_email)
        elif self.contact_emails:
            self.contact_email = self.contact_emails[0]
        self.contact_page_url = normalize_website_url(self.contact_page_url)
        self.demo_url = normalize_website_url(self.demo_url)
        self.help_center_url = normalize_website_url(self.help_center_url)
        self.support_url = normalize_website_url(self.support_url)
        self.about_url = normalize_website_url(self.about_url)
        self.team_url = normalize_website_url(self.team_url)
        self.developer_docs_url = normalize_website_url(self.developer_docs_url)
        self.integration_categories = _normalize_string_list(self.integration_categories)
        self.integrations = _normalize_string_list(self.integrations)
        self.integration_taxonomy = normalize_integration_taxonomy(
            self.integration_taxonomy,
            integrations=self.integrations,
            categories=self.integration_categories,
        )
        self.integration_categories = [item["category"] for item in self.integration_taxonomy]
        self.integrations = _flatten_integration_taxonomy(self.integration_taxonomy)
        self.external_enrichment = normalize_external_enrichment_records(self.external_enrichment)
        self.support_signals = _normalize_string_list(self.support_signals)
        self.directory_reasoning = _normalize_string_list(self.directory_reasoning)
        self.compliance = normalize_compliance_signals(self.compliance)
        self.case_study_details = normalize_case_study_details(self.case_study_details)
        self.testimonials = normalize_testimonial_records(self.testimonials)
        self.blog_posts = normalize_blog_posts(self.blog_posts)
        self.source_urls = [url for url in (normalize_website_url(url) for url in self.source_urls) if url]
        self.evidence_urls = [url for url in (normalize_website_url(url) for url in self.evidence_urls) if url]
        if not self.source_urls and self.evidence_urls:
            self.source_urls = list(self.evidence_urls)
        if not self.evidence_urls and self.source_urls:
            self.evidence_urls = list(self.source_urls)
        if not self.compliance and self.soc2:
            self.compliance = ["SOC 2"]
        if self.compliance and self.soc2 is None:
            self.soc2 = "SOC 2" in self.compliance
        self.youtube_channel_url = normalize_website_url(self.youtube_channel_url)
        self.funding_stage = self.funding_stage.strip()
        self.total_funding = self.total_funding.strip()
        self.use_case_details = _normalize_use_case_details(self.use_case_details)

    def validate(self) -> None:
        """Validate the schema structure and types.

        Raises:
            TypeError: If any field is missing or has an unexpected type.
        """
        if not isinstance(self.vendor_name, str):
            raise TypeError("vendor_name must be a string")
        if not isinstance(self.website, str):
            raise TypeError("website must be a string")
        for field_name in [
            "source",
            "mission",
            "usp",
            "founded",
            "confidence",
            "directory_fit",
            "directory_category",
            "llm_directory_fit",
            "llm_directory_category",
            "directory_decision_source",
            "ceo_name",
            "ceo_linkedin",
            "youtube_channel_url",
            "funding_stage",
            "total_funding",
            "hq_address",
            "company_hq",
            "contact_email",
            "contact_page_url",
            "demo_url",
            "help_center_url",
            "support_url",
            "about_url",
            "team_url",
            "developer_docs_url",
        ]:
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")

        for field_name in [
            "icp",
            "use_cases",
            "lifecycle_stages",
            "pricing",
            "integration_categories",
            "integrations",
            "support_signals",
            "compliance",
            "case_studies",
            "case_study_signals",
            "customers",
            "value_statements",
            "source_urls",
            "evidence_urls",
            "phone_numbers",
            "contact_emails",
            "directory_reasoning",
        ]:
            value = getattr(self, field_name)
            if not isinstance(value, list):
                raise TypeError(f"{field_name} must be a list")
            if not all(isinstance(item, str) for item in value):
                raise TypeError(f"All items in {field_name} must be strings")

        if not isinstance(self.icp_buyer, list):
            raise TypeError("icp_buyer must be a list")
        if not all(isinstance(item, dict) for item in self.icp_buyer):
            raise TypeError("All items in icp_buyer must be objects")
        if not isinstance(self.products, list):
            raise TypeError("products must be a list")
        if not all(isinstance(item, dict) for item in self.products):
            raise TypeError("All items in products must be objects")
        if not isinstance(self.integration_taxonomy, list):
            raise TypeError("integration_taxonomy must be a list")
        if not all(isinstance(item, dict) for item in self.integration_taxonomy):
            raise TypeError("All items in integration_taxonomy must be objects")
        if not isinstance(self.external_enrichment, list):
            raise TypeError("external_enrichment must be a list")
        if not all(isinstance(item, dict) for item in self.external_enrichment):
            raise TypeError("All items in external_enrichment must be objects")
        if not isinstance(self.leadership, list):
            raise TypeError("leadership must be a list")
        if not all(isinstance(item, dict) for item in self.leadership):
            raise TypeError("All items in leadership must be objects")
        if not isinstance(self.case_study_details, list):
            raise TypeError("case_study_details must be a list")
        if not all(isinstance(item, dict) for item in self.case_study_details):
            raise TypeError("All items in case_study_details must be objects")
        if not isinstance(self.testimonials, list):
            raise TypeError("testimonials must be a list")
        if not all(isinstance(item, dict) for item in self.testimonials):
            raise TypeError("All items in testimonials must be objects")
        if not isinstance(self.blog_posts, list):
            raise TypeError("blog_posts must be a list")
        if not all(isinstance(item, dict) for item in self.blog_posts):
            raise TypeError("All items in blog_posts must be objects")
        if not isinstance(self.use_case_details, list):
            raise TypeError("use_case_details must be a list")
        if not all(isinstance(item, dict) for item in self.use_case_details):
            raise TypeError("All items in use_case_details must be objects")

        for field_name in ["free_trial", "soc2", "include_in_directory", "llm_include_in_directory"]:
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{field_name} must be a bool or None")

        invalid_lifecycle_stages = [
            lifecycle_stage
            for lifecycle_stage in self.lifecycle_stages
            if lifecycle_stage not in CANONICAL_LIFECYCLE_STAGES
        ]
        if invalid_lifecycle_stages:
            raise TypeError(
                "lifecycle_stages must only contain canonical stage names: "
                + ", ".join(invalid_lifecycle_stages)
            )


def normalize_icp_buyer_profiles(value: object) -> list[dict[str, Any]]:
    """Return a normalized buyer-persona enrichment payload."""
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        return normalize_icp_buyer_profiles(parsed)

    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_personas: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue

        persona = str(raw_item.get("persona") or "").strip()
        if not persona:
            continue
        lowered_persona = persona.lower()
        if lowered_persona in seen_personas:
            continue

        confidence = _normalize_confidence_label(raw_item.get("confidence"))
        google_queries = _normalize_query_list(raw_item.get("google_queries"))
        geo_queries = _normalize_query_list(raw_item.get("geo_queries"))
        evidence = _normalize_string_list(raw_item.get("evidence"))

        normalized.append(
            {
                "persona": persona,
                "confidence": confidence,
                "evidence": evidence,
                "google_queries": google_queries,
                "geo_queries": geo_queries,
            }
        )
        seen_personas.add(lowered_persona)

    return normalized


def normalize_product_profiles(value: object) -> list[dict[str, Any]]:
    """Return normalized structured product metadata."""
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        return normalize_product_profiles(parsed)

    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for raw_item in value:
        if isinstance(raw_item, str):
            raw_item = {"name": raw_item}
        if not isinstance(raw_item, dict):
            continue

        name = str(raw_item.get("name") or "").strip()
        if not name:
            continue

        key = name.lower()
        if key in seen_keys:
            continue

        normalized.append(
            {
                "name": name,
                "category": str(raw_item.get("category") or "").strip(),
                "description": str(raw_item.get("description") or "").strip(),
                "use_cases": _normalize_string_list(raw_item.get("use_cases")),
                "integration_categories": _normalize_string_list(raw_item.get("integration_categories")),
                "integrations": _normalize_string_list(raw_item.get("integrations")),
                "demo_url": normalize_website_url(raw_item.get("demo_url")),
                "support_url": normalize_website_url(raw_item.get("support_url")),
                "help_center_url": normalize_website_url(raw_item.get("help_center_url")),
                "developer_docs_url": normalize_website_url(raw_item.get("developer_docs_url")),
                "source_url": normalize_website_url(raw_item.get("source_url")),
            }
        )
        seen_keys.add(key)
    return normalized


def normalize_integration_taxonomy(
    value: object,
    *,
    integrations: list[str] | None = None,
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return grouped integrations in a stable category-first shape."""
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            value = []
        else:
            try:
                value = json.loads(cleaned)
            except json.JSONDecodeError:
                value = []

    grouped: dict[str, list[str]] = {}
    seeded_categories: list[str] = []

    def seed_category(raw_category: object) -> None:
        category = _normalize_integration_category(raw_category)
        if not category:
            return
        grouped.setdefault(category, [])
        if category not in seeded_categories:
            seeded_categories.append(category)

    def add_integration(raw_name: object, *, raw_category: object = "") -> None:
        name = _canonicalize_integration_name(raw_name)
        category = _normalize_integration_category(raw_category) or _infer_integration_category(name)
        if not category and not name:
            return
        category = category or "other"
        grouped.setdefault(category, [])
        if category not in seeded_categories:
            seeded_categories.append(category)
        if name and name not in grouped[category]:
            grouped[category].append(name)

    if isinstance(value, dict):
        for raw_category, raw_integrations in value.items():
            seed_category(raw_category)
            for raw_integration in _normalize_string_list(raw_integrations):
                add_integration(raw_integration, raw_category=raw_category)
    elif isinstance(value, list):
        for raw_item in value:
            if isinstance(raw_item, dict):
                raw_category = raw_item.get("category")
                seed_category(raw_category)
                for raw_integration in _normalize_string_list(raw_item.get("integrations")):
                    add_integration(raw_integration, raw_category=raw_category)
            elif isinstance(raw_item, str):
                raw_string = raw_item.strip()
                if _normalize_integration_category(raw_string):
                    seed_category(raw_string)
                else:
                    add_integration(raw_string)

    for raw_category in categories or []:
        seed_category(raw_category)
    for raw_integration in integrations or []:
        add_integration(raw_integration)

    ordered_categories = [
        category
        for category in CANONICAL_INTEGRATION_CATEGORIES
        if category in grouped and (grouped[category] or category in seeded_categories)
    ]
    return [
        {
            "category": category,
            "integrations": grouped[category],
        }
        for category in ordered_categories
    ]


def normalize_external_enrichment_records(value: object) -> list[dict[str, Any]]:
    """Return normalized external enrichment provenance records.

    Supports two schemas:
    - Legacy: {provider, source_id, source_type, status, source_url, captured_at, freshness_days, fields, notes}
    - Provenance (M63): {field, url, source, value, fetched_at}
    """
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        return normalize_external_enrichment_records(parsed)

    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue

        # M63 provenance schema: field + url + source + value + fetched_at
        field_name = str(raw_item.get("field") or "").strip()
        if field_name:
            url = normalize_website_url(raw_item.get("url"))
            source = str(raw_item.get("source") or "webcrawl").strip()
            value_str = str(raw_item.get("value") or "").strip()
            fetched_at = str(raw_item.get("fetched_at") or "").strip()
            key = (field_name.lower(), url.lower(), source.lower())
            if key in seen_keys:
                continue
            normalized.append(
                {
                    "field": field_name,
                    "url": url,
                    "source": source,
                    "value": value_str,
                    "fetched_at": fetched_at,
                }
            )
            seen_keys.add(key)
            continue

        # Legacy schema: provider-based enrichment records
        provider = str(raw_item.get("provider") or "").strip()
        source_id = str(raw_item.get("source_id") or provider).strip()
        source_type = str(raw_item.get("source_type") or "").strip()
        source_url = normalize_website_url(raw_item.get("source_url"))
        key = (provider.lower(), source_id.lower(), source_url.lower())
        if key in seen_keys or not any((provider, source_id, source_type, source_url)):
            continue

        freshness_days = raw_item.get("freshness_days")
        if not isinstance(freshness_days, int) or freshness_days < 0:
            freshness_days = None

        normalized.append(
            {
                "provider": provider,
                "source_id": source_id,
                "source_type": source_type,
                "status": str(raw_item.get("status") or "deferred").strip(),
                "source_url": source_url,
                "captured_at": str(raw_item.get("captured_at") or "").strip(),
                "freshness_days": freshness_days,
                "fields": _normalize_string_list(raw_item.get("fields")),
                "notes": str(raw_item.get("notes") or "").strip(),
            }
        )
        seen_keys.add(key)
    return normalized


def _make_provenance_record(
    field: str,
    value: str,
    url: str,
    source: str = "webcrawl",
) -> dict[str, str]:
    """Return a provenance record in the M63 schema: {field, url, source, value, fetched_at}."""
    from datetime import datetime, timezone
    return {
        "field": str(field).strip(),
        "url": normalize_website_url(url),
        "source": str(source).strip() or "webcrawl",
        "value": str(value).strip(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_leadership_profiles(value: object) -> list[dict[str, Any]]:
    """Return normalized structured leadership metadata."""
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        return normalize_leadership_profiles(parsed)

    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue

        name = str(raw_item.get("name") or "").strip()
        title = str(raw_item.get("title") or "").strip()
        if not name:
            continue

        key = (name.lower(), title.lower())
        if key in seen_keys:
            continue

        normalized.append(
            {
                "name": name,
                "title": title,
                "linkedin": _normalize_linkedin_url(raw_item.get("linkedin")),
                "source_url": normalize_website_url(raw_item.get("source_url")),
            }
        )
        seen_keys.add(key)
    return normalized


def normalize_case_study_details(value: object) -> list[dict[str, Any]]:
    """Return normalized structured case-study metadata."""
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        return normalize_case_study_details(parsed)

    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue

        client = str(raw_item.get("client") or "").strip()
        title = str(raw_item.get("title") or "").strip()
        use_case = str(raw_item.get("use_case") or "").strip()
        value_realized = str(raw_item.get("value_realized") or "").strip()
        metric = str(raw_item.get("metric") or "").strip() or _extract_case_study_metric(value_realized)
        if not any((client, title, use_case, value_realized)):
            continue

        key = (client.lower(), title.lower(), value_realized.lower())
        if key in seen_keys:
            continue

        detail = {
            "client": client,
            "title": title,
            "use_case": use_case,
            "value_realized": value_realized,
            "source_url": normalize_website_url(raw_item.get("source_url")),
        }
        if metric:
            detail["metric"] = metric
        normalized.append(detail)
        seen_keys.add(key)
    return normalized


def normalize_compliance_signals(value: object) -> list[str]:
    """Return canonical compliance/security signals."""
    raw_values = _normalize_string_list(value)
    normalized: list[str] = []
    for raw_value in raw_values:
        canonical_value = _canonicalize_compliance_label(raw_value)
        if canonical_value and canonical_value not in normalized:
            normalized.append(canonical_value)
    return normalized


def normalize_testimonial_records(value: object) -> list[dict[str, Any]]:
    """Return normalized testimonial proof records."""
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        return normalize_testimonial_records(parsed)

    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        company = str(raw_item.get("company") or "").strip()
        source_url = normalize_website_url(raw_item.get("source_url"))
        proof_type = str(raw_item.get("proof_type") or "").strip()
        summary = str(raw_item.get("summary") or "").strip()
        quote = str(raw_item.get("quote") or "").strip()
        if not any((company, source_url, summary, quote)):
            continue
        key = (company.lower(), source_url.lower(), proof_type.lower())
        if key in seen_keys:
            continue
        normalized.append(
            {
                "company": company,
                "proof_type": proof_type or "logo",
                "summary": summary,
                "quote": quote,
                "source_url": source_url,
                "date": str(raw_item.get("date") or "").strip(),
            }
        )
        seen_keys.add(key)
    return normalized


def normalize_blog_posts(value: object) -> list[dict[str, Any]]:
    """Return normalized blog/article proof records."""
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        return normalize_blog_posts(parsed)

    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        source_url = normalize_website_url(raw_item.get("source_url"))
        title = str(raw_item.get("title") or "").strip()
        body = str(raw_item.get("body") or "").strip()
        if not any((source_url, title, body)):
            continue
        key = source_url.lower() or title.lower()
        if key in seen_urls:
            continue
        summary = str(raw_item.get("summary") or "").strip()
        summary_word_count = raw_item.get("summary_word_count")
        if not isinstance(summary_word_count, int) or summary_word_count < 0:
            summary_word_count = len(summary.split()) if summary else 0
        normalized.append(
            {
                "title": title,
                "body": body[:4000],
                "summary": summary,
                "summary_word_count": summary_word_count,
                "customer_name": str(raw_item.get("customer_name") or "").strip(),
                "value_statements": _normalize_string_list(raw_item.get("value_statements")),
                "source_url": source_url,
            }
        )
        seen_urls.add(key)
    return normalized


def summarize_icp_buyer_profiles(profiles: list[dict[str, Any]]) -> str:
    """Return a readable summary of buyer personas for flat review surfaces."""
    personas = [str(item.get("persona") or "").strip() for item in profiles if isinstance(item, dict)]
    personas = [persona for persona in personas if persona]
    return ", ".join(personas)


def normalize_website_url(value: object) -> str:
    """Return a canonical website URL suitable for persistence."""
    return _normalize_website_url(value)


def normalize_vendor_website(value: object) -> str:
    """Return a canonical vendor homepage URL for identity and dedupe."""
    return _normalize_vendor_website(value)


def normalize_email_address(value: object) -> str:
    """Return a canonical email address suitable for persistence."""
    return _normalize_email_address(value)


def normalize_email_list(value: object) -> list[str]:
    """Return a deduplicated list of canonical email addresses."""
    return _normalize_email_list(value)


def normalize_phone_number(value: object) -> str:
    """Return a compact phone number string when the input looks valid."""
    return _normalize_phone_number(value)


def normalize_phone_numbers(value: object) -> list[str]:
    """Return a deduplicated list of canonical phone numbers."""
    return _normalize_phone_numbers(value)


def _normalize_query_list(value: object) -> list[str]:
    queries = _normalize_string_list(value)
    return queries[:5]


def _normalize_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        candidates = [segment.strip() for segment in value.replace("\n", ",").replace("|", ",").split(",")]
        normalized: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized

    if isinstance(value, list):
        normalized = []
        for item in value:
            cleaned_item = str(item).strip()
            if cleaned_item and cleaned_item not in normalized:
                normalized.append(cleaned_item)
        return normalized

    return []


def _normalize_confidence_label(value: object) -> str:
    cleaned = str(value or "").strip().lower()
    if cleaned in {"low", "medium", "high"}:
        return cleaned
    return ""


def _canonicalize_compliance_label(value: object) -> str:
    cleaned = str(value or "").strip()
    lowered = cleaned.lower()
    if not lowered:
        return ""
    for keywords, label in COMPLIANCE_RULES:
        if _contains_any(lowered, keywords):
            return label
    return cleaned


def extract_vendor_intelligence(
    page_payload: dict[str, object],
) -> VendorIntelligence:
    """Convert explored vendor page payloads into a VendorIntelligence object.

    This implementation uses simple rule-based keyword matching on
    homepage and high-signal vendor pages to populate directory fields.
    """
    page_payloads = _coerce_page_payloads(page_payload)
    homepage_payload = page_payloads.get("homepage", {})
    homepage_text = str(homepage_payload.get("text", "")).strip()
    combined_text = _combine_page_texts(page_payloads)
    combined_text_lower = combined_text.lower()
    relevance_text = _combine_relevance_texts(page_payloads).lower()
    pricing_text = _page_text(page_payloads, "pricing_page").lower()
    case_studies_text = _page_text(page_payloads, "case_studies_page")
    case_studies_text_lower = case_studies_text.lower()
    testimonials_text = _page_text(page_payloads, "testimonials_page")
    blog_text = _page_text(page_payloads, "blog_page")
    product_text = _page_text(page_payloads, "product_page")
    about_text = _page_text(page_payloads, "about_page")
    team_text = _page_text(page_payloads, "team_page")
    contact_text = _page_text(page_payloads, "contact_page")
    demo_text = _page_text(page_payloads, "demo_page")
    help_text = _page_text(page_payloads, "help_page")
    support_text = _page_text(page_payloads, "support_page")
    integrations_text = _page_text(page_payloads, "integrations_page")
    integration_source_text = integrations_text or combined_text
    security_text = _page_text(page_payloads, "security_page").lower()
    all_evidence_urls = _collect_page_urls(page_payloads)
    canonical_website = normalize_vendor_website(
        homepage_payload.get("website") or homepage_payload.get("url") or ""
    )
    leadership = _extract_leadership(
        f"{about_text} {team_text}".strip(),
        source_url=_page_url(page_payloads, "team_page") or _page_url(page_payloads, "about_page"),
    )
    hq_address = _extract_hq_address(f"{about_text} {contact_text}".strip())
    contact_emails = _extract_contact_emails(contact_text or combined_text)

    icp = _extract_icp(combined_text_lower)
    use_cases = _extract_use_cases(combined_text_lower)
    lifecycle_stages = _extract_lifecycle_stages(combined_text_lower)
    value_statements = _extract_value_statements(combined_text_lower)
    case_study_signals = _extract_case_study_signals(
        " ".join(
            part
            for part in (
                case_studies_text_lower,
                testimonials_text.lower(),
                blog_text.lower(),
                combined_text_lower,
            )
            if part
        )
    )
    # M49: extract customers from case_studies_page first (highest signal), fall back to combined
    customers = _extract_customers(case_studies_text or combined_text)
    if case_studies_text and not customers:
        customers = _extract_customers(combined_text)
    pricing = _extract_pricing(pricing_text or combined_text_lower)
    integrations = _extract_integrations(integration_source_text)
    integration_taxonomy = build_integration_taxonomy(
        integration_source_text,
        integrations=integrations,
    )
    case_study_details = _extract_case_study_details(
        case_studies_text or "",
        source_url=_page_url(page_payloads, "case_studies_page"),
    )
    free_trial = _detect_boolean_signal(combined_text_lower, ["free trial", "start free", "try free"])
    compliance = _extract_compliance(security_text or combined_text_lower)
    testimonials = _extract_testimonials(
        testimonials_text or case_studies_text or combined_text,
        source_url=_page_url(page_payloads, "testimonials_page") or _page_url(page_payloads, "case_studies_page") or canonical_website,
    )
    blog_posts = _extract_blog_posts(page_payloads)

    # M63: collect enrichment provenance records for fields extracted from specific pages
    provenance_records: list[dict[str, Any]] = []
    _case_studies_url = _page_url(page_payloads, "case_studies_page")
    _about_url = _page_url(page_payloads, "about_page")
    _team_url = _page_url(page_payloads, "team_page")
    if customers and _case_studies_url:
        provenance_records.append(_make_provenance_record(
            "customers", ", ".join(customers[:5]), _case_studies_url, "case_studies_page",
        ))
    if case_study_details and _case_studies_url:
        provenance_records.append(_make_provenance_record(
            "case_study_details", str(len(case_study_details)), _case_studies_url, "case_studies_page",
        ))
    if leadership and (_about_url or _team_url):
        names = ", ".join(p["name"] for p in leadership if p.get("name"))
        provenance_records.append(_make_provenance_record(
            "leadership", names, _about_url or _team_url, "about_page",
        ))
    ceo_name_extracted = _extract_ceo_name(leadership, f"{about_text} {team_text}".strip())
    if ceo_name_extracted and (_about_url or _team_url):
        provenance_records.append(_make_provenance_record(
            "ceo_name", ceo_name_extracted, _about_url or _team_url, "about_page",
        ))

    return VendorIntelligence(
        vendor_name=str(homepage_payload.get("vendor_name", "")),
        website=canonical_website,
        source=str(homepage_payload.get("source", "")),
        mission=_extract_mission(homepage_text or combined_text),
        usp=_extract_usp(value_statements, combined_text),
        icp=icp,
        use_cases=use_cases,
        lifecycle_stages=lifecycle_stages,
        pricing=pricing,
        free_trial=free_trial,
        soc2="SOC 2" in compliance if compliance else None,
        compliance=compliance,
        founded=_extract_founded(combined_text),
        products=_extract_products(
            product_text or homepage_text,
            source_url=_page_url(page_payloads, "product_page") or canonical_website,
        ),
        leadership=leadership,
        ceo_name=_extract_ceo_name(leadership, f"{about_text} {team_text}".strip()),
        ceo_linkedin=_extract_ceo_linkedin_from_leadership(leadership) or _extract_ceo_linkedin(f"{about_text} {team_text}".strip()),
        hq_address=hq_address,
        phone_numbers=_extract_phone_numbers(contact_text or combined_text),
        contact_emails=contact_emails,
        company_hq=hq_address,
        contact_email=contact_emails[0] if contact_emails else "",
        contact_page_url=_page_url(page_payloads, "contact_page"),
        demo_url=_page_url(page_payloads, "demo_page"),
        help_center_url=_page_url(page_payloads, "help_page"),
        support_url=_page_url(page_payloads, "support_page"),
        about_url=_page_url(page_payloads, "about_page"),
        team_url=_page_url(page_payloads, "team_page"),
        developer_docs_url=_page_url(page_payloads, "developer_docs_page"),
        integration_categories=[item["category"] for item in integration_taxonomy],
        integrations=integrations,
        integration_taxonomy=integration_taxonomy,
        support_signals=_extract_support_signals(
            f"{help_text} {support_text} {contact_text} {demo_text}".strip().lower()
        ),
        case_studies=_derive_case_studies_text(case_study_details),
        case_study_signals=case_study_signals,
        case_study_details=case_study_details,
        testimonials=testimonials,
        blog_posts=blog_posts,
        customers=customers,
        value_statements=value_statements,
        confidence=_determine_confidence(
            icp=icp,
            use_cases=use_cases,
            lifecycle_stages=lifecycle_stages,
            value_statements=value_statements,
            case_study_signals=case_study_signals,
            testimonials=testimonials,
            blog_posts=blog_posts,
            pricing=pricing,
            strong_cs_relevance=_has_strong_cs_relevance(relevance_text),
        ),
        external_enrichment=provenance_records,
        source_urls=all_evidence_urls,
        evidence_urls=all_evidence_urls,
        youtube_channel_url=_extract_youtube_channel_url_from_pages(page_payloads),
        funding_stage=_extract_funding_stage(combined_text),
    )


def _extract_lifecycle_stages(text: str) -> list[str]:
    """Return lifecycle stages detected from homepage text."""
    lifecycle_stages: list[str] = []

    for stage_name, keywords in LIFECYCLE_STAGE_RULES:
        if _contains_any(text, keywords):
            lifecycle_stages.append(stage_name)

    return lifecycle_stages


def _extract_use_cases(text: str) -> list[str]:
    """Return use cases detected from homepage text."""
    use_cases: list[str] = []

    for keywords, label in USE_CASE_RULES:
        if _contains_any(text, keywords) and label not in use_cases:
            use_cases.append(label)

    return use_cases


def _extract_compliance(text: str) -> list[str]:
    """Return normalized compliance and security signals from vendor text."""
    compliance: list[str] = []
    for keywords, label in COMPLIANCE_RULES:
        if _contains_any(text, keywords) and label not in compliance:
            compliance.append(label)
    return compliance


def _extract_icp(text: str) -> list[str]:
    """Return simple ICP labels detected from vendor text."""
    icp: list[str] = []

    for keywords, label in ICP_RULES:
        if _contains_any(text, keywords) and label not in icp:
            icp.append(label)

    return icp


def _extract_value_statements(text: str) -> list[str]:
    """Return value statements detected from homepage text."""
    value_statements: list[str] = []

    for phrases, label in VALUE_STATEMENT_RULES:
        if _contains_any(text, phrases):
            value_statements.append(label)

    return value_statements


def _extract_pricing(text: str) -> list[str]:
    """Return simple pricing signals from vendor text."""
    pricing: list[str] = []

    if "$" in text and "$" not in pricing:
        pricing.append("$")

    for keywords, label in PRICING_RULES:
        if _contains_any(text, keywords) and label not in pricing:
            pricing.append(label)

    return pricing


def _extract_case_study_signals(text: str) -> list[str]:
    """Return case-study detection keyword signals from vendor text.

    These are keyword signals (e.g., "case study", "customer story") that indicate
    the presence of case-study-type content. They are stored in case_study_signals,
    NOT in case_studies. The case_studies field is reserved for confirmed case study
    URLs or summaries from LLM extraction.
    """
    signals: list[str] = []

    for keywords, label in CASE_STUDY_RULES:
        if _contains_any(text, keywords) and label not in signals:
            signals.append(label)

    if re.search(r"how [a-z0-9&.-]+ uses", text) and "how customers use the product" not in signals:
        signals.append("how customers use the product")

    return signals


def _extract_testimonials(text: str, *, source_url: str) -> list[dict[str, Any]]:
    """Return testimonial-style proof objects from customer/logo text."""
    testimonials: list[dict[str, Any]] = []
    lowered_text = text.lower()
    for company in _extract_customers(text):
        testimonials.append(
            {
                "company": company,
                "proof_type": "logo" if "trusted by" in lowered_text or "used by" in lowered_text else "customer_story",
                "summary": f"Customer proof visible for {company}.",
                "quote": "",
                "source_url": normalize_website_url(source_url),
                "date": "",
            }
        )
    return normalize_testimonial_records(testimonials)


def _extract_blog_posts(page_payloads: dict[str, dict[str, str | int]]) -> list[dict[str, Any]]:
    """Return bounded blog/article/review page summaries from crawled pages."""
    blog_posts: list[dict[str, Any]] = []
    for page_key, page_payload in page_payloads.items():
        page_url = _page_url(page_payloads, page_key)
        if not page_url or not _looks_like_blog_url(page_url, page_key):
            continue
        page_text = _page_text(page_payloads, page_key)
        if not page_text:
            continue
        body = re.sub(r"\s+", " ", page_text).strip()
        summary = _summarize_text(body, max_words=60)
        customers = _extract_customers(body)
        blog_posts.append(
            {
                "title": _extract_page_title(page_payload),
                "body": body[:4000],
                "summary": summary,
                "summary_word_count": len(summary.split()),
                "customer_name": customers[0] if customers else "",
                "value_statements": _extract_value_statements(body.lower()),
                "source_url": page_url,
            }
        )
    return normalize_blog_posts(blog_posts)


def _extract_case_study_details(text: str, *, source_url: str) -> list[dict[str, str]]:
    """Return structured case-study rows when the page exposes customer outcomes."""
    normalized_text = re.sub(r"\s+", " ", text).strip()
    if not normalized_text:
        return []

    details: list[dict[str, str]] = []
    patterns = [
        re.compile(
            r"(?P<client>[A-Z][A-Za-z0-9&.\-]+)\s+(?:used|uses|using)\s+.+?\s+to\s+(?P<value_realized>[^.]+)",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"(?P<client>[A-Z][A-Za-z0-9&.\-]+)\s+(?P<value_realized>(?:reduced|increased|improved|cut)\s+[^.]+)",
            flags=re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        for match in pattern.finditer(normalized_text):
            client = match.group("client").strip()
            value_realized = match.group("value_realized").strip(" .")
            detail = {
                "client": client,
                "title": f"{client} case study",
                "use_case": _infer_case_study_use_case(value_realized),
                "value_realized": value_realized,
                "source_url": normalize_website_url(source_url),
            }
            metric = _extract_case_study_metric(value_realized)
            if metric:
                detail["metric"] = metric
            if detail not in details:
                details.append(detail)
    return details


def _derive_case_studies_text(case_study_details: list[dict[str, str]]) -> list[str]:
    """Return plain-text outcome statements derived from structured case_study_details. (M49)

    Each entry is a short human-readable string like "Acme reduced churn by 20%."
    Only confirmed outcome statements are included — keyword signals stay in case_study_signals.
    """
    results: list[str] = []
    for detail in case_study_details:
        client = str(detail.get("client") or "").strip()
        value_realized = str(detail.get("value_realized") or "").strip()
        if client and value_realized:
            statement = f"{client} {value_realized}".rstrip(".")
            if statement not in results:
                results.append(statement)
    return results


def _extract_customers(text: str) -> list[str]:
    """Return simple named-customer signals from vendor text."""
    customers: list[str] = []

    for pattern in CUSTOMER_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            for customer_name in re.split(r",|\band\b", match.group(1)):
                cleaned_name = customer_name.strip().strip(".")
                if cleaned_name and cleaned_name not in customers:
                    customers.append(cleaned_name)

    return customers


def _extract_products(text: str, *, source_url: str) -> list[dict[str, Any]]:
    """Return simple structured product rows for vendors with named products."""
    normalized_text = re.sub(r"\s+", " ", text).strip()
    if not normalized_text:
        return []

    products: list[dict[str, str]] = []
    product_match = re.search(
        r"(?:products?|platforms?)\s+(?:include|includes|are|:)\s*([^.]+)",
        normalized_text,
        flags=re.IGNORECASE,
    )
    if not product_match:
        return products

    raw_names = re.split(r",|\band\b", product_match.group(1))
    for raw_name in raw_names:
        name = raw_name.strip().strip(".")
        if not name:
            continue
        products.append(
            {
                "name": name,
                "category": "platform",
                "description": normalized_text[:200],
                "use_cases": [],
                "integration_categories": [],
                "integrations": [],
                "demo_url": "",
                "support_url": "",
                "help_center_url": "",
                "developer_docs_url": "",
                "source_url": normalize_website_url(source_url),
            }
        )
    return normalize_product_profiles(products)


def _extract_leadership(text: str, *, source_url: str) -> list[dict[str, str]]:
    """Return structured founder and executive evidence including LinkedIn URLs."""
    normalized_text = re.sub(r"\s+", " ", text).strip()
    if not normalized_text:
        return []

    # Build a name->linkedin map from LinkedIn URLs near name+title patterns
    linkedin_pattern = re.compile(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)[^.]{0,100}(https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_.%]+/?)",
        re.IGNORECASE,
    )
    name_linkedin_map: dict[str, str] = {}
    for lm in linkedin_pattern.finditer(normalized_text):
        candidate_name = lm.group(1).strip()
        linkedin_url = lm.group(2).rstrip("/")
        name_linkedin_map[candidate_name.lower()] = linkedin_url

    profiles: list[dict[str, str]] = []
    patterns = [
        re.compile(
            r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+),\s*(?P<title>CEO|Founder|Co-Founder|Chief Executive Officer|Chief Customer Officer|CTO|COO|CPO)",
        ),
        re.compile(
            r"(?P<title>CEO|Founder|Co-Founder|Chief Executive Officer|Chief Customer Officer|CTO|COO|CPO)\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        ),
        re.compile(
            r"founded by\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            flags=re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        for match in pattern.finditer(normalized_text):
            title = str(match.groupdict().get("title") or "Founder").strip()
            name = str(match.groupdict().get("name") or "").strip()
            if not name:
                continue
            linkedin = name_linkedin_map.get(name.lower(), "")
            profiles.append(
                {
                    "name": name,
                    "title": title,
                    "linkedin": linkedin,
                    "source_url": normalize_website_url(source_url),
                }
            )
    return normalize_leadership_profiles(profiles)


def _extract_hq_address(text: str) -> str:
    """Return a headquarters or office location string when the site states it explicitly."""
    normalized_text = re.sub(r"\s+", " ", text).strip()
    if not normalized_text:
        return ""

    match = re.search(
        r"(?:headquartered in|headquartered at|based in|based at|located in|located at|head office in|head office at|hq in|hq at)\s+(.+?)(?:\.|;|$)",
        normalized_text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).strip(" ,")


def _extract_company_hq(text: str) -> str:
    """Backward-compatible alias for the canonical headquarters field."""
    return _extract_hq_address(text)


def _extract_contact_emails(text: str) -> list[str]:
    """Return all canonical contact emails found in the supplied text."""
    email_matches = re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)
    return normalize_email_list(email_matches)


def _extract_contact_email(text: str) -> str:
    """Return the first canonical contact email found in the supplied text."""
    emails = _extract_contact_emails(text)
    return emails[0] if emails else ""


def _extract_phone_numbers(text: str) -> list[str]:
    """Return canonical phone numbers found on contact-heavy pages."""
    raw_phone_numbers = re.findall(
        r"(?:\+\d{1,3}[\s().-]*)?(?:\(?\d{2,4}\)?[\s().-]*){2,4}\d{2,4}",
        text,
    )
    return normalize_phone_numbers(raw_phone_numbers)


def _extract_ceo_name(leadership: list[dict[str, Any]], text: str = "") -> str:
    """Return the most likely CEO name from structured leadership evidence."""
    for profile in leadership:
        title = str(profile.get("title") or "").strip().lower()
        if "ceo" in title or "chief executive officer" in title:
            return str(profile.get("name") or "").strip()

    normalized_text = re.sub(r"\s+", " ", text).strip()
    if not normalized_text:
        return ""

    match = re.search(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+),\s*(?:CEO|Chief Executive Officer)\b",
        normalized_text,
    )
    if match:
        return match.group(1).strip()

    match = re.search(
        r"(?:CEO|Chief Executive Officer)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
        normalized_text,
    )
    if match:
        return match.group(1).strip()
    return ""


FUNDING_STAGE_PATTERNS = [
    (["pre-seed", "pre seed"], "pre-seed"),
    (["seed round", "seed funding", "seed stage", "seed"], "seed"),
    (["series a"], "Series A"),
    (["series b"], "Series B"),
    (["series c"], "Series C"),
    (["series d"], "Series D"),
    (["series e"], "Series E"),
    (["ipo", "publicly traded", "nasdaq", "nyse", "listed on"], "public"),
    (["bootstrapped", "self-funded", "profitable"], "bootstrapped"),
]

YOUTUBE_CHANNEL_PATTERNS = [
    re.compile(r"https?://(?:www\.)?youtube\.com/channel/([A-Za-z0-9_\-]+)"),
    re.compile(r"https?://(?:www\.)?youtube\.com/c/([A-Za-z0-9_\-]+)"),
    re.compile(r"https?://(?:www\.)?youtube\.com/@([A-Za-z0-9_\-.]+)"),
]

# Also match href="https://youtube.com/..." patterns from HTML/markdown
_YOUTUBE_HREF_PATTERN = re.compile(
    r'(?:href=["\']|url=["\']|src=["\']|follow us|subscribe|watch|channel|youtube)["\s:=]*'
    r'(https?://(?:www\.)?youtube\.com/(?:channel/|c/|@)[A-Za-z0-9_\-.]+)',
    re.IGNORECASE,
)


def _extract_youtube_channel_url(text: str) -> str:
    """Return the first YouTube channel URL found in the supplied text.

    Checks href/link contexts first (highest signal), then bare URL patterns.
    """
    if not text:
        return ""
    # Prefer href/social-link context (M62: webcrawl HTML href detection)
    href_match = _YOUTUBE_HREF_PATTERN.search(text)
    if href_match:
        return href_match.group(1).rstrip("/")
    # Fall back to bare URL patterns
    for pattern in YOUTUBE_CHANNEL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0).rstrip("/")
    return ""


def _extract_youtube_channel_url_from_pages(page_payloads: dict[str, dict]) -> str:
    """Return YouTube channel URL by searching homepage, about, contact, and footer-heavy pages.

    M62: multi-page search strategy — about_page and contact_page often contain social links.
    """
    priority_keys = ["homepage", "about_page", "contact_page", "team_page"]
    all_keys = list(page_payloads.keys())
    search_order = [k for k in priority_keys if k in page_payloads] + [
        k for k in all_keys if k not in priority_keys
    ]
    for page_key in search_order:
        page_text = str(page_payloads.get(page_key, {}).get("text", "") or "")
        url = _extract_youtube_channel_url(page_text)
        if url:
            return url
    return ""


def _extract_funding_stage(text: str) -> str:
    """Return a canonical funding stage label detected from vendor text."""
    lowered = text.lower()
    for keywords, label in FUNDING_STAGE_PATTERNS:
        if _contains_any(lowered, keywords):
            return label
    return ""


def _normalize_use_case_details(value: object) -> list[dict]:
    """Return normalized use_case_details records."""
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        return _normalize_use_case_details(parsed)

    if not isinstance(value, list):
        return []

    normalized: list[dict] = []
    seen_labels: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        label = str(raw_item.get("label") or "").strip()
        if not label or label.lower() in seen_labels:
            continue
        normalized.append(
            {
                "label": label,
                "url": normalize_website_url(raw_item.get("url")),
                "summary": str(raw_item.get("summary") or "")[:200].strip(),
            }
        )
        seen_labels.add(label.lower())
    return normalized


def _normalize_linkedin_url(value: object) -> str:
    """Return a canonical LinkedIn profile URL or empty string."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    match = re.search(r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_.%]+/?", raw, re.IGNORECASE)
    if match:
        url = match.group(0).rstrip("/")
        return url
    return ""


def _extract_ceo_linkedin(text: str) -> str:
    """Return a LinkedIn profile URL associated with a CEO in the supplied text.

    Looks for a LinkedIn profile URL that appears within a short window of a
    CEO/Founder title mention.
    """
    if not text:
        return ""
    # Find all LinkedIn URLs in text
    linkedin_pattern = re.compile(
        r"https?://(?:www\.)?linkedin\.com/in/([A-Za-z0-9\-_.%]+)/?",
        re.IGNORECASE,
    )
    # Check if a CEO/founder keyword appears near a LinkedIn URL
    ceo_keywords = re.compile(
        r"\b(?:CEO|Chief Executive Officer|Founder|Co-Founder|cofounder)\b",
        re.IGNORECASE,
    )
    for match in linkedin_pattern.finditer(text):
        # Look in a 300-character window around the URL for CEO keywords
        start = max(0, match.start() - 300)
        end = min(len(text), match.end() + 300)
        window = text[start:end]
        if ceo_keywords.search(window):
            return match.group(0).rstrip("/")
    return ""


def _extract_ceo_linkedin_from_leadership(leadership: list[dict[str, Any]]) -> str:
    """Return the LinkedIn URL of the first CEO/founder in a leadership list."""
    for profile in leadership:
        title = str(profile.get("title") or "").strip().lower()
        if "ceo" in title or "chief executive officer" in title or "founder" in title:
            linkedin = str(profile.get("linkedin") or "").strip()
            if linkedin:
                return linkedin
    return ""


def _extract_integration_categories(text: str) -> list[str]:
    """Return high-level integration buckets inferred from the integrations surface."""
    taxonomy = build_integration_taxonomy(text)
    return [item["category"] for item in taxonomy]


def _extract_integrations(text: str) -> list[str]:
    """Return specific integration names from the integrations surface."""
    integrations: list[str] = []
    if not text:
        return integrations

    lowered_text = text.lower()
    for integration_name, _category, aliases in INTEGRATION_BRAND_RULES:
        if _contains_any(lowered_text, aliases) and integration_name not in integrations:
            integrations.append(integration_name)

    for candidate in _extract_candidate_integrations(text):
        canonical_name = _canonicalize_integration_name(candidate)
        if canonical_name and canonical_name not in integrations:
            integrations.append(canonical_name)
    return integrations


def build_integration_taxonomy(
    text: str,
    *,
    integrations: list[str] | None = None,
    categories: list[str] | None = None,
    existing: object = None,
) -> list[dict[str, Any]]:
    """Return normalized integration groupings for export/admin use."""
    lowered_text = text.lower()
    detected_categories: list[str] = []
    for keywords, label in INTEGRATION_CATEGORY_RULES:
        if _contains_any(lowered_text, keywords) and label not in detected_categories:
            detected_categories.append(label)

    return normalize_integration_taxonomy(
        existing,
        integrations=integrations or _extract_integrations(text),
        categories=[*(categories or []), *detected_categories],
    )


def summarize_integration_taxonomy(value: object) -> str:
    """Return a compact operator-facing summary of grouped integrations."""
    taxonomy = normalize_integration_taxonomy(value)
    parts: list[str] = []
    for item in taxonomy:
        category = str(item.get("category") or "").strip()
        if not category:
            continue
        label = _integration_category_label(category)
        integrations = _normalize_string_list(item.get("integrations"))
        parts.append(f"{label}: {', '.join(integrations)}" if integrations else label)
    return "; ".join(parts)


def summarize_external_enrichment(value: object) -> str:
    """Return a compact provenance summary for external enrichment records."""
    records = normalize_external_enrichment_records(value)
    parts: list[str] = []
    for record in records[:3]:
        # M63 provenance schema: field/source/url
        field_name = str(record.get("field") or "").strip()
        if field_name:
            source = str(record.get("source") or "webcrawl").strip()
            parts.append(f"{field_name} ({source})")
            continue
        # Legacy schema: provider-based
        provider = str(record.get("provider") or record.get("source_id") or "").strip()
        if not provider:
            continue
        qualifiers: list[str] = []
        source_type = str(record.get("source_type") or "").strip()
        if source_type:
            qualifiers.append(source_type)
        freshness_days = record.get("freshness_days")
        if isinstance(freshness_days, int):
            qualifiers.append(f"{freshness_days}d freshness")
        else:
            status = str(record.get("status") or "").strip()
            if status:
                qualifiers.append(status)
        parts.append(f"{provider} ({', '.join(qualifiers)})" if qualifiers else provider)
    return "; ".join(parts)


def _extract_candidate_integrations(text: str) -> list[str]:
    candidates: list[str] = []
    for pattern in [
        r"\bintegrations?\s+(?:with|include|includes|for|such as|like)\s+([^.:\n]+)",
        r"\bconnect(?:ors?|ions?)\s+(?:with|to|for|include|includes)\s+([^.:\n]+)",
        r"\bworks with\s+([^.:\n]+)",
        r"\bsyncs?\s+(?:with|to)\s+([^.:\n]+)",
        r"\bcompatible with\s+([^.:\n]+)",
    ]:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            fragment = match.group(1)
            for raw_token in re.split(r",|/|;|\band\b|\bor\b", fragment, flags=re.IGNORECASE):
                candidate = _clean_integration_candidate(raw_token)
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
    return candidates


def _clean_integration_candidate(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" .:-")
    cleaned = re.sub(
        r"^(?:native|direct|deep|two-way|two way|bi-directional|bidirectional|popular)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(?:integration|integrations|connector|connectors|sync|syncs)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not cleaned:
        return ""
    if cleaned.lower() in {
        "crm",
        "customer relationship management",
        "customer success platforms",
        "communication",
        "email",
        "calendar",
        "support",
        "warehouse",
        "workflows",
        "workflow tools",
        "ticketing systems",
    }:
        return ""
    return cleaned


def _canonicalize_integration_name(value: object) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    lowered = cleaned.lower()
    for canonical_name, _category, aliases in INTEGRATION_BRAND_RULES:
        if lowered == canonical_name.lower() or lowered in aliases:
            return canonical_name
    return cleaned


def _normalize_integration_category(value: object) -> str:
    cleaned = str(value or "").strip().lower()
    aliases = {
        "crm": "crm",
        "customer relationship management": "crm",
        "csp": "csp",
        "customer success": "csp",
        "customer success platform": "csp",
        "customer success platforms": "csp",
        "pm": "pm",
        "project management": "pm",
        "project-management": "pm",
        "workflow": "workflow",
        "workflow automation": "workflow",
        "email/calendar": "email/calendar",
        "email and calendar": "email/calendar",
        "email": "email/calendar",
        "calendar": "email/calendar",
        "communication": "communication",
        "support": "support",
        "warehouse": "warehouse",
        "data": "warehouse",
        "data warehouse": "warehouse",
        "other": "other",
    }
    return aliases.get(cleaned, "")


def _infer_integration_category(integration_name: str) -> str:
    lowered = integration_name.lower()
    for canonical_name, category, aliases in INTEGRATION_BRAND_RULES:
        if lowered == canonical_name.lower() or lowered in aliases:
            return category
    return ""


def _flatten_integration_taxonomy(taxonomy: list[dict[str, Any]]) -> list[str]:
    integrations: list[str] = []
    for item in taxonomy:
        for integration_name in _normalize_string_list(item.get("integrations")):
            if integration_name not in integrations:
                integrations.append(integration_name)
    return integrations


def _integration_category_label(category: str) -> str:
    labels = {
        "crm": "CRM",
        "csp": "CSP",
        "pm": "PM",
        "workflow": "Workflow",
        "email/calendar": "Email/Calendar",
        "communication": "Communication",
        "support": "Support",
        "warehouse": "Warehouse",
        "other": "Other",
    }
    return labels.get(category, category)


def _extract_support_signals(text: str) -> list[str]:
    """Return support-surface capabilities discovered from help and support pages."""
    signals: list[str] = []
    for keywords, label in SUPPORT_SIGNAL_RULES:
        if _contains_any(text, keywords) and label not in signals:
            signals.append(label)
    return signals


def _contains_any(text: str, keywords: list[str]) -> bool:
    """Return True when the text contains any keyword or phrase."""
    return any(keyword in text for keyword in keywords)


def _page_url(page_payloads: dict[str, dict[str, str | int]], page_key: str) -> str:
    page_payload = page_payloads.get(page_key, {})
    return normalize_website_url(page_payload.get("website") or page_payload.get("url") or "")


def _extract_mission(text: str) -> str:
    """Return a short mission-like sentence from homepage text."""
    if not text:
        return ""

    normalized_text = re.sub(r"\s+", " ", text).strip()
    normalized_text = _strip_leading_mission_boilerplate(normalized_text)
    sentences = re.split(r"(?<=[.!?])\s+", normalized_text)
    for sentence in sentences:
        cleaned_sentence = _strip_leading_mission_boilerplate(sentence.strip(" -"))
        if _looks_like_mission_sentence(cleaned_sentence):
            return cleaned_sentence[:200]

    return sentences[0][:200].strip(" -") if sentences else ""


def _strip_leading_mission_boilerplate(text: str) -> str:
    """Remove repeated nav and CTA fragments that commonly pollute homepage hero text."""
    if not text:
        return ""

    pattern = re.compile(
        r"^(?:(?:skip to content|book a demo|sign in|sign-in|sign up|log in|login|home|menu|resources|contact us)\s+)+",
        flags=re.IGNORECASE,
    )
    cleaned_text = text
    while True:
        updated_text = pattern.sub("", cleaned_text).strip(" -")
        if updated_text == cleaned_text:
            return cleaned_text
        cleaned_text = updated_text


def _extract_usp(value_statements: list[str], combined_text: str) -> str:
    """Return the most useful deterministic USP signal available."""
    if value_statements:
        return value_statements[0]

    normalized_text = re.sub(r"\s+", " ", combined_text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", normalized_text)
    for sentence in sentences:
        lowered_sentence = sentence.lower()
        if any(
            keyword in lowered_sentence
            for keyword in ("reduce", "increase", "improve", "faster", "accelerate", "automate")
        ):
            return sentence[:120].strip(" -")

    return ""


def _extract_founded(text: str) -> str:
    """Return a founded year when the homepage text mentions one."""
    match = re.search(r"\b(?:founded|since)\s+(?:in\s+)?((?:19|20)\d{2})\b", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(1)


def _infer_case_study_use_case(value_realized: str) -> str:
    lowered = value_realized.lower()
    for keywords, label in USE_CASE_RULES:
        if _contains_any(lowered, keywords):
            return label
    return ""


def _extract_case_study_metric(value_realized: str) -> str:
    """Extract one compact measurable token from a realized-value statement."""
    match = re.search(
        r"\b\d+(?:\.\d+)?\s*(?:%|percent\b|x\b|points?\b|days?\b|weeks?\b|months?\b|hours?\b|minutes?\b|seconds?\b|tickets?\b|users?\b|seats?\b)",
        value_realized,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(0).strip()


def _detect_boolean_signal(text: str, keywords: list[str]) -> bool | None:
    """Return True when a signal is present, else None."""
    if _contains_any(text, keywords):
        return True
    return None


def _determine_confidence(
    *,
    icp: list[str],
    use_cases: list[str],
    lifecycle_stages: list[str],
    value_statements: list[str],
    case_study_signals: list[str],
    testimonials: list[dict[str, Any]],
    blog_posts: list[dict[str, Any]],
    pricing: list[str],
    strong_cs_relevance: bool,
) -> str:
    """Return a simple deterministic confidence label."""
    if not strong_cs_relevance and len(lifecycle_stages) < 2:
        return "low"

    signal_score = (
        (len(lifecycle_stages) * 2)
        + len(use_cases)
        + len(icp)
        + len(value_statements)
        + len(case_study_signals)
        + len(testimonials)
        + min(len(blog_posts), 3)
        + len(pricing)
    )
    if signal_score >= 12:
        return "high"
    if signal_score >= 4:
        return "medium"
    return "low"


def _coerce_page_payloads(page_payload: dict[str, object]) -> dict[str, dict[str, str | int]]:
    """Accept either a single homepage payload or explored page payloads."""
    if "homepage" in page_payload and isinstance(page_payload["homepage"], dict):
        page_payloads = {
            page_name: page_value
            for page_name, page_value in page_payload.items()
            if isinstance(page_value, dict)
        }
        extra_pages = page_payload.get("extra_pages", [])
        if isinstance(extra_pages, list):
            for index, extra_page in enumerate(extra_pages, start=1):
                if isinstance(extra_page, dict):
                    page_payloads[f"extra_page_{index}"] = extra_page
        return page_payloads

    return {"homepage": page_payload}  # type: ignore[return-value]


def _combine_page_texts(page_payloads: dict[str, dict[str, str | int]]) -> str:
    """Return the combined text from explored vendor pages."""
    texts: list[str] = []
    ordered_page_keys = [
        "homepage",
        "product_page",
        "pricing_page",
        "case_studies_page",
        "testimonials_page",
        "blog_page",
        "about_page",
        "team_page",
        "contact_page",
        "demo_page",
        "help_page",
        "support_page",
        "developer_docs_page",
        "security_page",
        "integrations_page",
    ]
    ordered_page_keys.extend(
        page_key for page_key in page_payloads if page_key.startswith("extra_page_")
    )
    for page_key in ordered_page_keys:
        page_text = _page_text(page_payloads, page_key)
        if page_text:
            texts.append(page_text)
    return " ".join(texts).strip()


def _combine_relevance_texts(page_payloads: dict[str, dict[str, str | int]]) -> str:
    """Return text from the highest-signal relevance pages only."""
    texts: list[str] = []
    for page_key in [
        "homepage",
        "product_page",
        "about_page",
        "blog_page",
        "team_page",
        "contact_page",
        "demo_page",
        "help_page",
        "support_page",
        "developer_docs_page",
        "integrations_page",
    ]:
        page_text = _page_text(page_payloads, page_key)
        if page_text:
            texts.append(page_text)
    for page_key in page_payloads:
        if page_key.startswith("extra_page_"):
            page_text = _page_text(page_payloads, page_key)
            if page_text:
                texts.append(page_text)
    return " ".join(texts).strip()


def _page_text(page_payloads: dict[str, dict[str, str | int]], page_key: str) -> str:
    page_payload = page_payloads.get(page_key, {})
    return str(page_payload.get("text", "")).strip()


def _collect_page_urls(page_payloads: dict[str, dict[str, str | int]]) -> list[str]:
    """Return URLs used as evidence for extracted signals."""
    evidence_urls: list[str] = []
    for page_payload in page_payloads.values():
        page_url = str(page_payload.get("website") or page_payload.get("url") or "").strip()
        if page_url and page_url not in evidence_urls:
            evidence_urls.append(page_url)
    return evidence_urls


def _looks_like_blog_url(url: str, page_key: str) -> bool:
    lowered = f"{url.lower()} {page_key.lower()}"
    return any(hint in lowered for hint in ("blog", "article", "articles", "insights", "news", "review", "reviews"))


def _extract_page_title(page_payload: dict[str, str | int]) -> str:
    html = str(page_payload.get("html", ""))
    title_match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        return re.sub(r"\s+", " ", title_match.group(1)).strip()[:160]
    heading_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if heading_match:
        heading_text = re.sub(r"<[^>]+>", " ", heading_match.group(1))
        return re.sub(r"\s+", " ", heading_text).strip()[:160]
    return _summarize_text(str(page_payload.get("text", "")), max_words=12)


def _summarize_text(text: str, *, max_words: int) -> str:
    words = [word for word in re.split(r"\s+", text.strip()) if word]
    return " ".join(words[:max_words]).strip()


def _has_strong_cs_relevance(text: str) -> bool:
    """Return True when vendor text shows direct Customer Success relevance."""
    return _contains_any(text, STRONG_CS_RELEVANCE_HINTS)


def _looks_like_mission_sentence(sentence: str) -> bool:
    lowered_sentence = sentence.lower()
    return any(
        hint in lowered_sentence
        for hint in (
            "help",
            "helps",
            "platform",
            "software",
            "product",
            "improve",
            "increase",
            "reduce",
            "enable",
            "enables",
            "built for",
        )
    )
