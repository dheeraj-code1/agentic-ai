import random
import uuid
from typing import Annotated, Literal, TypedDict

from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt

load_dotenv(find_dotenv())

MODEL = "openai/gpt-oss-20b"

ORDER_RETRIES = 3
COOK_RETRIES = 2
SERVE_RETRIES = 2
COOK_SUCCESS_PROBABILITY = 0.6
SERVE_SUCCESS_PROBABILITY = 0.6

MENU = {
    "paneer butter masala": 5,
    "dal makhani": 10,
    "veg biryani": 3,
    "chicken biryani": 2,
    "butter naan": 20,
    "masala dosa": 0,
    "gulab jamun": 8,
}

OrderStatus = Literal[
    "pending",
    "unavailable",
    "partial",
    "confirmed",
    "cooked",
    "completed",
    "failed",
    "cancelled",
]


class OrderDetails(TypedDict):
    dish_name: str
    quantity: int
    available_quantity: int


class RestaurantState(TypedDict):
    messages: Annotated[list, add_messages]
    order: OrderDetails
    status: OrderStatus
    order_retries: int
    cook_retries: int
    serve_retries: int
    final_result: str


@tool
def order_confirm(dish_name: str, quantity: int) -> str:
    """Check the menu for a dish and place the order. Call this whenever the user
    orders a dish, or agrees to proceed with the partially available quantity.

    Args:
        dish_name: Exact dish name as written in the menu (fix typos / short names).
        quantity: Number of plates requested, 1 if not specified.
    """
    # Executed by the order_confirm graph node, not by the LLM directly.
    return ""


llm = ChatGroq(model=MODEL, temperature=0)
order_llm = llm.bind_tools([order_confirm])

AGENT_PROMPT = f"""You are the order-taking assistant of a restaurant.
Menu dishes: {", ".join(MENU)}
You do NOT know stock levels; only the `order_confirm` tool can check them.

Rules:
- The user can order exactly ONE dish per order. If no quantity is given, assume 1.
- When the user orders any food dish (even one not on the menu), ALWAYS call the
  `order_confirm` tool with the dish name and quantity. Never answer about availability yourself.
- Users make typos and use short or alternate names. Map what they wrote to the matching
  menu dish and pass the EXACT menu name, e.g. "paneeeer buttere maslala" -> "paneer butter masala",
  "naan" -> "butter naan". Only if no menu dish reasonably matches, pass the user's dish name as-is.
- If a previous order was partially available and the user agrees to proceed, call
  `order_confirm` with the same dish and the available quantity.
- If the user picks a different dish, call `order_confirm` with the new dish.
- If the message is not about ordering food from this restaurant, or the user declines
  to order, do NOT call any tool; reply with one short polite closing sentence."""


def order_summary(state: RestaurantState) -> str:
    order = state.get("order") or {}
    return (
        f"dish={order.get('dish_name')!r}, requested={order.get('quantity')}, "
        f"available={order.get('available_quantity')}, status={state['status']}, "
        f"order_retries_left={state['order_retries']}, cook_retries_left={state['cook_retries']}, "
        f"serve_retries_left={state['serve_retries']}"
    )


def llm_say(state: RestaurantState, instruction: str) -> AIMessage:
    system = SystemMessage(
        f"You are a friendly restaurant assistant. Menu: {MENU}\n"
        f"Current order state: {order_summary(state)}\n{instruction}\n"
        "Reply in 1-3 short sentences. Do not invent facts beyond the state."
    )
    return AIMessage(llm.invoke([system, *state["messages"]]).content)


def human(state: RestaurantState):
    user_input = interrupt("Waiting for user input")
    return {"messages": [HumanMessage(user_input)]}


def agent(state: RestaurantState):
    response = order_llm.invoke([SystemMessage(AGENT_PROMPT), *state["messages"]])
    if response.tool_calls:
        return {"messages": [response]}
    return {"messages": [response], "status": "cancelled"}


def order_confirm_node(state: RestaurantState):
    tool_call = state["messages"][-1].tool_calls[0]
    dish_name = str(tool_call["args"].get("dish_name", "")).strip().lower()
    quantity = int(tool_call["args"].get("quantity", 1) or 1)
    available = MENU.get(dish_name, 0)

    if available == 0:
        status = "unavailable"
    elif available < quantity:
        status = "partial"
    else:
        status = "confirmed"

    order_retries = state["order_retries"] - (status != "confirmed")
    print(f"[order_confirm] {dish_name} x{quantity} -> {status} (available={available})")

    return {
        "order": {"dish_name": dish_name, "quantity": quantity, "available_quantity": available},
        "status": status,
        "order_retries": order_retries,
        "messages": [
            ToolMessage(
                f"status={status}, requested={quantity}, available={available}",
                tool_call_id=tool_call["id"],
            )
        ],
    }


