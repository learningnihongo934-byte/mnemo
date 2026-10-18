"""/define <word>: dictionary definition."""
import httpx


def register(mnemo):
    @mnemo.command("/define", "dictionary definition of a word")
    def define(arg, ctx):
        if not arg:
            return "Usage: `/define serendipity`"
        r = httpx.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{arg.split()[0]}", timeout=10)
        if r.status_code != 200:
            return f"I couldn't find “{arg}”."
        out = [f"**{arg}**"]
        for m in r.json()[0]["meanings"][:3]:
            out.append(f"*{m['partOfSpeech']}*: {m['definitions'][0]['definition']}")
        return "\n".join(out)
