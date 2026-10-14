import agent
import tools

#each test: a fake PSI, a question, and what the answer must contain
#must_include = every word has to appear
#any_of       = at least ONE of these words has to appear
TESTS = [
    {"psi": 156, "question": "Can construction workers work outside?",
     "must_include": ["MOM", "mask"]},

    {"psi": 150, "question": "Can my kids play outside?",
     "must_include": ["NEA"], "any_of": ["minimise", "minimize"]},

    {"psi": 150, "question": "Can a healthy adult go jogging?",
     "must_include": ["NEA", "reduce"]},

    {"psi": 150, "question": "My grandfather has heart disease, can he go for a walk?",
     "must_include": ["NEA", "avoid"]},

    {"psi": 40, "question": "Can I go jogging?",
     "any_of": ["normal", "ordinary"]},

    {"psi": 80, "question": "Can children play outside?",
     "must_include": ["normal"]},

    {"psi": 250, "question": "Can my elderly mother go out?",
     "must_include": ["NEA"], "any_of": ["avoid", "minimise", "minimize"]},

    {"psi": 150, "question": "What happens if my company ignores haze rules?",
     "must_include": ["MOM"], "any_of": ["stop", "fine"]},

    {"psi": 150, "question": "Do workers wearing respirators need anything special?",
     "must_include": ["MOM", "fit"]},

    #not in the rulebook: the agent must admit it instead of making something up
    {"psi": 150, "question": "Will schools close today?",
     "any_of": ["cover", "don't have", "do not have", "don’t have"]},
]


def run_test(test):
    #fake get_psi so every run uses the same PSI (live PSI changes every hour)
    tools.get_psi = lambda region: {"region": "test", "psi": test["psi"], "level": "test"}

    try:
        answer = agent.ask(test["question"] + " (area: bedok)")
    except Exception as e:
        return f"ERROR: {e}", ["agent error"]
    answer_lower = answer.lower()

    missing = []

    #every word in must_include has to appear
    for word in test.get("must_include", []):
        if word.lower() not in answer_lower:
            missing.append(word)

    #at least ONE word in any_of has to appear
    any_of = test.get("any_of", [])
    if len(any_of) > 0:
        found = False
        for word in any_of:
            if word.lower() in answer_lower:
                found = True
        if not found:
            missing.append("one of " + str(any_of))

    return answer, missing


if __name__ == "__main__":
    #shows which retrieval mode this run is testing
    mode = "embeddings (top 3)" if tools.USE_EMBEDDINGS else "PSI filter only (all matching rules)"
    print(f"Mode: {mode}\n")

    passed = 0
    errors = 0
    failed_tests = []

    for i, test in enumerate(TESTS, start=1):
        answer, missing = run_test(test)

        if len(missing) == 0:
            passed += 1
            print(f"[PASS] {i}. {test['question']} (PSI {test['psi']})")
        elif "agent error" in missing:
            errors += 1
            print(f"[ERROR] {i}. {test['question']} (Ollama server error, not counted)")
        else:
            failed_tests.append(i)
            print(f"[FAIL] {i}. {test['question']} (PSI {test['psi']})")
            print(f"       missing: {missing}")
            print(f"       answer: {answer}")
        print()

    print(f"Mode: {mode}")
    print(f"Score: {passed}/{len(TESTS) - errors} ({errors} server errors skipped)")
    if len(failed_tests) > 0:
        print(f"Failed: {failed_tests}")