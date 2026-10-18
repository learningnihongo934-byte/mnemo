"""Small helpers: /time, /calc, /remember."""
import ast
import datetime
import operator

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.FloorDiv: operator.floordiv}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.operand))
    raise ValueError("only numbers and + - * / ** % //")


def register(mnemo):
    @mnemo.command("/time", "current date and time")
    def time_(arg, ctx):
        return datetime.datetime.now().strftime("It's %A, %B %d %Y, %I:%M %p.")

    @mnemo.command("/calc", "calculator, e.g. /calc 12*(3+4)")
    def calc(arg, ctx):
        try:
            return f"`{arg}` = **{_eval(ast.parse(arg, mode='eval').body):g}**"
        except Exception as e:
            return f"Can't calculate that: {e}"

    @mnemo.command("/remember", "save a note to memory, e.g. /remember my wifi is on floor 2")
    def remember(arg, ctx):
        if not arg:
            return "Usage: `/remember something important`"
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        ctx.memory.add_doc(f"note:{stamp}", "Note: " + arg[:60], (arg + "\n") * 3, "note")
        return "📝 Saved to memory."
