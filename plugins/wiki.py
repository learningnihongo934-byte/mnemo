"""/wiki <topic>: quick Wikipedia summary, saved to memory."""
import httpx


def register(mnemo):
    @mnemo.command("/wiki", "Wikipedia summary of a topic (also saved to memory)")
    def wiki(arg, ctx):
        if not arg:
            return "Usage: `/wiki black holes`"
        r = httpx.get("https://en.wikipedia.org/api/rest_v1/page/summary/" + arg.replace(" ", "_"),
                      headers={"User-Agent": ctx.settings["user_agent"]}, timeout=10, follow_redirects=True)
        if r.status_code != 200:
            return f"No Wikipedia page found for “{arg}”."
        j = r.json()
        url = j.get("content_urls", {}).get("desktop", {}).get("page", "")
        ctx.crawler.learn_page(url, j.get("title", arg), j.get("extract", ""), source="plugin")
        return f"**{j.get('title')}**\n\n{j.get('extract', '')}\n\n{url}"
