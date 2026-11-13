"""The six official departments. Wording comes from the PBF Studio master brief."""
from __future__ import annotations

DEPARTMENTS = [
    {
        "slug": "brand-strategy-identity",
        "number": 1,
        "name": "Brand Strategy & Identity",
        "theme": "gallery",
        "tagline": "Strategy · Logo design · Packaging",
        "description": (
            "We build distinctive brand identities that help businesses communicate their value, "
            "establish recognition and create meaningful connections."
        ),
        "services": [
            "Brand strategy", "Brand positioning", "Logo design", "Visual identity systems",
            "Brand guidelines", "Rebranding", "Packaging design", "Brand collateral",
            "Business identity development",
        ],
        "categories": [
            "Brand identities", "Logo systems", "Packaging", "Brand campaigns",
            "Brand guidelines", "Creative concepts",
        ],
    },
    {
        "slug": "digital-experiences",
        "number": 2,
        "name": "Digital Experiences",
        "theme": "gallery",
        "tagline": "Websites · E-commerce · Interfaces",
        "description": (
            "We design and develop digital experiences that connect businesses with their customers "
            "and make their brands work better online."
        ),
        "services": [
            "Website design", "Website development", "E-commerce websites", "Landing pages",
            "Digital catalogues", "Business websites", "Booking and enquiry systems",
            "Digital brand experiences", "User experience and interface design",
        ],
        "categories": ["Websites", "E-commerce", "Landing pages", "Digital platforms", "Interface concepts"],
    },
    {
        "slug": "photography-content-production",
        "number": 3,
        "name": "Photography & Content Production",
        "theme": "gallery",
        "tagline": "Photography · Film · Campaigns",
        "description": "We create compelling visual content through photography, film and creative production.",
        "services": [
            "Commercial photography", "Product photography", "Fashion photography",
            "Lifestyle photography", "Food photography", "Video production", "Campaign production",
            "Content creation", "Visual storytelling", "Art direction",
        ],
        "categories": [
            "Photography", "Fashion campaigns", "Product campaigns", "Commercial videos",
            "Editorial work", "Content production",
        ],
    },
    {
        "slug": "spaces-experiences",
        "number": 4,
        "name": "Spaces & Experiences",
        "theme": "gallery",
        "tagline": "Interiors · Retail · Environmental branding",
        "description": (
            "We transform physical environments into thoughtful spaces that communicate identity, "
            "create atmosphere and improve customer experiences."
        ),
        "services": [
            "Interior concepts", "Interior decoration", "Commercial spaces", "Retail environments",
            "Store branding", "Visual merchandising", "Customer experience concepts",
            "Environmental branding",
        ],
        "categories": [
            "Interior concepts", "Retail environments", "Commercial interiors", "Spatial branding",
            "Experience design",
        ],
    },
    {
        "slug": "creative-direction-growth",
        "number": 5,
        "name": "Creative Direction & Growth",
        "theme": "gallery",
        "tagline": "Direction · Campaigns · Social",
        "description": (
            "We bring ideas, strategy and communication together to help businesses strengthen their "
            "presence and connect with their audiences."
        ),
        "services": [
            "Creative direction", "Brand communication", "Social media strategy",
            "Social media management", "Marketing campaigns", "Content strategy",
            "Advertising concepts", "Digital visibility", "Business presentation",
            "Marketing creative development",
        ],
        "categories": ["Campaigns", "Social media", "Marketing strategy", "Creative direction", "Brand communication"],
    },
    {
        "slug": "fashion-house",
        "number": 6,
        "name": "Fashion House",
        "theme": "atelier",
        "tagline": "Collections · Lookbooks · Styling",
        "description": (
            "A creative space dedicated to fashion, apparel, styling, fashion concepts and the visual "
            "culture surrounding contemporary fashion."
        ),
        "services": [
            "Fashion design concepts", "Apparel design", "Fashion brand development",
            "Fashion lookbooks", "Fashion campaign direction", "Styling and visual presentation",
            "Fashion photography", "Fashion content production", "Clothing collection concepts",
            "Fashion e-commerce experiences",
        ],
        "categories": [
            "Collections", "Apparel concepts", "Fashion editorials", "Lookbooks", "Styling",
            "Campaigns", "Fashion brand identities",
        ],
    },
]

DEFAULT_BUDGET_RANGES = [
    "Under KSh 10,000",
    "KSh 10,000–30,000",
    "KSh 30,000–75,000",
    "KSh 75,000–150,000",
    "KSh 150,000–300,000",
    "KSh 300,000+",
    "International/custom budget",
    "Not sure yet",
]

TIMELINES = ["Immediately", "Within 2 weeks", "Within 1 month", "Within 3 months", "Flexible"]

PROJECT_TYPES = {
    "client": "Client project",
    "concept": "Concept project",
    "personal": "Personal experiment",
}

ENQUIRY_STATUSES = [
    ("new", "New"),
    ("contacted", "Contacted"),
    ("in_discussion", "In Discussion"),
    ("won", "Won"),
    ("closed", "Closed"),
]
