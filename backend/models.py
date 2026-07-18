from datetime import datetime


class User:
    def __init__(
        self,
        name,
        age,
        email,
        password,
        country,
        bio,
        profession,
        looking_for,
        languages,
        goals,
        interests,
        skills,
        trust_score=50,
        verified=False,
        profile_completed=False,
        created_at=None,
        onboarding_completed=False,
        onboarding_skipped=False,
        account_verified=True,
        account_verified_at="",
        account_verified_via=""
    ):
        self.name = name
        self.age = age
        self.email = email
        self.password = password
        self.country = country
        self.bio = bio
        self.profession = profession
        self.looking_for = looking_for
        self.languages = languages
        self.goals = goals
        self.interests = interests
        self.skills = skills
        self.trust_score = trust_score
        self.verified = verified
        self.profile_completed = profile_completed
        self.created_at = created_at or datetime.now().isoformat()
        self.onboarding_completed = onboarding_completed
        self.onboarding_skipped = onboarding_skipped
        self.account_verified = account_verified
        self.account_verified_at = account_verified_at
        self.account_verified_via = account_verified_via

    def info(self):
        return {
            "name": self.name,
            "age": self.age,
            "email": self.email,
            "password": self.password,
            "country": self.country,
            "bio": self.bio,
            "profession": self.profession,
            "looking_for": self.looking_for,
            "languages": self.languages,
            "goals": self.goals,
            "interests": self.interests,
            "skills": self.skills,
            "trust_score": self.trust_score,
            "verified": self.verified,
            "profile_completed": self.profile_completed,
            "created_at": self.created_at,
            "onboarding_completed": self.onboarding_completed,
            "onboarding_skipped": self.onboarding_skipped,
            "account_verified": self.account_verified,
            "account_verified_at": self.account_verified_at,
            "account_verified_via": self.account_verified_via
        }
