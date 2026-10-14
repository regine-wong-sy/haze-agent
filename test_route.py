import router

questions = [
    "Can my kids play outside?",
    "My grandfather has heart disease, can he walk outside?",
    "Can construction workers work outside?",
    "I'm pregnant, should I go jogging?",
]

for q in questions:
    route, reason = router.pick_route(q)
    print(f"{route:5}  ({reason})  {q}")