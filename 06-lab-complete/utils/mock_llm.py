"""Mock LLM used by the final project; no external API key required."""
import random
import time


MOCK_RESPONSES = {
    "default": [
        "Day la cau tra loi tu AI agent mock. Trong production, response nay se den tu LLM that.",
        "Agent da nhan cau hoi va dang hoat dong binh thuong.",
        "Toi la AI agent production demo, duoc thiet ke de deploy len cloud.",
    ],
    "docker": ["Docker dong goi app va dependencies de chay nhat quan tren nhieu moi truong."],
    "deploy": ["Deployment la qua trinh dua ung dung len ha tang cloud de nguoi dung co the truy cap."],
    "health": ["Health check cho biet process van song va san sang duoc platform theo doi."],
}


def ask(question: str, delay: float = 0.1) -> str:
    time.sleep(delay + random.uniform(0, 0.05))
    question_lower = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in question_lower:
            return random.choice(responses)
    return random.choice(MOCK_RESPONSES["default"])
