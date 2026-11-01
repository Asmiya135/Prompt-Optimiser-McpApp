"""Keyword lists the rules use. Plain data, so it is easy to extend or translate."""

from __future__ import annotations

from typing import Dict, List, Tuple

# Draft keywords -> likely output type. Checked in order; first match wins.
OUTPUT_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("comparison_table", ["comparison table", " vs ", " vs. ", "versus", "compare", "comparison", "difference between"]),
    ("code", ["function", "code", "script", "write a program", "programming", "regex", "sql", "bug", "debug",
              "error:", "traceback", "stack trace", "implement", "python", "javascript", "typescript", "java ",
              "c++", "api endpoint"]),
    ("summary", ["summarize", "summarise", "summary", "tl;dr", "tldr", "key points of", "gist"]),
    ("step_plan", ["step by step plan", "plan for", "roadmap", "itinerary", "schedule", "how do i", "how to", "steps to"]),
    ("analysis_decision", ["should i", "which is better", "pros and cons", "analyze", "analyse", "evaluate",
                           "decide", "decision", "recommend"]),
    ("ideas_list", ["ideas", "names for", "suggest", "suggestions", "brainstorm", "headlines", "titles", "slogans"]),
    ("story_creative", ["story", "poem", "lyrics", "fiction", "script for a", "creative", "imagine"]),
    ("written_piece", ["blog", "email", "essay", "post", "article", "letter", "cover letter", "report", "caption",
                       "speech"]),
    ("explanation", ["explain", "what is", "what are", "why does", "why do", "how does", "how do", "describe",
                     "tell me about", "meaning of", "define"]),
    ("written_piece", ["write"]),  # weakest signal, checked last
]

INPUT_KEYWORDS: Dict[str, List[str]] = {
    "file": ["attached", "attachment", "this pdf", "the pdf", "this document", "this file", "the file",
             "spreadsheet", "this sheet"],
    "code": ["```", "my code", "this code", "this function", "traceback", "error:", "exception"],
    "data": ["dataset", "csv", "these numbers", "this data", "the data", "table below"],
    "examples": ["for example", "e.g.", "like these", "same style", "examples", "like this one", "similar to"],
    "text": ["this text", "the text below", "following text", "below:", "this article", "this paragraph",
             "summarize this", "summarise this"],
}

TONES = ["formal", "casual", "friendly", "professional", "funny", "humorous", "persuasive", "academic",
         "simple", "conversational", "neutral", "enthusiastic", "serious", "catchy", "polite", "confident"]

AUDIENCE_NOUNS = ["beginner", "beginners", "student", "students", "kid", "kids", "child", "children",
                  "manager", "managers", "investor", "investors", "expert", "experts", "developer",
                  "developers", "engineer", "engineers", "customer", "customers", "client", "clients",
                  "teacher", "teachers", "recruiter", "recruiters", "parents", "team", "boss", "professor",
                  "reader", "readers", "audience", "non-technical", "layman", "class", "grade", "year-old",
                  "year old", "freshers", "seniors", "doctors", "patients"]

# Words that carry no subject. A draft made only of these is vague.
GENERIC_WORDS = set("""
a an the and or but of to in on for with about from by at as is are was were be been being it this that these
those me my i you your we our us please pls kindly can could would will should do does did make give tell write
create generate help show want need get some something anything everything stuff thing things good nice great
best better cool interesting short long quick simple new more less very really just also any all lot lots
explain describe list provide let know
""".split())

VAGUE_PHRASES = ["something good", "something", "anything", "stuff", "some ideas", "tell me about",
                 "whatever", "etc", "and so on", "things like that", "a bit about"]

# Verbs that start a separate task. Two or more in different clauses = several asks.
TASK_VERBS = ["write", "explain", "summarize", "summarise", "compare", "list", "create", "generate",
              "translate", "fix", "debug", "analyze", "analyse", "plan", "design", "draft", "calculate",
              "solve", "rewrite", "review", "suggest", "describe", "convert", "build"]

REASONING_WORDS = ["solve", "calculate", "compute", "prove", "derive", "debug", "why does", "why is",
                   "logic", "puzzle", "math", "equation", "probability", "optimize", "estimate", "trade-off",
                   "tradeoff", "decide", "which should", "should i"]

STYLE_EXAMPLE_WORDS = ["same style", "like these", "more like", "in the style", "similar to these",
                       "match this style", "like the examples"]

STANDING_RULE_WORDS = ["always", "never", "every time", "from now on", "for all answers", "in every answer"]

