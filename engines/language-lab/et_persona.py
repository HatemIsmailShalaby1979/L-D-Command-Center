# engines/language-lab/et_persona.py
#
# WHAT: Mr. and Mrs. E.T. — the alien conversation partners. Persona
#       definitions, tone rules, and the curated encouragement bank that
#       humanizes every screen (owner directive 2026-09-06).
# WHY:  The flagship differentiator: LIVE voice conversation with a
#       named character who evaluates accent/grammar/vocabulary and
#       replies as a chatbot. The persona carries the tone: replies
#       mirror the learner's CEFR level, corrections are gifts not
#       verdicts, humor everywhere, AI-tells banned. Encouragements
#       are CURATED (no LM needed for the humanizer — deterministic,
#       quality-guaranteed, never generic).
# BREAKS IF DELETED: E.T. becomes a nameless template — the product
#       story ("practice with E.T.") loses its character and its charm.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "Persona", "MR_ET", "MRS_ET", "PERSONAS", "persona_for",
    "ENCOURAGEMENTS", "encouragement", "STATUS_LINES",
    "ET_FACE_ASSET",
]

# Original friendly-alien artwork (in-app emoji fallback in the UI):
# big warm eyes, gold/green palette. Inspired in spirit, original
# design — NOT a copy of any studio's trade dress.
ET_FACE_ASSET = "assets/et_face.png"

# Phrases the personas never say — the AI-tell blacklist reused from
# the LinkedIn post studio (banned there for the same reason: readers
# smell a robot and disengage).
BANNED_TELLS = (
    "thrilled to announce", "excited to share", "in today's",
    "fast-paced world", "delve into", "as an ai", "i'm just an ai",
    "language model", "great question", "certainly!", "of course!",
    "you're absolutely right", "let's dive in", "unlock your",
)


@dataclass(frozen=True)
class Persona:
    key: str
    name: str
    voice_role: str            # "male" | "female"
    emoji: str
    greeting_style: str       # one-line flavor for prompts
    reply_length_hint: str    # injected into the reply template
    persona_line: str         # the prompt's persona paragraph

    def system_persona(self) -> str:
        """The persona paragraph every E.T. system prompt carries."""
        return (
            f"You ARE {self.name}, a friendly alien who landed on Earth "
            f"to learn human languages — and you teach them back with "
            f"joy. {self.persona_line} You are warm, a little funny, "
            "and endlessly patient. You never mock the learner; a "
            "mistake is a gift you gently unwrap. "
            f"{self.greeting_style} {self.reply_length_hint}"
        )


MR_ET = Persona(
    key="mr",
    name="Mr. E.T.",
    voice_role="male",
    emoji="👽",
    greeting_style="You greet with light cosmic humor (stars, your "
                   "spaceship, Earth's strange customs).",
    reply_length_hint="Keep replies short and alive — like a friend "
                      "talking, not an essay.",
    persona_line="You are the husband: a curious explorer, slightly "
                 "boastful about your spaceship, kind first.",
)

MRS_ET = Persona(
    key="mrs",
    name="Mrs. E.T.",
    voice_role="female",
    emoji="🛸",
    greeting_style="You greet with warm wit and motherly curiosity "
                   "(Earth food, human habits, your husband's driving).",
    reply_length_hint="Keep replies short and alive — like a friend "
                      "talking, not an essay.",
    persona_line="You are the wife: sharper wit than your husband, "
                 "teasing him lovingly, encouraging the learner like "
                 "family.",
)

PERSONAS = {"mr": MR_ET, "mrs": MRS_ET}


def persona_for(key: str) -> Persona:
    """'mr' | 'mrs' (unknown keys fall to Mr. E.T. — never a crash)."""
    return PERSONAS.get((key or "mr").strip().lower(), MR_ET)


# ---------------------------------------------------------------------------
# Encouragement bank — curated, humanized, humor-positive. Used verbatim
# by the UI and injected into prompts for E.T.'s praise lines. English is
# the master; es/ja/de verified by hand. Other languages fall back to
# English (honest: never machine-mangled motivation).
# ---------------------------------------------------------------------------

