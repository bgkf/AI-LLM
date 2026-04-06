#!/bin/bash
# =============================================================================
# Agent Tools Connection Report
# Runs as a script (not a Jamf EA) — outputs plain JSON to stdout
# Requires: jq (built-in on macOS 26+)
#
# Tools covered:
#   Claude Desktop, ChatGPT, Cursor, Gemini (Google), Raycast,
#   Warp, Visual Studio Code, Comet (Perplexity),
#   Superhuman, Bear, TickTick, Perplexity
#
# Note: Claude Code shares Claude Desktop's MCP config
#   (~/.claude/claude_desktop_config.json) and is not reported separately.
#
# Install-only tools (no MCP config — presence + version only):
#   Superhuman, Bear, TickTick, Perplexity
# =============================================================================

CURRENT_USER=$(stat -f "%Su" /dev/console 2>/dev/null)
[[ -z "$CURRENT_USER" || "$CURRENT_USER" == "root" ]] && CURRENT_USER=""

USER_HOME=""
if [[ -n "$CURRENT_USER" ]]; then
  USER_HOME=$(dscl . -read "/Users/${CURRENT_USER}" NFSHomeDirectory 2>/dev/null | awk '{print $2}')
  [[ -z "$USER_HOME" ]] && USER_HOME="/Users/${CURRENT_USER}"
fi

HOSTNAME=$(hostname -s)
OS_VERSION=$(sw_vers -productVersion)
SERIAL=$(system_profiler SPHardwareDataType 2>/dev/null | awk '/Serial Number/ {print $NF}')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ── Helper: app version or "not_installed" ────────────────────────────────────
app_version() {
  [[ -d "$1" ]] || { echo "not_installed"; return; }
  /usr/bin/defaults read "${1}/Contents/Info" CFBundleShortVersionString 2>/dev/null \
    | tr -d '\n' || echo "unknown"
}

# ═════════════════════════════════════════════════════════════════════════════
# CLAUDE DESKTOP
# ~/.claude/claude_desktop_config.json → mcpServers
# Also used by Claude Code — not reported separately.
# ═════════════════════════════════════════════════════════════════════════════
CLAUDE_VERSION=$(app_version "/Applications/Claude.app")
CLAUDE_CONNECTIONS="[]"