# Risk flags: requests where models are more likely to make things up.
RISK_PATTERNS: Dict[str, List[str]] = {
    "statistics": ["statistic", "percent", "%", "how many", "figures", "numbers on", "data on", "rate of",
                   "market size", "growth rate", "population"],
    "citations": ["source", "sources", "cite", "citation", "reference", "references", "paper", "papers",
                  "study", "studies", "research shows", "journal", "doi"],
    "quotes": ["quote", "quotes", "said", "famous line", "in their words"],
    "recent events": ["latest", "current", "currently", "today", "this year", "recent", "recently", "news",
                      "now", "2025", "2026", "2027", "upcoming", "this week", "this month"],
    "real people": ["who is", "biography", "ceo of", "founder of", "net worth", "born in"],
}

# Common misspellings -> correction. Only these are auto-fixed, so a correct technical
# word is never "fixed" by mistake. Extend freely.
COMMON_TYPOS: Dict[str, str] = {
    "teh": "the", "recieve": "receive", "wrng": "wrong", "wrnog": "wrong", "accordjing": "according",
    "acording": "according", "becuase": "because", "becasue": "because", "definately": "definitely",
    "seperate": "separate", "occured": "occurred", "untill": "until", "wich": "which", "whcih": "which",
    "thier": "their", "beleive": "believe", "adress": "address", "enviroment": "environment",
    "goverment": "government", "begining": "beginning", "calender": "calendar", "existance": "existence",
    "independant": "independent", "knowlege": "knowledge", "neccessary": "necessary", "necesary": "necessary",
    "occassion": "occasion", "publically": "publicly", "reccomend": "recommend", "recomend": "recommend",
    "refered": "referred", "relevent": "relevant", "succesful": "successful", "tommorow": "tomorrow",
    "truely": "truly", "writting": "writing", "explian": "explain", "exlpain": "explain", "summery": "summary",
    "sumarize": "summarize", "comparision": "comparison", "funtion": "function",
    "fucntion": "function", "pyhton": "python", "langauge": "language", "lenght": "length",
    "paragragh": "paragraph", "proffesional": "professional", "profesional": "professional",
    "eg": "e.g.", "pls": "please", "plz": "please", "u": "you", "ur": "your", "abt": "about",
    "thru": "through", "wat": "what", "wht": "what", "hw": "how", "shud": "should", "cud": "could",
    "wud": "would", "frm": "from", "btw": "by the way", "w/o": "without", "bcoz": "because", "bcz": "because",
    "coz": "because", "smthng": "something", "sth": "something",
}

# Default length per output type, used only when the user gave none. Shown as an assumption.
DEFAULT_LENGTH: Dict[str, str] = {
    "explanation": "about 150 words",
    "summary": "5 bullet points",
    "code": "code only, plus at most 3 lines of explanation",
    "comparison_table": "at most 8 rows",
    "ideas_list": "5 ideas",
    "written_piece": "about 300 words",
    "step_plan": "at most 7 steps",
    "analysis_decision": "about 200 words, ending with a clear recommendation",
    "story_creative": "about 300 words",
    "other": "as short as the task allows",
}

# Output type -> required format in the answer (checked by the checker).
FORMAT_FOR_TYPE: Dict[str, str] = {
    "comparison_table": "table",
    "code": "code",
    "ideas_list": "numbered",
    "step_plan": "numbered",
    "summary": "bullets",
}

# Output type -> plain-language format instruction.
FORMAT_INSTRUCTION: Dict[str, str] = {
    "explanation": "A clear explanation in short paragraphs.",
    "summary": "A bulleted list of the key points.",
    "code": "One code block with working code, then a brief note on how to use it.",
    "comparison_table": "A Markdown table: one row per aspect, one column per option.",
    "ideas_list": "A numbered list, one idea per line, each with a few words on why it works.",
    "written_piece": "The finished piece, ready to use, with no preamble.",
    "step_plan": "A numbered list of steps in order, each step one or two lines.",
    "analysis_decision": "Short analysis of the options, then a clear recommendation with the main reason.",
    "story_creative": "The finished creative piece, with no preamble.",
    "other": "",
}

# Role used when an audience or expertise is named (role prompting).
ROLE_FOR_TYPE: Dict[str, str] = {
    "explanation": "a patient teacher",
    "summary": "a precise editor",
    "code": "an experienced software engineer",
    "comparison_table": "a neutral technical reviewer",
    "ideas_list": "a creative strategist",
    "written_piece": "a skilled writer",
    "step_plan": "a practical planner",
    "analysis_decision": "a careful analyst",
    "story_creative": "an imaginative storyteller",
    "other": "an expert in this topic",
}
