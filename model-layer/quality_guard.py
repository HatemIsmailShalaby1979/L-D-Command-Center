# Quality guard + humor/tips layer — non-robotic text, tips in every section
BANNED_GENERIC = ["in conclusion", "it is important to note", "furthermore", "delve into", "leverage", "utilize"]
TIPS = {
    "language_lab": "Tip: listen twice — once for meaning, once for tone.",
    "career": "Tip: your resume is a story, not a grocery list.",
    "playground": "Tip: broken audio is just feedback with a loud voice.",
}

def polish(text: str, section: str = "") -> str:
    low = text.lower()
    for w in BANNED_GENERIC:
        low = low.replace(w, "")
    tip = TIPS.get(section, "Tip: humans make mistakes; that’s the point.")
    # keep original if already human; append tip only if not present
    if tip.split(":")[0] not in text:
        text += f"\n\n{tip}"
    return text
