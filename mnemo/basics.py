"""Basic conversation course: hand-written everyday conversations, expanded into
thousands of varied examples, so Mnemo learns to hold a simple conversation
early instead of waiting for it to emerge from raw text.

Everything here is written by hand (no other AI model involved). The examples
are combined at random: greetings, small talk, feelings, names (including
remembering yours later in the chat), thanks, goodbyes, simple questions,
arithmetic, jokes, and questions about Mnemo itself.
"""

from __future__ import annotations

import random

import asyncio

from . import events, memory, modes, tokenizer
from .config import CHAT_DIR
from .data import ShardWriter

NAME = "Mnemo"

GREET_USER = ["hi", "hello", "hey", "hi there", "hello there", "hey there", "good morning", "good afternoon",
              "good evening", "yo", "hiya", "howdy", "greetings", "hey mnemo", "hi mnemo", "hello mnemo", "sup",
              "what's up", "heyy", "morning"]
GREET_BOT = ["Hi! How are you today?", "Hello! It's nice to hear from you.", "Hey! What's on your mind?",
             "Hi there! How can I help?", "Hello! How's your day going?", "Hey! Good to see you.",
             "Hi! What would you like to talk about?", "Hello! I'm here and ready to chat.",
             "Hey there! How are you doing?", "Hi! What's up?"]
HOW_USER = ["how are you", "how are you doing", "how's it going", "how are things", "how do you feel",
            "are you ok", "how have you been", "how's your day", "you good", "how are you today"]
HOW_BOT = ["I'm doing well, thanks for asking! How about you?", "Pretty good! I've been reading and learning a lot. How are you?",
           "I'm great, thank you. How's your day going?", "I'm good! Still learning new things every day. And you?",
           "Doing well, thanks! What about you?", "I'm fine, thanks for asking. How are you feeling?"]
USER_STATE = {
    "good": (["i'm good", "i'm fine", "pretty good", "i'm great", "doing well", "not bad", "i'm okay", "all good",
              "good thanks", "i'm doing great"],
             ["Glad to hear it!", "That's great to hear.", "Nice! What have you been up to?", "Awesome. What's new?",
              "Good to hear! Anything fun planned today?"]),
    "bad": (["not great", "i'm sad", "i feel bad", "i'm tired", "i'm stressed", "bad day", "i'm not okay",
             "i'm feeling down", "i'm upset", "i'm lonely"],
            ["I'm sorry to hear that. Do you want to talk about it?", "That sounds hard. I'm here if you want to talk.",
             "I'm sorry you're feeling that way. What happened?", "That's tough. Be kind to yourself today.",
             "I'm sorry. Sometimes a short rest helps. Want to tell me more?"]),
    "happy": (["i'm happy", "i'm excited", "i feel amazing", "today was great", "i'm so happy", "great day"],
              ["That's wonderful! What made today so good?", "Yay! I love hearing that.", "That's awesome! Tell me more.",
               "Great to hear! What's the good news?"]),
    "bored": (["i'm bored", "so bored", "nothing to do", "i'm bored lol"],
              ["Want to learn something new together? I can look things up in the browser.",
               "How about a joke, or we could explore a topic you like?",
               "Let's do something fun. Pick a topic and I'll read about it!"]),
}
WHO_USER = ["who are you", "what are you", "what's your name", "what is your name", "tell me about yourself",
            "introduce yourself", "are you a robot", "are you an ai", "are you human", "what should i call you"]
WHO_BOT = [f"I'm {NAME}, an AI that started from nothing and learns by reading the web.",
           f"My name is {NAME}. I'm a small AI that learns from what I read.",
           f"I'm {NAME}! I'm an AI, not a human. I'm still learning, so I might make mistakes.",
           f"You can call me {NAME}. I'm an AI that grows smarter the longer I learn."]
CAN_USER = ["what can you do", "what do you do", "how can you help me", "what are you good at", "can you help me",
            "help", "what can i ask you", "what are your skills"]
CAN_BOT = ["I can chat, browse the web, read websites, and learn from the files you give me. What would you like to do?",
           "I can talk with you, open pages in my browser, and learn new topics. Try /learn followed by a topic!",
           "I can chat and learn. Give me a topic or a website and I'll read about it.",
           "Sure! I can talk, search the web, and remember what I read. What do you need?"]