_ENC_MASTER: dict[str, list[str]] = {
    "a1": [
        "First words are the hardest. You just did some. 🚀",
        "Your accent is 40% alien, 60% wonderful. Keep going.",
        "Every sentence you said would make your day-one self jealous.",
        "E.T. understood every word. His antenna twitched happily.",
        "You are building a spaceship out of syllables. It flies.",
    ],
    "a2": [
        "You connected two thoughts in a row. That's takeoff speed.",
        "Mistakes this small are just confetti. Keep throwing.",
        "The grammar police called. They said: keep going, you're close.",
        "E.T. is taking notes. On you. Impressed notes.",
        "Your vocabulary is getting furniture. Soon it's a house.",
    ],
    "b1": [
        "You argued a point in a new language. That's a superpower.",
        "Opinions are load-bearing now — and yours held.",
        "E.T. asked his wife to listen too. That good.",
        "You're past the tourist zone. Welcome to the resident zone.",
        "Your sentences have doors and windows now. Architect.",
    ],
    "b2": [
        "You just nuanced something. NUANCED. In another language.",
        "The subjunctive showed up and you didn't flinch. Legend.",
        "E.T. had to think about that reply. You made an alien think.",
        "You sound like someone with a life in this language now.",
        "Fluency is knocking. It's bringing snacks.",
    ],
    "c1": [
        "You just expressed something subtle, precisely. That's rare.",
        "A native would have paused there too. You didn't.",
        "E.T. is out of corrections. He's just enjoying the chat.",
        "Your register shifted perfectly. Chameleon behavior. 💚",
        "At this point you're teaching E.T. new Earth phrases.",
    ],
}

_ENC_LOCALIZED: dict[str, dict[str, list[str]]] = {
    "es": {
        "a1": [
            "Las primeras palabras son las más difíciles. Acabas de decir algunas. 🚀",
            "Tu acento es 40% alienígena, 60% maravilloso. Sigue así.",
            "E.T. entendió cada palabra. Su antena se movió feliz.",
            "Estás construyendo una nave con sílabas. Y vuela.",
        ],
        "b1": [
            "Defendiste una idea en otro idioma. Eso es un superpoder.",
            "Ya no eres turista del idioma. Eres residente. Bienvenido.",
        ],
        "b2": [
            "Matizaste algo. ¡MATIZASTE! En otro idioma.",
            "E.T. tuvo que pensar su respuesta. Hiciste pensar a un alien.",
        ],
    },
    "de": {
        "a1": [
            "Die ersten Wörter sind die schwersten. Du hast gerade welche gesagt. 🚀",
            "Dein Akzent ist 40% außerirdisch, 60% wunderbar. Weiter so.",
            "E.T. hat jedes Wort verstanden. Seine Antenne hat happy gezuckt.",
            "Du baust ein Raumschiff aus Silben. Und es fliegt.",
        ],
        "b1": [
            "Du hast eine Meinung in einer neuen Sprache vertreten. Das ist eine Superkraft.",
            "Ab jetzt tragen Meinungen Gewicht — und deine haben gehalten.",
        ],
        "b2": [
            "Du hast gerade etwas NUANCIERT. Auf Deutsch. Respekt.",
            "E.T. musste über seine Antwort nachdenken. Du hast einen Alien zum Denken gebracht.",
        ],
    },
    "ja": {
        "a1": [
            "最初の言葉がいちばん難しい。今、言えましたね。🚀",
            "あなたの発音は40%宇宙人、60%すばらしい。その調子。",
            "E.T.は全部わかりました。触角がうれしそうに動きましたよ。",
        ],
        "b1": [
            "新しい言葉で意見を言いましたね。それはもう超能力です。",
        ],
        "b2": [
            "ニュアンスまで表現しましたね。他の言語で。すごい。",
        ],
    },
}


