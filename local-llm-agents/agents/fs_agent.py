import json
from openai import OpenAI
from shared.config import config
from shared.tools import filesystem_tools, execute_tool

client = OpenAI(base_url=f"{config['llama_server_url']}/v1", api_key="none")

ALLOWED_DIR = config["allowed_dir"]

# --- Agentic loop ---
def run(messages):
    while True:
        response = client.chat.completions.create(
            model="local",
            messages=messages,
            tools=filesystem_tools,
            tool_choice="auto"
        )

        msg = response.choices[0].message

        # Model is done, return final text
        if msg.tool_calls is None:
            messages.append({"role": "assistant", "content": msg.content})
            return msg.content

        # Model wants to call tools — execute them
        messages.append(msg)  # add assistant message with tool_calls

        for tool_call in msg.tool_calls:
            result = execute_tool(
                tool_call.function.name,
                json.loads(tool_call.function.arguments),
                ALLOWED_DIR
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })
        # Loop: send results back to the model


if __name__ == "__main__":
    print(f"Agent ready. Talking to LLM at {config['llama_server_url']}")
    print(f"Filesystem access limited to: {ALLOWED_DIR}")
    print("Type 'exit' to quit.\n")

    messages = [
        {
            "role": "system",
            "content": (
                f"/no-think\n"
                f"You are a helpful assistant with access to the local filesystem. "
                f"You may only access files within: {ALLOWED_DIR}\n"
                f"Use the provided tools to list directories, read files, and write files."
            )
        }
    ]

    while True:
        user_input = input("You: ")
        if user_input.strip().lower() == "exit":
            break
        messages.append({"role": "user", "content": user_input})
        result = run(messages)
        print(f"\nAgent: {result}\n")