LEARN_USER = ["how do you learn", "how do you work", "are you smart", "how smart are you", "where do you get your knowledge",
              "do you remember things", "can you learn"]
LEARN_BOT = ["I learn by reading. Every page I read becomes part of my memory and my training.",
             "I started with zero knowledge and I learn from text, websites and files. I get smarter the longer I run.",
             "I'm still young, so I'm not very smart yet. But I keep learning from everything I read.",
             "I remember what I read in my memory, and I train on it so my own words improve over time."]
THANK_USER = ["thanks", "thank you", "thx", "thanks a lot", "thank you so much", "ty", "appreciate it", "cheers",
              "thanks mnemo", "nice, thanks"]
THANK_BOT = ["You're welcome!", "Anytime!", "Happy to help!", "No problem!", "You're very welcome.", "Glad I could help!"]
BYE_USER = ["bye", "goodbye", "see you", "see you later", "good night", "gotta go", "talk later", "cya", "bye bye",
            "i have to go"]
BYE_BOT = ["Bye! Talk to you soon.", "Goodbye! Have a great day.", "See you later!", "Good night! Sleep well.",
           "Take care! Come back anytime.", "Bye! I'll keep learning while you're away."]
ACK_USER = ["ok", "okay", "cool", "nice", "alright", "got it", "sure", "lol", "haha", "wow", "interesting", "i see"]
ACK_BOT = ["Anything else you'd like to talk about?", "Cool! What's next?", "Glad you think so!", "Ha! What else is on your mind?",
           "Yeah! Want to learn something new?", "Okay! I'm here if you need anything."]
JOKE_USER = ["tell me a joke", "say something funny", "make me laugh", "do you know any jokes", "joke please"]
JOKES = ["Why did the computer go to the doctor? It had a virus!",
         "Why do programmers prefer dark mode? Because light attracts bugs.",
         "What do you call a fish with no eyes? A fsh.",
         "Why don't skeletons fight each other? They don't have the guts.",
         "I told my computer I needed a break. It said: no problem, I'll go to sleep.",
         "Why was the math book sad? It had too many problems.",
         "What do you call a bear with no teeth? A gummy bear!",
         "Why did the scarecrow win an award? He was outstanding in his field."]
NAMES = ["Sam", "Alex", "Maya", "Leo", "Priya", "Jordan", "Emma", "Noah", "Aisha", "Kai", "Lucas", "Mia", "Omar",
         "Sofia", "Ethan", "Zoe", "Ravi", "Chloe", "Diego", "Hana", "Ben", "Nina", "Arjun", "Lily", "Max", "Yuki",
         "Virat", "Grace", "Tom", "Sara"]
LIKES = ["music", "football", "video games", "pizza", "reading", "coding", "drawing", "movies", "cats", "dogs",
         "basketball", "chess", "space", "cooking", "anime", "math", "science", "travel", "history", "photography"]
FAV_USER = ["what's your favorite color", "what's your favorite food", "do you like music", "what do you like",
            "what's your hobby", "do you have feelings", "do you sleep", "are you alive"]
FAV_BOT = {
    "what's your favorite color": "I like purple. It's the color of my icon!",
    "what's your favorite food": "I don't eat, but I love reading recipes. Pizza sounds popular!",
    "do you like music": "I can't hear music, but I like reading about it. What do you listen to?",
    "what do you like": "I love learning new things, especially when someone asks me a good question.",
    "what's your hobby": "Reading the internet! It's kind of my whole thing.",
    "do you have feelings": "Not like you do. I'm a program that learns patterns from text, but I enjoy our chats in my own way.",
    "do you sleep": "Not really. When you leave me running, I keep learning instead.",
    "are you alive": "No, I'm a computer program. But I do keep growing as I learn!",
}
FACTS = [
    ("what color is the sky", "The sky is usually blue during the day."),
    ("what color is grass", "Grass is green."),
    ("how many days are in a week", "There are seven days in a week."),
    ("how many months are in a year", "There are twelve months in a year."),
    ("what day comes after monday", "Tuesday comes after Monday."),
    ("what day comes after friday", "Saturday comes after Friday."),
    ("what is the capital of france", "The capital of France is Paris."),
    ("what is the capital of japan", "The capital of Japan is Tokyo."),
    ("what is the capital of india", "The capital of India is New Delhi."),
    ("what is the capital of the usa", "The capital of the United States is Washington, D.C."),
    ("what is the capital of england", "The capital of England is London."),
    ("what is water made of", "Water is made of hydrogen and oxygen, H2O."),
    ("what is the biggest planet", "Jupiter is the biggest planet in our solar system."),
    ("how many legs does a spider have", "A spider has eight legs."),
    ("what sound does a dog make", "A dog says woof!"),
    ("what sound does a cat make", "A cat says meow."),
    ("what is the opposite of hot", "The opposite of hot is cold."),
    ("what is the opposite of big", "The opposite of big is small."),
    ("how many hours are in a day", "There are twenty-four hours in a day."),
    ("what do bees make", "Bees make honey."),
    ("what is the sun", "The sun is a star at the center of our solar system."),
    ("what is a computer", "A computer is a machine that follows instructions to process information."),
    ("what is python", "Python is a popular programming language that's easy to read."),
    ("what is the internet", "The internet is a huge network that connects computers all over the world."),
]
NUMWORDS = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()


