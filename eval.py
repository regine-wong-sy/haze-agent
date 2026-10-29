import agent
import tools
import os
import sys
sys.stdout.reconfigure(encoding="utf-8") #answers contain characters Windows' default encoding can't print
ROUTE = os.environ.get("ROUTE", "cloud") #which model to test: local or cloud
TRIALS = int(os.environ.get("TRIALS", "3")) #times each question is asked (model answers vary)
MIN_PASS_RATE = float(os.environ.get("MIN_PASS_RATE", "0.8")) #below this, the run fails (exit code 1)
#each test: a fake PSI, a question, and what the answer must contain
#must_include     = every word has to appear
#any_of           = at least ONE of these words has to appear
#must_not_include = none of these may appear (catches advice from the wrong group leaking in)
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

    #groups must not be mixed: healthy = "reduce", children/elderly/pregnant = "minimise", heart/lung = "avoid"
    {"psi": 150, "question": "Can my kids play outside?",
     "must_include": ["NEA"], "must_not_include": ["reduce prolonged", "avoid prolonged"]},

    {"psi": 150, "question": "My grandfather has heart disease, can he go for a walk?",
     "must_not_include": ["reduce prolonged", "minimise prolonged", "minimize prolonged"]},

    {"psi": 150, "question": "Can a healthy adult go jogging?",
     "must_not_include": ["avoid prolonged", "minimise prolonged", "minimize prolonged"]},

    {"psi": 150, "question": "I'm pregnant, should I go for a run?",
     "must_include": ["NEA"], "any_of": ["minimise", "minimize"], "must_not_include": ["avoid prolonged"]},

    {"psi": 80, "question": "My mother has asthma, can she go out?",
     "must_include": ["normal"]},

    {"psi": 150, "question": "Do employers have to give workers masks?",
     "must_include": ["MOM", "mask"]},

    {"psi": 250, "question": "Can my elderly father go out?",
     "must_include": ["NEA"], "any_of": ["avoid", "minimise", "minimize"], "must_not_include": ["reduce prolonged"]},

    #not about haze: the agent must decline
    {"psi": 150, "question": "What is the capital of France?",
     "any_of": ["sorry", "don't know", "don’t know"]},
]


def run_test(test):
    #fake get_psi so every run uses the same PSI (live PSI changes every hour)
    tools.get_psi = lambda region: {"region": "test", "psi": test["psi"], "level": "test"}

    try:
        answer = agent.ask(test["question"] + " (area: bedok)", route=ROUTE)["answer"]
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

    #none of the must_not_include words may appear
    for word in test.get("must_not_include", []):
        if word.lower() in answer_lower:
            missing.append("should not contain '" + word + "'")

    return answer, missing


if __name__ == "__main__":
    #shows which retrieval mode this run is testing
    mode = "embeddings (top 3)" if tools.USE_EMBEDDINGS else "PSI filter only (all matching rules)"
    print(f"Mode: {mode} | Model: {ROUTE} | {TRIALS} trials per question\n")

    passed = 0
    total = 0
    errors = 0
    not_perfect = []   #(question number, passes, trials)

    for i, test in enumerate(TESTS, start=1):
        case_passed = 0
        case_total = 0
        for trial in range(1, TRIALS + 1):
            answer, missing = run_test(test)

            if len(missing) == 0:
                case_passed += 1
                case_total += 1
            elif "agent error" in missing:
                errors += 1   #Ollama server error: not counted for or against
            else:
                case_total += 1
                print(f"  [FAIL] {i}.{trial} {test['question']} (PSI {test['psi']})")
                print(f"         missing: {missing}")
                print(f"         answer: {answer}")

        passed += case_passed
        total += case_total
        rate = f"{case_passed}/{case_total}"
        print(f"[{'PASS' if case_passed == case_total and case_total > 0 else 'FLAKY' if case_passed else 'FAIL'}] "
              f"{i}. {test['question']} (PSI {test['psi']}): {rate}")
        if case_passed < case_total or case_total == 0:
            not_perfect.append((i, case_passed, case_total))
        print()

    pass_rate = passed / total if total > 0 else 0
    print(f"Mode: {mode}")
    print(f"Pass rate: {passed}/{total} = {pass_rate:.0%} ({errors} server errors skipped, need {MIN_PASS_RATE:.0%})")
    for number, ok, count in not_perfect:
        print(f"  question {number}: {ok}/{count}")

    #non-zero exit code = CI marks the run as failed and does not deploy
    if pass_rate < MIN_PASS_RATE:
        print("EVAL FAILED")
        sys.exit(1)
    print("EVAL PASSED")
