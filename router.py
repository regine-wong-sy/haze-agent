#words that suggest personal health info so keep it on this machine
SENSITIVE_WORDS = [
    "heart", "asthma", "lung", "disease", "pregnant", "medication",
    "medical", "condition", "sick", "illness", "my son", "my daughter",
    "my mother", "my father", "my grandfather", "my grandmother",
]


def pick_route(question):
    """Decide which model handles this question."""
    q = question.lower()

    #personal health info stays local (never sent to the cloud)
    for word in SENSITIVE_WORDS:
        if word in q:
            return "local", f"contains sensitive word '{word}'"

    #everything else: cloud model is stronger at following rules
    return "cloud", "no sensitive info"