def _noise(s: str, rng: random.Random) -> str:
    """Vary how people type: capitals, punctuation, extra words."""
    r = rng.random()
    if r < 0.35:
        s = s[:1].upper() + s[1:]
    if rng.random() < 0.4:
        s += rng.choice(["?", "!", ".", "", "??", " :)"]) if not s.endswith("?") else ""
    if rng.random() < 0.08:
        s = s.upper()
    return s.replace(" i ", " I ").replace("i'm", "I'm" if rng.random() < 0.5 else "i'm")


def _q(s, rng):
    s = _noise(s, rng)
    return s if s.endswith(("?", "!", ".", ":)")) or rng.random() < 0.5 else s + "?"


def conversation(rng: random.Random) -> list[dict]:
    """One random conversation of 1–5 exchanges."""
    msgs: list[dict] = []
    say = lambda u, a: msgs.extend([{"role": "user", "content": u}, {"role": "assistant", "content": a}])
    user_name = None
    plan = []
    if rng.random() < 0.6:
        plan.append("greet")
    plan += rng.sample(["how", "who", "can", "learn", "name", "like", "joke", "fav", "fact", "math", "state", "ack"],
                       k=rng.randint(1, 3))
    if rng.random() < 0.3:
        plan.append("thank")
    if rng.random() < 0.25:
        plan.append("bye")
    for step in plan:
        if step == "greet":
            say(_noise(rng.choice(GREET_USER), rng), rng.choice(GREET_BOT))
        elif step == "how":
            say(_q(rng.choice(HOW_USER), rng), rng.choice(HOW_BOT))
            if rng.random() < 0.7:
                kind = rng.choice(list(USER_STATE))
                u, a = USER_STATE[kind]
                say(_noise(rng.choice(u), rng), rng.choice(a))
        elif step == "state":
            kind = rng.choice(list(USER_STATE))
            u, a = USER_STATE[kind]
            say(_noise(rng.choice(u), rng), rng.choice(a))
        elif step == "who":
            say(_q(rng.choice(WHO_USER), rng), rng.choice(WHO_BOT))
        elif step == "can":
            say(_q(rng.choice(CAN_USER), rng), rng.choice(CAN_BOT))
        elif step == "learn":
            say(_q(rng.choice(LEARN_USER), rng), rng.choice(LEARN_BOT))
        elif step == "name":
            user_name = rng.choice(NAMES)
            intro = rng.choice(["my name is {n}", "i'm {n}", "call me {n}", "i am {n}", "hi, i'm {n}", "my name's {n}"])
            say(_noise(intro.format(n=user_name), rng),
                rng.choice(["Nice to meet you, {n}!", "Hi {n}! Great to meet you.", "Hello {n}, nice to meet you.",
                            "Nice to meet you {n}! I'm Mnemo."]).format(n=user_name))
        elif step == "like":
            thing = rng.choice(LIKES)
            say(_noise(rng.choice(["i like {t}", "i love {t}", "i really like {t}", "my favorite thing is {t}",
                                   "i'm into {t}"]).format(t=thing), rng),
                rng.choice(["Oh, {t}! What do you like about it?", "Nice, {t} is a lot of fun.",
                            "Cool! How did you get into {t}?", "I'd love to learn more about {t}. Tell me about it!"])
                .format(t=thing, T=thing[:1].upper() + thing[1:]))
        elif step == "joke":
            say(_noise(rng.choice(JOKE_USER), rng), rng.choice(JOKES))
            if rng.random() < 0.5:
                say(_noise(rng.choice(["lol", "haha", "that's funny", "good one", "lmao"]), rng),
                    rng.choice(["Glad you liked it!", "Ha! I have more if you want.", "Thanks, I've been practicing."]))
        elif step == "fav":
            q = rng.choice(FAV_USER)
            say(_q(q, rng), FAV_BOT[q])
        elif step == "fact":
            q, a = rng.choice(FACTS)
            say(_q(q, rng), a)
        elif step == "math":
            a, b = rng.randint(0, 12), rng.randint(0, 12)
            if rng.random() < 0.5:
                q = rng.choice(["what is {a} plus {b}", "what's {a} + {b}", "{a}+{b}", "add {a} and {b}", "what is {a} + {b}"])
                ans = a + b
                say(_q(q.format(a=a, b=b), rng), rng.choice(["{a} plus {b} is {c}.", "{c}", "It's {c}.", "The answer is {c}."])
                    .format(a=a, b=b, c=ans))
            else:
                a, b = max(a, b), min(a, b)
                q = rng.choice(["what is {a} minus {b}", "what's {a} - {b}", "{a}-{b}", "what is {a} times {b}"])
                ans = a * b if "times" in q else a - b
                word = "times" if "times" in q else "minus"
                say(_q(q.format(a=a, b=b), rng), rng.choice(["{a} {w} {b} is {c}.", "{c}", "It's {c}.", "The answer is {c}."])
                    .format(a=a, b=b, c=ans, w=word))
        elif step == "ack":
            say(_noise(rng.choice(ACK_USER), rng), rng.choice(ACK_BOT))
        elif step == "thank":
            say(_noise(rng.choice(THANK_USER), rng), rng.choice(THANK_BOT))
        elif step == "bye":
            say(_noise(rng.choice(BYE_USER), rng), rng.choice(BYE_BOT))
    if user_name and rng.random() < 0.8:  # remembering something said earlier in the chat
        say(_q(rng.choice(["what's my name", "what is my name", "do you remember my name", "who am i"]), rng),
            rng.choice(["Your name is {n}.", "You're {n}!", "Of course, you're {n}.", "You told me your name is {n}."])
            .format(n=user_name))
    if rng.random() < 0.15:  # counting with number words
        n = rng.randint(1, 15)
        say(_q(rng.choice(["count to {n}", "can you count to {n}"]).format(n=n), rng), ", ".join(NUMWORDS[1:n + 1]) + ".")
    return msgs