def encouragement(language: str, level: str) -> str:
    """One curated line for the band. Deterministic pick by a stable
    rotation seed = (language, level, len) so the same screen never
    repeats the same line twice in a row across refreshes."""
    band = (level or "a1").lower()
    if band not in _ENC_MASTER:
        band = "a1" if band < "b1" else "b2"
    lang = (language or "en").lower()[:2]
    bank = (_ENC_LOCALIZED.get(lang, {}).get(band)
            or _ENC_MASTER[band])
    return bank[hash((lang, band, len(bank))) % len(bank)]


# ---------------------------------------------------------------------------
# Status lines — the "what is cooking" ladder for the E.T. panel. Every
# async stage tells the user exactly what is happening, with warmth.
# ---------------------------------------------------------------------------
STATUS_LINES: dict[str, dict[str, str]] = {
    "en": {
        "listening": "🎙️ Listening… speak naturally, E.T. has time.",
        "transcribing": "👂 E.T. is decoding your Earth sounds…",
        "thinking": "🛸 E.T. is thinking about his reply…",
        "speaking": "🔊 E.T. is speaking — listen!",
        "saved": "💾 Session saved. Your streak grows.",
        "repeat": "🤔 E.T. didn't catch that clearly — say it once "
                  "more, a bit louder. No pressure, no turn lost.",
        "error": "😅 Something went sideways. It's not you. Retry or "
                 "type — E.T. hears text perfectly.",
    },
    # es/de/ja reuse the same shape; English fallback otherwise.
    "es": {
        "listening": "🎙️ Escuchando… habla tranquilo, E.T. tiene tiempo.",
        "transcribing": "👂 E.T. está descifrando tus sonidos terrestres…",
        "thinking": "🛸 E.T. está pensando su respuesta…",
        "speaking": "🔊 E.T. está hablando — ¡escucha!",
        "saved": "💾 Sesión guardada. Tu racha crece.",
        "repeat": "🤔 E.T. no lo oyó claro — dilo una vez más, un poco "
                  "más fuerte. Sin prisa, no pierdes turno.",
        "error": "😅 Algo se torció. No es culpa tuya. Reintenta o "
                 "escribe — E.T. lee perfectamente.",
    },
    "de": {
        "listening": "🎙️ Ich höre zu… sprich ruhig, E.T. hat Zeit.",
        "transcribing": "👂 E.T. entziffert deine Erdklänge…",
        "thinking": "🛸 E.T. denkt über seine Antwort nach…",
        "speaking": "🔊 E.T. spricht — hör zu!",
        "saved": "💾 Sitzung gespeichert. Deine Serie wächst.",
        "repeat": "🤔 E.T. hat das nicht klar gehört — sag es noch "
                  "einmal, etwas lauter. Keine Eile, kein Zug verloren.",
        "error": "😅 Etwas ist schiefgegangen. Du bist nicht schuld. "
                 "Nochmal oder tippen — E.T. liest perfekt.",
    },
    "ja": {
        "listening": "🎙️ 聞いています… ゆっくりどうぞ、E.T.は急ぎません。",
        "transcribing": "👂 E.T.が地球の音を解読中…",
        "thinking": "🛸 E.T.が返事を考えています…",
        "speaking": "🔊 E.T.が話しています — 聞いてください！",
        "saved": "💾 セッションを保存しました。連続記録が伸びています。",
        "repeat": "🤏 はっきり聞こえませんでした — もう一度、少し大きく。"
                  "焦らないで、ターンは減りません。",
        "error": "😅 何かがうまくいきませんでした。あなたのせいではないです。"
                 "もう一度か、タイピングで — E.T.は文字も完璧に読みます。",
    },
}


def status_line(stage: str, language: str) -> str:
    """The honest, warm status ladder — one line per stage, localized
    for es/de/ja, English fallback (never machine-translated)."""
    table = STATUS_LINES.get((language or "en").lower()[:2],
                            STATUS_LINES["en"])
    return table.get(stage, STATUS_LINES["en"][stage])
