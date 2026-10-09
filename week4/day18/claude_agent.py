import ast
import json
import operator
import os

from dotenv import find_dotenv, load_dotenv
from groq import Groq
from tavily import TavilyClient

load_dotenv(find_dotenv())

MODEL = "openai/gpt-oss-20b"

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


def web_search(query: str) -> str:
    response = tavily_client.search(query=query, max_results=5)
    results = [
        {"title": r["title"], "url": r["url"], "content": r["content"]}
        for r in response.get("results", [])
    ]
    return json.dumps(results)


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def calculate(expression: str) -> str:
    # Only arithmetic is allowed; plain eval() would execute arbitrary code.
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_eval_node(tree.body))
    except Exception as e:
        return f"Error: {e}"


tools = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for up-to-date information on any topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a simple math expression using + - * / // % ** and parentheses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate, e.g. '(12 + 8) * 3'.",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]

available_functions = {
    "web_search": web_search,
    "calculate": calculate,
}


def run_agent(user_input: str, max_iterations: int = 5) -> str:
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Use web_search for current or factual "
            "information and calculate for any math. Don't repeat similar searches: after "
            "one or two searches, answer with the best information you have. If the question "
            "is ambiguous, share what you found and ask the user to clarify.",
        },
        {"role": "user", "content": user_input},
    ]

    for iteration in range(1, max_iterations + 1):
        print(f"\n--- Iteration {iteration}/{max_iterations} ---")
        if iteration < max_iterations:
            response = groq_client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
        else:
            # gpt-oss on Groq ignores tool_choice="none" and errors, so drop tools entirely.
            messages.append(
                {
                    "role": "system",
                    "content": "Tool limit reached. Give your final answer now using only "
                    "the information gathered so far.",
                }
            )
            response = groq_client.chat.completions.create(model=MODEL, messages=messages)
        message = response.choices[0].message

        if not message.tool_calls:
            print(f"[done] final answer after {iteration} iteration(s)")
            return message.content

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [tc.model_dump() for tc in message.tool_calls],
            }
        )

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}")
            print(f"[tool call] {name}({args})")

            func = available_functions.get(name)
            result = func(**args) if func else f"Error: unknown tool {name}"
            print(f"[tool result] {result[:200]}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": name,
                    "content": result,
                }
            )

    return f"Stopped: reached {max_iterations} iterations without a final answer."


if __name__ == "__main__":
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        if user_input:
            print("Agent:", run_agent(user_input))