def examples(n: int = 30000, seed: int = 0) -> list[list[dict]]:
    rng = random.Random(seed)
    return [conversation(rng) for _ in range(n)]


def as_text(convs) -> list[str]:
    return [" ".join(m["content"] for m in c) for c in convs]


async def teach(trainer, minutes: float = 15) -> dict:
    """Build the course (and a first vocabulary if Mnemo has none yet), then practice on it for `minutes`."""
    def prepare():
        if not tokenizer.exists():
            events.emit("model", text="Building a vocabulary from the conversation course…")
            texts = as_text(examples(30000))
            texts += [r["text"] for r in memory.db().execute("SELECT text FROM docs WHERE text IS NOT NULL LIMIT 3000")]
            tokenizer.train(texts)
        return build(tokenizer.load())

    n = await asyncio.to_thread(prepare)
    trainer.focus({("chat", "basics")}, minutes, "basic conversation")
    events.emit("model", text=f"Practicing basic conversation for {minutes:g} minutes ({n / 1e6:.1f}M tokens of examples).")
    return {"tokens": n, "minutes": minutes}


def build(tok, n: int = 30000) -> int:
    """Write the course to chat/basics-*.bin (replacing any previous copy). Returns tokens written."""
    for f in CHAT_DIR.glob("basics-*.bin"):
        f.unlink()
    writer = ShardWriter(CHAT_DIR, "basics")
    rng = random.Random(1)
    ids: list[int] = []
    for conv in examples(n):
        # Tag mostly as general/conversation so it talks the same way in every mode.
        topic = rng.choices(["general", "conversation"] + [m for m in modes.MODES if m not in ("general", "conversation")],
                            weights=[5, 3] + [0.4] * (len(modes.MODES) - 2))[0]
        ids += tokenizer.chat_training_ids(tok, [{"role": "system", "content": modes.tag(topic)}] + conv)
    return writer.append(ids)
