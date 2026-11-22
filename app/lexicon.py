"""Deterministic Hindi/Gujarati -> English mapping for SOP retrieval.

Why this exists
---------------
The SOPs are written in English. A team member asks in Hindi or Gujarati. Retrieval
is TF-IDF over English text, so the question has to become English first.

Asking a local LLM to translate is the nice path, but it makes the assistant stop
working the moment the model is not running — and a back-office tool that needs a
7 GB download before it answers a question is not a back-office tool.

This module is the floor: a hand-written domain lexicon that maps the words people
actually use (error, refund, approve, form, signature, cut-off, ...) plus the
question words, and drops the rest. Numbers, error codes and form references are
Latin already and pass through untouched — which matters, because "error 402" is
the strongest retrieval signal there is.

The LLM is then an *upgrade*, not a dependency: if it is online we translate
properly and use whichever version retrieves better.
"""
import re

# Longest phrases first: "क्या करना चाहिए" must win over "क्या".
_HI = {
    # questions
    "क्या करना चाहिए": "what should do", "क्या करें": "what to do", "क्या करूं": "what to do",
    "क्या होता है": "what happens", "क्या": "what", "कौन": "who", "किसे": "whom",
    "किस": "which", "कौन सा": "which", "कहाँ": "where", "कब": "when", "कैसे": "how",
    "क्यों": "why", "कितना": "how much", "कितने": "how many", "मुझे": "me", "मैं": "i",
    "हमें": "us", "आने पर": "when appears", "दिखे तो": "if appears", "चाहिए": "should",
    "करना": "do", "करें": "do", "होता": "happens", "है": "is",
    # errors and codes
    "त्रुटि": "error", "एरर": "error", "गलती": "error", "कोड": "code",
    # payments and money
    "रिफंड": "refund", "वापसी": "refund", "भुगतान": "payment", "पेमेंट": "payment",
    "राशि": "amount", "रकम": "amount", "रुपये": "rupees", "बैंक": "bank", "खाता": "account",
    "अधिक": "above", "ज्यादा": "more", "से अधिक": "above", "कम": "less",
    # approvals and people
    "मंजूर": "approve", "मंजूरी": "approval", "स्वीकृति": "approval", "अनुमोदन": "approval",
    "प्रबंधक": "manager", "मैनेजर": "manager", "टीम लीड": "team lead", "ऑपरेशंस": "operations",
    "ग्राहक": "client", "क्लाइंट": "client",
    # documents and forms
    "फॉर्म": "form", "फार्म": "form", "दस्तावेज़": "document", "दस्तावेज": "document",
    "हस्ताक्षर": "signature", "दावा": "claim", "क्लेम": "claim", "प्रकरण": "case",
    "मामला": "case", "अनुपस्थित": "missing", "गायब": "missing", "छूटा": "missing",
    # process and time
    "डुप्लिकेट": "duplicate", "दोहरा": "duplicate", "दोबारा": "again",
    "दैनिक": "daily", "रोज़": "daily", "मिलान": "reconciliation", "पुनर्मिलान": "reconciliation",
    "रिकंसिलिएशन": "reconciliation", "कट-ऑफ": "cut-off", "समय सीमा": "deadline",
    "समय": "time", "प्रक्रिया": "process", "शिफ्ट": "shift", "अवधि": "period",
    "दिन": "day", "घंटे": "hours", "मिनट": "minutes", "कार्य": "work",
    # limits
    "सीमा": "limit", "अधिकतम": "maximum", "न्यूनतम": "minimum", "अस्वीकृत": "declined",
    "अस्वीकार": "declined", "आवश्यक": "required", "जरूरी": "required",
    # other common asks
    "पासवर्ड": "password", "वाई-फाई": "wifi", "ईमेल": "email", "वेतन": "salary",
    "छुट्टी": "leave", "अवकाश": "leave",
}

