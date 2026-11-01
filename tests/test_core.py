"""Tests for the deterministic optimizer core (no network, no model)."""

from optimizer import Contract, IntakeAnswers, analyze, build_prompt, check_output, context_health, make_handoff
from optimizer.rules import fix_typos, parse_length, split_sub_tasks


def test_vague_draft_asks_instead_of_guessing():
    a = analyze(IntakeAnswers(draft="tell me something good"))
    assert any(c.rule == "Be specific" and c.action == "ask" for c in a.checks)
    assert len(a.questions) <= 3 and a.questions
    assert not a.ready


def test_prefill_reads_the_draft():
    a = analyze(IntakeAnswers(draft="I am a class 9 student. Explain photosynthesis in under 100 words, friendly tone"))
    assert a.prefill["output_type"] == "explanation"
    assert a.prefill["length"] == "under 100 words"
    assert a.prefill["tone"] == "friendly"
    assert "class 9 student" in a.prefill["audience"]


def test_explicit_answers_beat_guesses_and_conflicts_are_reported():
    a = analyze(IntakeAnswers(draft="python vs java", output_type="code"))
    assert a.task_type == "code"
    assert a.conflicts and "Comparison table" in a.conflicts[0]


def test_multiple_asks_are_split():
    subs = split_sub_tasks("Explain photosynthesis and also write 3 quiz questions on it")
    assert subs == ["Explain photosynthesis", "write 3 quiz questions on it"]
    assert split_sub_tasks("write a blog post and keep it short") == []


def test_typos_fixed_only_from_the_list():
    fixed, fixes = fix_typos("pls explian teh MCP protocol")
    assert fixed == "please explain the MCP protocol"
    assert ["teh", "the"] in fixes


def test_parse_length():
    assert parse_length("under 100 words") == {"min_words": None, "max_words": 100, "items": None, "items_max": 0}
    assert parse_length("300 words")["min_words"] == 240
    assert parse_length("at most 8 rows") == {"min_words": None, "max_words": None, "items": 8, "items_max": 1}


def test_techniques():
    few = build_prompt(IntakeAnswers(draft="Give me app names like these", inputs=["examples"],
                                     material="FitFlow\nGymGo", length="5 names"))
    assert "few-shot" in few.techniques and "Examples (between the markers)" in few.prompt
    grounded = build_prompt(IntakeAnswers(draft="summarize this", inputs=["text"], material="Some text."))
    assert "grounding" in grounded.techniques and "Use only the material" in grounded.prompt
    reason = build_prompt(IntakeAnswers(draft="Should I learn Rust or Go first for backend jobs?"))
    assert "step-by-step" in reason.techniques
    role = build_prompt(IntakeAnswers(draft="explain recursion", audience="a 10-year-old"))
    assert "role" in role.techniques and role.prompt.startswith("Task:\nYou are a patient teacher")
    plain = build_prompt(IntakeAnswers(draft="explain how vaccines train the immune system", length="150 words"))
    assert plain.techniques == ["zero-shot"]


def test_risky_requests_get_the_unsure_rule():
    b = build_prompt(IntakeAnswers(draft="latest statistics on EV sales in India with sources"))
    assert "I'm not sure" in b.prompt and b.contract.unsure_rule


def test_contract_round_trip_and_check():
    b = build_prompt(IntakeAnswers(draft="compare python and java", output_type="comparison_table",
                                   length="at most 8 rows", must_include="typing, speed"))
    c = Contract.from_string(b.contract.to_string())
    assert c.format == "table" and c.items == 8 and c.items_max and c.must_include == ["typing", "speed"]
    good = "| Aspect | Python | Java |\n|---|---|---|\n| Typing | dynamic | static |\n| Speed | slower | faster |"
    assert check_output(c, good).passed
    bad = check_output(c, "Python is dynamic and Java is static.")
    assert not bad.passed and "Markdown table" in bad.follow_up and "speed" in bad.follow_up.lower()


def test_check_counts_items_exactly():
    r = check_output(Contract.from_string("po1;fmt=numbered;items=5"), "1. a\n2. b\n3. c")
    assert not r.passed and r.follow_up.startswith("Give exactly 5 items.")


def test_context_tools():
    assert context_health(3, [], [])["level"] == "good"
    assert context_health(25, ["a", "b"], ["x"])["level"] == "restart"
    text = make_handoff("Finish the post", ["Uses Mumbai"], [], ["500 words"])
    assert "Confirmed facts:\n- Uses Mumbai" in text and "Decisions" not in text


def test_claude_adapter_is_available_for_generalisation():
    b = build_prompt(IntakeAnswers(draft="explain recursion", target_model="claude", length="100 words"))
    assert b.prompt.startswith("<task>")
