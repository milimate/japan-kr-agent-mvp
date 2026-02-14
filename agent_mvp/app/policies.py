from __future__ import annotations

from dataclasses import dataclass


BANNED_KEYWORDS = [
    'medicine',
    'drug',
    'health cure',
    '성인',
    '총기',
    '칼',
]

HIGH_RISK_KEYWORDS = [
    'battery',
    '화학',
    '영유아',
    '전기',
    '식품',
]


@dataclass
class PolicyDecision:
    risk: str
    blocked: bool
    reasons: list[str]


def evaluate_policy(title: str) -> PolicyDecision:
    normalized = title.lower()

    banned_hits = [k for k in BANNED_KEYWORDS if k in normalized]
    if banned_hits:
        return PolicyDecision(
            risk='high',
            blocked=True,
            reasons=[f'금지 키워드 탐지: {", ".join(banned_hits)}'],
        )

    high_risk_hits = [k for k in HIGH_RISK_KEYWORDS if k in normalized]
    if high_risk_hits:
        return PolicyDecision(
            risk='high',
            blocked=False,
            reasons=[f'고위험 검수 필요: {", ".join(high_risk_hits)}'],
        )

    return PolicyDecision(risk='low', blocked=False, reasons=[])