def ask_user(state: RestaurantState):
    if state["status"] == "unavailable":
        instruction = (
            "The requested dish is not available. Tell the user and ask them to order "
            "something else from the menu."
        )
    else:
        instruction = (
            "Only part of the requested quantity is available. Tell the user how many are "
            "available and ask whether to proceed with that quantity or order something else."
        )
    return {"messages": [llm_say(state, instruction)]}


def cook(state: RestaurantState):
    if random.random() < COOK_SUCCESS_PROBABILITY:
        print("[cook] success")
        return {"status": "cooked"}
    print(f"[cook] failed, cook retries left: {state['cook_retries'] - 1}")
    return {"cook_retries": state["cook_retries"] - 1}


def serve(state: RestaurantState):
    if random.random() < SERVE_SUCCESS_PROBABILITY:
        print("[serve] success")
        return {"status": "completed"}
    print(f"[serve] failed, serve retries left: {state['serve_retries'] - 1}")
    # The served dish was lost, so it has to be cooked again.
    return {"serve_retries": state["serve_retries"] - 1, "status": "confirmed"}


def finish(state: RestaurantState):
    status = state["status"]
    if status == "cancelled":
        return {"final_result": "Order not placed."}

    if status == "completed":
        order = state["order"]
        final_result = f"Order completed: {order['quantity']} x {order['dish_name']}."
        instruction = "The order was cooked and served successfully. Tell the user to enjoy the meal."
    else:
        if state["order_retries"] == 0:
            reason = "none of the requested dishes could be ordered after 3 attempts"
        elif state["cook_retries"] == 0:
            reason = "the kitchen failed to cook the dish"
        else:
            reason = "the dish could not be served to the table"
        status = "failed"
        final_result = f"Order failed: {reason}."
        instruction = (
            f"The order FAILED and will NOT be delivered because {reason}. "
            "Apologize sincerely to the user. Do not say the order is confirmed or served."
        )

    return {
        "status": status,
        "final_result": final_result,
        "messages": [llm_say({**state, "status": status}, instruction)],
    }


def route_agent(state: RestaurantState):
    return "order_confirm" if state["status"] != "cancelled" else "finish"


def route_order(state: RestaurantState):
    if state["status"] == "confirmed":
        return "cook"
    return "ask_user" if state["order_retries"] > 0 else "finish"


def route_cook(state: RestaurantState):
    if state["status"] == "cooked":
        return "serve"
    return "cook" if state["cook_retries"] > 0 else "finish"


def route_serve(state: RestaurantState):
    if state["status"] == "completed" or state["serve_retries"] == 0:
        return "finish"
    return "cook" if state["cook_retries"] > 0 else "finish"


def build_graph():
    graph = StateGraph(RestaurantState)
    graph.add_node("human", human)
    graph.add_node("agent", agent)
    graph.add_node("order_confirm", order_confirm_node)
    graph.add_node("ask_user", ask_user)
    graph.add_node("cook", cook)
    graph.add_node("serve", serve)
    graph.add_node("finish", finish)

    graph.add_edge(START, "human")
    graph.add_edge("human", "agent")
    graph.add_conditional_edges("agent", route_agent, ["order_confirm", "finish"])
    graph.add_conditional_edges("order_confirm", route_order, ["cook", "ask_user", "finish"])
    graph.add_edge("ask_user", "human")
    graph.add_conditional_edges("cook", route_cook, ["serve", "cook", "finish"])
    graph.add_conditional_edges("serve", route_serve, ["cook", "finish"])
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=InMemorySaver())


def print_new_ai_messages(result, seen: int) -> int:
    messages = result["messages"]
    for message in messages[seen:]:
        if isinstance(message, AIMessage) and message.content and not message.tool_calls:
            print(f"Agent: {message.content}")
    return len(messages)


def main():
    app = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    initial_state = {
        "messages": [],
        "order": {"dish_name": "", "quantity": 0, "available_quantity": 0},
        "status": "pending",
        "order_retries": ORDER_RETRIES,
        "cook_retries": COOK_RETRIES,
        "serve_retries": SERVE_RETRIES,
        "final_result": "",
    }

    print("Menu:", ", ".join(f"{dish} ({qty})" for dish, qty in MENU.items()))
    result = app.invoke(initial_state, config)
    seen = 0
    while "__interrupt__" in result:
        user_input = input("You: ").strip()
        result = app.invoke(Command(resume=user_input), config)
        seen = print_new_ai_messages(result, seen)

    print(f"\nFinal result: {result['final_result']} (status={result['status']})")


if __name__ == "__main__":
    main()
