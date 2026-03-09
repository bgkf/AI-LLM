import json
import os
from shared.safety import is_safe_path


# --- Tool definitions ---
filesystem_tools = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and folders in a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    }
]


# --- Tool execution (your code does this, not the model) ---
def execute_tool(name, args, allowed_dir):
    if name == "list_directory":
        path = args["path"]
        if not is_safe_path(path, allowed_dir):
            return "Error: Access denied"
        return json.dumps(os.listdir(path))

    elif name == "read_file":
        path = args["path"]
        if not is_safe_path(path, allowed_dir):
            return "Error: Access denied"
        with open(path) as f:
            return f.read()

    elif name == "write_file":
        path = args["path"]
        if not is_safe_path(path, allowed_dir):
            return "Error: Access denied"
        with open(path, "w") as f:
            f.write(args["content"])
        return "File written successfully"

    return f"Error: Unknown tool '{name}'"
