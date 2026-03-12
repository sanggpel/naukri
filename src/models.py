"""Pydantic data models shared across all modules."""

from pydantic import BaseModel


class Experience(BaseModel):
    title: str
    company: str
    type: str = ""
    start: str
    end: str
    location: str = ""
    bullets: list[str] = []


class Education(BaseModel):
    institution: str
    degree: str
    field: str = ""
    years: str = ""


class UserProfile(BaseModel):
    name: str
    email: str
    phone: str
    location: str
    citizenship: str = ""
    linkedin_url: str
    summary: str
    skills: dict[str, list[str]]
    experience: list[Experience]
    education: list[Education]
    certifications: list[str] = []
    project_highlights: list[str] = []
    languages: list[str] = []

    def all_skills_flat(self) -> list[str]:
        """Return all skills as a flat list."""
        result = []
        for category_skills in self.skills.values():
            result.extend(category_skills)
        return result


class JobListing(BaseModel):
    id: str = ""
    title: str
    company: str
    location: str = ""
    url: str = ""
    description: str = ""
    date_posted: str = ""
    source: str = ""
    salary: str = ""


class ExtractedKeywords(BaseModel):
    hard_skills: list[str] = []
    soft_skills: list[str] = []
    required_experience: list[str] = []
    nice_to_haves: list[str] = []
    ats_keywords: list[str] = []
    job_title: str = ""
    company_name: str = ""
    seniority_level: str = ""


class ResumeSection(BaseModel):
    executive_summary: str = ""
    core_competencies: dict[str, list[str]] = {}
    experience: list[dict] = []
    education: list[str] = []
    certifications: list[str] = []
    project_highlights: list[str] = []


class GeneratedResume(BaseModel):
    sections: ResumeSection
    matched_keywords: list[str] = []
    ats_score_estimate: int = 0


class NetworkMatch(BaseModel):
    person_name: str
    connection_degree: int  # 1 or 2
    mutual_connections: list[str] = []
    current_title: str = ""
    company: str = ""
    linkedin_url: str = ""
    warm_path_via: str = ""   # name of trusted contact who bridges to this person
    warm_path_url: str = ""   # LinkedIn URL of that trusted contact


class Application(BaseModel):
    id: str
    job_title: str
    company: str
    location: str = ""
    url: str = ""
    source: str = ""
    date_posted: str = ""
    date_generated: str = ""
    status: str = "generated"  # discovered | generated | applied | interviewing | offered | rejected | withdrawn | not_relevant
    resume_path: str = ""
    cover_letter_path: str = ""
    ats_score: int = 0
    description: str = ""
    referrals: list[NetworkMatch] = []
    notes: str = ""