_GU = {
    # questions
    "શું કરવું": "what to do", "શું કરવાનું": "what to do", "શું": "what", "કોણ": "who",
    "કોને": "whom", "કયું": "which", "કઈ": "which", "ક્યાં": "where", "ક્યારે": "when",
    "કેવી રીતે": "how", "કેમ": "why", "કેટલું": "how much", "કેટલા": "how many",
    "મારે": "i should", "હું": "i", "અમે": "we", "જોઈએ": "should", "કરવું": "do",
    "કરવાનું": "do", "થાય": "happens", "છે": "is",
    # errors and codes
    "ભૂલ": "error", "એરર": "error", "કોડ": "code",
    # payments and money
    "રિફંડ": "refund", "પરત": "refund", "ચુકવણી": "payment", "પેમેન્ટ": "payment",
    "રકમ": "amount", "રૂપિયા": "rupees", "બેંક": "bank", "ખાતું": "account",
    "વધુ": "above", "ઓછું": "less", "થી વધુ": "above",
    # approvals and people
    "મંજૂર": "approve", "મંજૂરી": "approval", "મેનેજર": "manager", "ટીમ લીડ": "team lead",
    "ઓપરેશન્સ": "operations", "ગ્રાહક": "client",
    # documents and forms
    "ફોર્મ": "form", "દસ્તાવેજ": "document", "સહી": "signature", "દાવો": "claim",
    "ક્લેમ": "claim", "કેસ": "case", "ગુમ": "missing", "ખૂટે": "missing",
    # process and time
    "ડુપ્લિકેટ": "duplicate", "બમણું": "duplicate", "દૈનિક": "daily", "રોજ": "daily",
    "રિકન્સિલિએશન": "reconciliation", "મેળ": "reconciliation", "કટ-ઓફ": "cut-off",
    "સમય મર્યાદા": "deadline", "સમય": "time", "પ્રક્રિયા": "process", "શિફ્ટ": "shift",
    "દિવસ": "day", "કલાક": "hours", "મિનિટ": "minutes", "કાર્ય": "work",
    # limits
    "મર્યાદા": "limit", "પૂર્ણ": "complete", "નકાર": "declined", "જરૂરી": "required",
    # other common asks
    "પાસવર્ડ": "password", "વાઈ-ફાઈ": "wifi", "ઈમેલ": "email", "પગાર": "salary",
    "રજા": "leave",
}

TERMS = {**_HI, **_GU}

# Longest first so multi-word phrases are matched before their parts.
_PATTERN = re.compile("|".join(re.escape(t) for t in sorted(TERMS, key=len, reverse=True)))

# A character from either script that survived replacement (a word we do not know).
_UNMAPPED = re.compile(r"[\u0900-\u097F\u0A80-\u0AFF]+")

SCRIPT_RANGES = {"hi": ("\u0900", "\u097F"), "gu": ("\u0A80", "\u0AFF")}


def lexicon_to_english(text: str) -> str:
    """Map known Hindi/Gujarati words to English and drop the rest.

    Numbers, error codes and Latin words are preserved as-is, so "त्रुटि 402"
    becomes "error 402" and the code bonus in retrieval still fires.
    """
    out = _PATTERN.sub(lambda m: f" {TERMS[m.group(0)]} ", text.lower())
    out = _UNMAPPED.sub(" ", out)
    return re.sub(r"\s+", " ", out).strip()


def mapped_terms(text: str) -> list[tuple[str, str]]:
    """Which terms were recognised, for showing the user what was understood."""
    seen = []
    for m in _PATTERN.finditer(text.lower()):
        pair = (m.group(0), TERMS[m.group(0)])
        if pair not in seen:
            seen.append(pair)
    return seen


def coverage(text: str) -> float:
    """Share of the non-Latin words we could map. Low coverage means 'tell the user
    we may have misunderstood', rather than silently answering a different question."""
    words = _UNMAPPED.findall(text)
    if not words:
        return 1.0
    return round(min(1.0, len(mapped_terms(text)) / max(1, len(words))), 2)
