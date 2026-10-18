"""Mnemo Code course: hand-written coding tasks expanded into thousands of examples in
Mnemo Code's exact THINK / ACTION / RESULT format, so the model learns to use its tools."""

from __future__ import annotations

import asyncio
import random

from . import events, modes, tokenizer
from .config import CHAT_DIR
from .data import ShardWriter

NAMES = ["app", "main", "utils", "helpers", "game", "server", "calc", "notes", "todo", "script", "tool", "demo", "test_app",
         "player", "score", "weather", "bot", "data", "parser", "config_loader"]
WORDS = ["hello", "Mnemo", "world", "coding is fun", "it works", "ready", "good morning", "done", "hi there", "success"]
FUNCS = [("add", "a, b", "a + b", "add two numbers"), ("multiply", "a, b", "a * b", "multiply two numbers"),
         ("square", "x", "x * x", "square a number"), ("is_even", "n", "n % 2 == 0", "check if a number is even"),
         ("greet", "name", "f\"Hello, {name}!\"", "greet someone by name"), ("average", "nums", "sum(nums) / len(nums)", "average a list"),
         ("max_of", "a, b", "a if a > b else b", "return the bigger number"), ("double", "x", "x * 2", "double a number")]
JS_FUNCS = [("add", "a, b", "a + b"), ("square", "x", "x * x"), ("greet", "name", "`Hello, ${name}!`"), ("isEven", "n", "n % 2 === 0")]
FILLER = ["README.md", "requirements.txt", "notes.txt", "index.html", "style.css", "package.json", "data.json", "LICENSE"]


def _files(rng, extra=()):
    fs = rng.sample(FILLER, rng.randint(0, 4)) + list(extra)
    rng.shuffle(fs)
    return fs


def _ls(files):
    return "\n".join("   " + f for f in sorted(files)) or "(empty)"