if [[ "$CLAUDE_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  for cfg in \
      "${USER_HOME}/Library/Application Support/Claude/claude_desktop_config.json" \
      "${USER_HOME}/.claude/claude_desktop_config.json"; do
    [[ -f "$cfg" ]] || continue
    CLAUDE_CONNECTIONS=$(jq -c '
      .mcpServers // {} | to_entries | map({
        name:    .key,
        type:    "mcp",
        command: (.value.command // ""),
        enabled: true
      })
    ' "$cfg" 2>/dev/null || echo "[]")
    break
  done
fi

# ═════════════════════════════════════════════════════════════════════════════
# CHATGPT
# ~/Library/Application Support/OpenAI/ChatGPT/settings.json → enabledConnectors
# ═════════════════════════════════════════════════════════════════════════════
CHATGPT_VERSION=$(app_version "/Applications/ChatGPT.app")
CHATGPT_CONNECTIONS="[]"

if [[ "$CHATGPT_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  cfg="${USER_HOME}/Library/Application Support/OpenAI/ChatGPT/settings.json"
  if [[ -f "$cfg" ]]; then
    CHATGPT_CONNECTIONS=$(jq -c '
      (.enabledConnectors // .plugins // []) |
      if type == "array" then
        map({name: (. | tostring), type: "connector", enabled: true})
      elif type == "object" then
        to_entries | map({
          name:    .key,
          type:    "connector",
          enabled: (.value | if type == "boolean" then . else true end)
        })
      else [] end
    ' "$cfg" 2>/dev/null || echo "[]")
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# CURSOR
# ~/.cursor/mcp.json → mcpServers
# ~/Library/Application Support/Cursor/User/settings.json → SSH, Copilot, model
# ═════════════════════════════════════════════════════════════════════════════
CURSOR_VERSION=$(app_version "/Applications/Cursor.app")
CURSOR_CONNECTIONS="[]"

if [[ "$CURSOR_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  CURSOR_SETTINGS="${USER_HOME}/Library/Application Support/Cursor/User/settings.json"
  CURSOR_MCP="${USER_HOME}/.cursor/mcp.json"

  CURSOR_FROM_SETTINGS="[]"
  if [[ -f "$CURSOR_SETTINGS" ]]; then
    CURSOR_FROM_SETTINGS=$(jq -cn \
      --argjson cfg "$(jq '.' "$CURSOR_SETTINGS" 2>/dev/null || echo '{}')" '
      []
      + (if $cfg["remote.SSH.configFile"] then
           [{name: "SSH", type: "remote", enabled: true}]
         else [] end)
      + (if $cfg["github.copilot.enable"] == true then
           [{name: "GitHub Copilot", type: "ai", enabled: true}]
         else [] end)
      + (if ($cfg["cursor.aiModel"] // $cfg["cursor.general.aiModel"]) != null then
           [{name: ("AI Model: " + ($cfg["cursor.aiModel"] // $cfg["cursor.general.aiModel"])),
             type: "ai", enabled: true}]
         else [] end)
    ' 2>/dev/null || echo "[]")
  fi

  CURSOR_FROM_MCP="[]"
  if [[ -f "$CURSOR_MCP" ]]; then
    CURSOR_FROM_MCP=$(jq -c '
      .mcpServers // {} | to_entries | map({
        name:    .key,
        type:    "mcp",
        command: (.value.command // ""),
        enabled: true
      })
    ' "$CURSOR_MCP" 2>/dev/null || echo "[]")
  fi

  CURSOR_CONNECTIONS=$(jq -cn \
    --argjson a "$CURSOR_FROM_SETTINGS" \
    --argjson b "$CURSOR_FROM_MCP" \
    '$a + $b')
fi

# ═════════════════════════════════════════════════════════════════════════════
# GEMINI (Google)
# ~/Library/Application Support/Google/Gemini/ + Keychain
# ═════════════════════════════════════════════════════════════════════════════
GEMINI_VERSION="not_installed"
for candidate in \
    "/Applications/Gemini.app" \
    "/Applications/Google AI.app" \
    "/Applications/Google Gemini.app"; do
  if [[ -d "$candidate" ]]; then
    GEMINI_VERSION=$(app_version "$candidate")
    break
  fi
done

GEMINI_CONNECTIONS="[]"
if [[ "$GEMINI_VERSION" != "not_installed" && -n "$CURRENT_USER" ]]; then
  declare -A GEMINI_MAP
  GEMINI_MAP["Google Drive"]="com.google.GoogleDrive"
  GEMINI_MAP["Gmail"]="com.google.Gmail"
  GEMINI_MAP["Calendar"]="com.google.Calendar"
  GEMINI_MAP["Google Docs"]="com.google.GoogleDocs"
  GEMINI_MAP["YouTube"]="com.google.YouTube"
  GEMINI_MAP["Maps"]="com.google.Maps"

  GEMINI_ITEMS="[]"
  for svc in "Google Drive" "Gmail" "Calendar" "Google Docs" "YouTube" "Maps"; do
    if /usr/bin/security find-generic-password \
        -s "${GEMINI_MAP[$svc]}" -a "$CURRENT_USER" &>/dev/null; then
      GEMINI_ITEMS=$(jq -cn \
        --argjson arr "$GEMINI_ITEMS" \
        --arg name "$svc" \
        '$arr + [{name: $name, type: "google_workspace", enabled: true}]')
    fi
  done
  GEMINI_CONNECTIONS="$GEMINI_ITEMS"
fi

# ═════════════════════════════════════════════════════════════════════════════
# RAYCAST
# Keychain (Raycast - <Service>), extensions dir, aiProvider/aiModel defaults
# ═════════════════════════════════════════════════════════════════════════════
RAYCAST_VERSION=$(app_version "/Applications/Raycast.app")
RAYCAST_EXT_COUNT=0
RAYCAST_CONNECTIONS="[]"

if [[ "$RAYCAST_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  EXTENSIONS_DIR="${USER_HOME}/Library/Application Support/com.raycast.macos/extensions"
  if [[ -d "$EXTENSIONS_DIR" ]]; then
    RAYCAST_EXT_COUNT=$(find "$EXTENSIONS_DIR" -maxdepth 1 -mindepth 1 -type d 2>/dev/null \
      | wc -l | tr -d ' ')
  fi

  RAYCAST_ITEMS="[]"
  for svc in "GitHub" "Slack" "Linear" "Jira" "Notion" "Google Calendar" "Spotify" "1Password"; do
    if /usr/bin/security find-generic-password \
        -s "Raycast - ${svc}" &>/dev/null; then
      RAYCAST_ITEMS=$(jq -cn \
        --argjson arr "$RAYCAST_ITEMS" \
        --arg name "$svc" \
        '$arr + [{name: $name, type: "extension", enabled: true}]')
    fi
  done

  AI_PROVIDER=$(/usr/bin/defaults read com.raycast.macos aiProvider 2>/dev/null || true)
  if [[ -n "$AI_PROVIDER" ]]; then
    AI_MODEL=$(/usr/bin/defaults read com.raycast.macos aiModel 2>/dev/null || true)
    AI_LABEL="${AI_PROVIDER}${AI_MODEL:+:${AI_MODEL}}"
    RAYCAST_ITEMS=$(jq -cn \
      --argjson arr "$RAYCAST_ITEMS" \
      --arg name "$AI_LABEL" \
      '$arr + [{name: $name, type: "ai_provider", enabled: true}]')
  fi

  RAYCAST_CONNECTIONS="$RAYCAST_ITEMS"
fi

# ═════════════════════════════════════════════════════════════════════════════
# WARP
# ~/Library/Group Containers/2BBY89MBSN.dev.warp/.../mcp/*.json → mcpServers
# Each file in the mcp/ directory is a separate server config
# ═════════════════════════════════════════════════════════════════════════════
WARP_VERSION=$(app_version "/Applications/Warp.app")
WARP_CONNECTIONS="[]"

if [[ "$WARP_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  WARP_MCP_DIR="${USER_HOME}/Library/Group Containers/2BBY89MBSN.dev.warp/Library/Application Support/dev.warp.Warp-Stable/mcp"

  if [[ -d "$WARP_MCP_DIR" ]]; then
    WARP_CONNECTIONS=$(
      find "$WARP_MCP_DIR" -maxdepth 1 -name "*.json" 2>/dev/null \
        | sort \
        | while IFS= read -r f; do
            jq -c '
              .mcpServers // {} | to_entries[] | {
                name:    .key,
                type:    "mcp",
                command: (.value.command // .value.url // ""),
                enabled: true
              }
            ' "$f" 2>/dev/null
          done \
        | jq -sc '.'
    )
    [[ -z "$WARP_CONNECTIONS" ]] && WARP_CONNECTIONS="[]"
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# VISUAL STUDIO CODE
# ~/Library/Application Support/Code/User/mcp.json → servers
# Note: VS Code uses "servers" key (not "mcpServers" like everyone else)
# ═════════════════════════════════════════════════════════════════════════════
VSCODE_VERSION=$(app_version "/Applications/Visual Studio Code.app")
VSCODE_CONNECTIONS="[]"

if [[ "$VSCODE_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  VSCODE_MCP="${USER_HOME}/Library/Application Support/Code/User/mcp.json"

  if [[ -f "$VSCODE_MCP" ]]; then
    VSCODE_CONNECTIONS=$(jq -c '
      .servers // {} | to_entries | map({
        name:    .key,
        type:    "mcp",
        command: (.value.command // .value.url // ""),
        enabled: true
      })
    ' "$VSCODE_MCP" 2>/dev/null || echo "[]")
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# COMET (Perplexity AI Browser)
# ~/Library/Application Support/Comet/mcp.json → mcpServers
# ═════════════════════════════════════════════════════════════════════════════
COMET_VERSION=$(app_version "/Applications/Comet.app")
COMET_CONNECTIONS="[]"

if [[ "$COMET_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  COMET_MCP="${USER_HOME}/Library/Application Support/Comet/mcp.json"

  if [[ -f "$COMET_MCP" ]]; then
    COMET_CONNECTIONS=$(jq -c '
      .mcpServers // {} | to_entries | map({
        name:    .key,
        type:    "mcp",
        command: (.value.command // .value.url // ""),
        enabled: true
      })
    ' "$COMET_MCP" 2>/dev/null || echo "[]")
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# INSTALL-ONLY TOOLS
# No MCP config — presence and version reported only, connections always []
# ═════════════════════════════════════════════════════════════════════════════
SUPERHUMAN_VERSION=$(app_version "/Applications/Superhuman.app")
BEAR_VERSION=$(app_version "/Applications/Bear.app")
TICKTICK_VERSION=$(app_version "/Applications/TickTick.app")
PERPLEXITY_VERSION=$(app_version "/Applications/Perplexity.app")

# ═════════════════════════════════════════════════════════════════════════════
# EMIT JSON
# All values passed via --arg / --argjson — no bash interpolation in jq source
# ═════════════════════════════════════════════════════════════════════════════
OUTPUT_JSON=$(jq -cn \
  --arg      ts                  "$TIMESTAMP" \
  --arg      hostname             "$HOSTNAME" \
  --arg      serial               "$SERIAL" \
  --arg      os_version           "$OS_VERSION" \
  --arg      current_user         "$CURRENT_USER" \
  --arg      claude_ver           "$CLAUDE_VERSION" \
  --argjson  claude_conns         "$CLAUDE_CONNECTIONS" \
  --arg      chatgpt_ver          "$CHATGPT_VERSION" \
  --argjson  chatgpt_conns        "$CHATGPT_CONNECTIONS" \
  --arg      cursor_ver           "$CURSOR_VERSION" \
  --argjson  cursor_conns         "$CURSOR_CONNECTIONS" \
  --arg      gemini_ver           "$GEMINI_VERSION" \
  --argjson  gemini_conns         "$GEMINI_CONNECTIONS" \
  --arg      raycast_ver          "$RAYCAST_VERSION" \
  --argjson  raycast_conns        "$RAYCAST_CONNECTIONS" \
  --argjson  raycast_exts         "$RAYCAST_EXT_COUNT" \
  --arg      warp_ver             "$WARP_VERSION" \
  --argjson  warp_conns           "$WARP_CONNECTIONS" \
  --arg      vscode_ver           "$VSCODE_VERSION" \
  --argjson  vscode_conns         "$VSCODE_CONNECTIONS" \
  --arg      comet_ver            "$COMET_VERSION" \
  --argjson  comet_conns          "$COMET_CONNECTIONS" \
  --arg      superhuman_ver       "$SUPERHUMAN_VERSION" \
  --arg      bear_ver             "$BEAR_VERSION" \
  --arg      ticktick_ver         "$TICKTICK_VERSION" \
  --arg      perplexity_ver       "$PERPLEXITY_VERSION" \
  '
  def tool($ver; $conns):
    { installed: ($ver != "not_installed"),
      version:   (if $ver == "not_installed" then null else $ver end),
      connections: $conns };

  def install_only($ver):
    tool($ver; []);

  {
    collected_at: $ts,
    device: {
      hostname:      $hostname,
      serial_number: (if $serial == "" then null else $serial end),
      os_version:    $os_version,
      current_user:  (if $current_user == "" then null else $current_user end)
    },
    tools: {
      claude:              tool($claude_ver;   $claude_conns),
      chatgpt:             tool($chatgpt_ver;  $chatgpt_conns),
      cursor:              tool($cursor_ver;   $cursor_conns),
      gemini:              tool($gemini_ver;   $gemini_conns),
      raycast:            (tool($raycast_ver;  $raycast_conns)
                           + {extensions_installed: $raycast_exts}),
      warp:                tool($warp_ver;     $warp_conns),
      visual_studio_code:  tool($vscode_ver;   $vscode_conns),
      comet:               tool($comet_ver;    $comet_conns),
      superhuman:          install_only($superhuman_ver),
      bear:                install_only($bear_ver),
      ticktick:            install_only($ticktick_ver),
      perplexity:          install_only($perplexity_ver)
    }
  }
  ')

# ═════════════════════════════════════════════════════════════════════════════
# OUTPUT + POST
# Print JSON to stdout (visible in Jamf policy log)
# POST to Okta Workflow webhook — set OKTA_WEBHOOK_URL before deploying
# ═════════════════════════════════════════════════════════════════════════════
echo "$OUTPUT_JSON"

OKTA_WEBHOOK_URL="https://webhook_invoke.url"

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$OKTA_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "User-Agent: AgentToolsReport/1.0" \
  --max-time 10 \
  --retry 2 \
  -d "$OUTPUT_JSON")

if [[ "$HTTP_STATUS" =~ ^2 ]]; then
  echo "Posted to Okta webhook: HTTP $HTTP_STATUS" >&2
else
  echo "Webhook POST failed: HTTP $HTTP_STATUS" >&2
  exit 1
fi