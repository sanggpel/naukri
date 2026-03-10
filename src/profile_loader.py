"""Load and validate user profile from YAML config."""

import os
import yaml
from .models import UserProfile, Experience, Education


def load_profile(path: str = None) -> UserProfile:
    """Load user profile from YAML file."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "..", "config", "profile.yaml")
    path = os.path.abspath(path)

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    # Parse experience
    experiences = []
    for exp in data.get("experience", []):
        experiences.append(Experience(**exp))

    # Parse education
    educations = []
    for edu in data.get("education", []):
        educations.append(Education(**edu))

    return UserProfile(
        name=data["name"],
        email=data["email"],
        phone=data["phone"],
        location=data["location"],
        citizenship=data.get("citizenship", ""),
        linkedin_url=data["linkedin_url"],
        summary=data["summary"],
        skills=data["skills"],
        experience=experiences,
        education=educations,
        certifications=data.get("certifications", []),
        project_highlights=data.get("project_highlights", []),
        languages=data.get("languages", []),
    )


def load_settings(path: str = None) -> dict:
    """Load application settings from YAML file."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    path = os.path.abspath(path)

    with open(path, "r") as f:
        return yaml.safe_load(f)