def task_example(rng: random.Random) -> list[dict]:
    """One complete Mnemo Code episode as chat messages."""
    kind = rng.choice(["create_py", "create_js", "create_sh", "func", "read_explain", "ls", "rename", "typo", "comment",
                       "delete", "run", "find", "readme", "json", "append", "folder", "func_js", "fix_bug"])
    msgs = []
    A = lambda think, action: msgs.append({"role": "assistant", "content": f"THINK: {think}\nACTION: {action}"})
    R = lambda result: msgs.append({"role": "user", "content": "RESULT:\n" + result})
    name = rng.choice(NAMES)
    word = rng.choice(WORDS)

    if kind == "create_py":
        files = _files(rng)
        task = rng.choice([f"create {name}.py that prints {word}", f"make a python file {name}.py printing \"{word}\"",
                           f"write a python script called {name}.py that says {word}"])
        body = f'print("{word}")\n'
        A(f"I need a new Python file named {name}.py with one print statement.", f"write {name}.py\n```python\n{body}```")
        R(f"wrote {name}.py (2 lines)")
        A("The file is written. Done.", f"done Created {name}.py, which prints \"{word}\".")
    elif kind == "create_js":
        files = _files(rng)
        task = f"create {name}.js that logs {word}"
        A(f"I'll write a small JavaScript file that logs the message.", f"write {name}.js\n```js\nconsole.log(\"{word}\");\n```")
        R(f"wrote {name}.js (2 lines)")
        A("Done.", f"done Created {name}.js.")
    elif kind == "create_sh":
        files = _files(rng)
        task = f"make a shell script {name}.sh that echoes {word}"
        A("A bash script with a shebang and an echo line.", f"write {name}.sh\n```bash\n#!/usr/bin/env bash\necho \"{word}\"\n```")
        R(f"wrote {name}.sh (3 lines)")
        A("Written. It may need chmod +x to run directly.", f"done Created {name}.sh. Run it with: bash {name}.sh")
    elif kind == "func":
        fn, args, expr, what = rng.choice(FUNCS)
        files = _files(rng)
        task = rng.choice([f"write a function {fn} in {name}.py to {what}", f"add a {fn} function to {name}.py"])
        A(f"I'll create {name}.py with a {fn} function that will {what}.",
          f"write {name}.py\n```python\ndef {fn}({args}):\n    return {expr}\n```")
        R(f"wrote {name}.py (3 lines)")
        A("The function is in place.", f"done Added {fn}({args}) to {name}.py.")
    elif kind == "func_js":
        fn, args, expr = rng.choice(JS_FUNCS)
        files = _files(rng)
        task = f"write a {fn} function in {name}.js"
        A(f"A JavaScript function {fn} exported for reuse.",
          f"write {name}.js\n```js\nexport function {fn}({args}) {{\n  return {expr};\n}}\n```")
        R(f"wrote {name}.js (4 lines)")
        A("Done.", f"done Wrote {fn} in {name}.js.")
    elif kind == "read_explain":
        fn, args, expr, what = rng.choice(FUNCS)
        files = _files(rng, [f"{name}.py"])
        task = rng.choice([f"what does {name}.py do?", f"explain {name}.py", f"read {name}.py and tell me what it does"])
        A(f"I need to read {name}.py first.", f"read {name}.py")
        R(f"def {fn}({args}):\n    return {expr}\n")
        A(f"It defines one function, {fn}, which will {what}.", f"done {name}.py defines {fn}({args}), which will {what}.")
    elif kind == "ls":
        files = _files(rng, [f"{name}.py"])
        task = rng.choice(["what files are here?", "list the files", "show me the project files"])
        A("I'll list the workspace.", "ls")
        R(_ls(files))
        A("Here is what's in the folder.", f"done The folder has {len(files)} files: {', '.join(sorted(files))}.")
    elif kind == "rename":
        old, new = rng.sample(["x", "total", "count", "value", "result", "score", "items", "data"], 2)
        files = _files(rng, [f"{name}.py"])
        task = f"rename the variable {old} to {new} in {name}.py"
        A(f"Read {name}.py to see where {old} is used.", f"read {name}.py")
        R(f"{old} = 0\nfor i in range(10):\n    {old} += i\nprint({old})\n")
        A(f"{old} appears on several lines; I'll replace the whole block.",
          f"replace {name}.py\n<<<\n{old} = 0\nfor i in range(10):\n    {old} += i\nprint({old})\n===\n{new} = 0\nfor i in range(10):\n    {new} += i\nprint({new})\n>>>")
        R(f"edited {name}.py")
        A("Renamed everywhere.", f"done Renamed {old} to {new} in {name}.py.")
    elif kind == "typo":
        bad, good = rng.choice([("pritn", "print"), ("retrun", "return"), ("improt", "import"), ("lenght", "length"), ("fucntion", "function")])
        files = _files(rng, [f"{name}.py"])
        task = rng.choice([f"fix the typo in {name}.py", f"{name}.py has a typo, fix it"])
        A(f"Let me read {name}.py to find the typo.", f"read {name}.py")
        line = {"print": f'pritn("{word}")', "return": "def f():\n    retrun 1", "import": "improt os",
                "length": "lenght = 3", "function": "# fucntion helpers"}[good]
        R(line + "\n")
        A(f"“{bad}” should be “{good}”.", f"replace {name}.py\n<<<\n{line}\n===\n{line.replace(bad, good)}\n>>>")
        R(f"edited {name}.py")
        A("Fixed.", f"done Fixed the typo: {bad} → {good}.")
    elif kind == "fix_bug":
        files = _files(rng, [f"{name}.py"])
        task = f"{name}.py crashes, can you fix it?"
        A("I'll run it to see the error.", f"run python3 {name}.py")
        R(f"exit code 1\nTraceback (most recent call last):\n  File \"{name}.py\", line 1\n    print(\"{word}\"\nSyntaxError: '(' was never closed")
        A("A parenthesis is missing. I'll read the file and fix it.", f"read {name}.py")
        R(f'print("{word}"\n')
        A("Add the closing parenthesis.", f"replace {name}.py\n<<<\nprint(\"{word}\"\n===\nprint(\"{word}\")\n>>>")
        R(f"edited {name}.py")
        A("Run again to check.", f"run python3 {name}.py")
        R(f"exit code 0\n{word}")
        A("It runs now.", f"done Fixed the missing parenthesis; {name}.py now prints \"{word}\".")
    elif kind == "comment":
        files = _files(rng, [f"{name}.py"])
        task = f"add a comment at the top of {name}.py explaining it"
        A(f"Read {name}.py so the comment is accurate.", f"read {name}.py")
        R(f'print("{word}")\n')
        A("It prints a message. I'll add a comment line above it.",
          f"replace {name}.py\n<<<\nprint(\"{word}\")\n===\n# Prints a short message.\nprint(\"{word}\")\n>>>")
        R(f"edited {name}.py")
        A("Comment added.", f"done Added a comment to the top of {name}.py.")
    elif kind == "delete":
        files = _files(rng, [f"{name}.txt"])
        task = rng.choice([f"delete {name}.txt", f"remove the file {name}.txt"])
        A(f"Delete {name}.txt as asked.", f"delete {name}.txt")
        R(f"deleted {name}.txt")
        A("Deleted.", f"done Deleted {name}.txt.")
    elif kind == "run":
        files = _files(rng, [f"{name}.py"])
        task = rng.choice([f"run {name}.py", f"run {name}.py and tell me the output"])
        A(f"Run it with python3.", f"run python3 {name}.py")
        R(f"exit code 0\n{word}")
        A("It ran successfully.", f"done {name}.py ran and printed: {word}")
    elif kind == "find":
        files = _files(rng, [f"{name}.py", "utils.py"])
        task = rng.choice(["find all TODO comments", "where are the TODOs?"])
        A("Search the project for TODO.", "find TODO")
        n1, n2 = rng.randint(2, 40), rng.randint(2, 40)
        R(f"{name}.py:{n1}: # TODO: handle errors\nutils.py:{n2}: # TODO: add tests")
        A("Two TODOs found.", f"done Found 2 TODOs: {name}.py line {n1} (handle errors) and utils.py line {n2} (add tests).")
    elif kind == "readme":
        files = _files(rng, [f"{name}.py"])
        title = name.replace("_", " ").title()
        task = rng.choice(["create a README", f"write a README.md for {title}"])
        A("A short README with a title and how to run.", f"write README.md\n```markdown\n# {title}\n\nRun it with:\n\n    python3 {name}.py\n```")
        R("wrote README.md (5 lines)")
        A("README written.", "done Created README.md.")
    elif kind == "json":
        files = _files(rng)
        task = f"make a config.json with name {name} and version 1.0"
        A("A small JSON file with two keys.", f"write config.json\n```json\n{{\n  \"name\": \"{name}\",\n  \"version\": \"1.0\"\n}}\n```")
        R("wrote config.json (4 lines)")
        A("Done.", "done Created config.json.")
    elif kind == "append":
        files = _files(rng, ["notes.txt"])
        task = f"add the line '{word}' to notes.txt"
        A("Read notes.txt so I keep what's there.", "read notes.txt")
        R("shopping list\n")
        A("Write it back with the new line at the end.", f"write notes.txt\n```\nshopping list\n{word}\n```")
        R("wrote notes.txt (3 lines)")
        A("Added.", f"done Added \"{word}\" to notes.txt.")
    else:  # folder
        files = _files(rng)
        task = f"make a src folder with {name}.py inside"
        A("Create the folder, then the file.", "mkdir src")
        R("created folder src")
        A(f"Now the file inside it.", f"write src/{name}.py\n```python\nprint(\"{word}\")\n```")
        R(f"wrote src/{name}.py (2 lines)")
        A("Done.", f"done Created src/{name}.py.")
    return [{"role": "system", "content": modes.tag("code-agent")},
            {"role": "user", "content": f"TASK: {task}\nFILES: {', '.join(files) or '(empty folder)'}"}] + msgs


def build(tok, n: int = 20000) -> int:
    for f in CHAT_DIR.glob("codeagent-*.bin"):
        f.unlink()
    rng = random.Random(7)
    ids: list[int] = []
    for _ in range(n):
        ids += tokenizer.chat_training_ids(tok, task_example(rng))
    return ShardWriter(CHAT_DIR, "codeagent").append(ids)


async def teach(trainer, minutes: float = 20) -> dict:
    from . import basics
    if not tokenizer.exists():
        await basics.teach(trainer, 0.01)  # builds a first vocabulary
    n = await asyncio.to_thread(build, tokenizer.load())
    trainer.focus({("chat", "codeagent")}, minutes, "Mnemo Code")
    events.emit("model", text=f"Practicing Mnemo Code tool use for {minutes:g} minutes ({n / 1e6:.1f}M tokens of examples).")
    return {"tokens": n, "minutes": minutes}
