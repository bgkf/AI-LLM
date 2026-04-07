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
# Connection detection methods:
#   MCP config files  → Claude, Claude Code, Cursor, Warp, VS Code, Comet
#   Settings JSON     → ChatGPT
#   Keychain + prefs  → Gemini, Raycast, Superhuman, Bear, TickTick, Perplexity
#   Extensions dir    → Raycast (installed + authenticated extensions)
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
# Expanded from 6 to 14 Google Workspace services
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
  GEMINI_MAP["Google Calendar"]="com.google.Calendar"
  GEMINI_MAP["Google Docs"]="com.google.GoogleDocs"
  GEMINI_MAP["Google Sheets"]="com.google.GoogleSheets"
  GEMINI_MAP["Google Slides"]="com.google.GoogleSlides"
  GEMINI_MAP["YouTube"]="com.google.YouTube"
  GEMINI_MAP["Google Maps"]="com.google.Maps"
  GEMINI_MAP["Google Meet"]="com.google.Meet"
  GEMINI_MAP["Google Tasks"]="com.google.Tasks"
  GEMINI_MAP["Google Keep"]="com.google.Keep"
  GEMINI_MAP["Google Photos"]="com.google.Photos"
  GEMINI_MAP["Google Chat"]="com.google.Chat"
  GEMINI_MAP["Google Contacts"]="com.google.Contacts"

  GEMINI_ITEMS="[]"
  for svc_name in \
      "Google Drive" "Gmail" "Google Calendar" "Google Docs" "Google Sheets" \
      "Google Slides" "YouTube" "Google Maps" "Google Meet" "Google Tasks" \
      "Google Keep" "Google Photos" "Google Chat" "Google Contacts"; do
    bundle_id="${GEMINI_MAP[$svc_name]}"
    if /usr/bin/security find-generic-password \
        -s "$bundle_id" -a "$CURRENT_USER" &>/dev/null; then
      GEMINI_ITEMS=$(jq -cn \
        --argjson arr "$GEMINI_ITEMS" \
        --arg name "$svc_name" \
        '$arr + [{name: $name, type: "google_workspace", enabled: true}]')
    fi
  done
  GEMINI_CONNECTIONS="$GEMINI_ITEMS"
fi

# ═════════════════════════════════════════════════════════════════════════════
# RAYCAST
# extensions_installed + extensions[] → all installed extensions (package.json)
# connections[]                       → extensions with active Keychain credentials
#                                       (dynamic: checks every installed extension
#                                        title against "Raycast - <title>" in Keychain)
# aiProvider/aiModel                  → active AI provider from defaults
# ═════════════════════════════════════════════════════════════════════════════
RAYCAST_VERSION=$(app_version "/Applications/Raycast.app")
RAYCAST_EXT_NAMES="[]"
RAYCAST_CONNECTIONS="[]"

if [[ "$RAYCAST_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  EXTENSIONS_DIR="${USER_HOME}/Library/Application Support/com.raycast.macos/extensions"

  if [[ -d "$EXTENSIONS_DIR" ]]; then
    RAYCAST_EXT_NAMES=$(
      find "$EXTENSIONS_DIR" -maxdepth 2 -name "package.json" 2>/dev/null \
        | sort \
        | while IFS= read -r f; do
            jq -r '(.title // .name // null) | select(. != null)' "$f" 2>/dev/null
          done \
        | jq -R . | jq -sc '.'
    )
    [[ -z "$RAYCAST_EXT_NAMES" ]] && RAYCAST_EXT_NAMES="[]"
  fi

  RAYCAST_ITEMS="[]"

  if [[ -d "$EXTENSIONS_DIR" ]]; then
    while IFS= read -r pkg; do
      ext_name=$(jq -r '(.title // .name // null) | select(. != null)' "$pkg" 2>/dev/null)
      [[ -z "$ext_name" ]] && continue
      if /usr/bin/security find-generic-password \
          -s "Raycast - ${ext_name}" &>/dev/null 2>&1; then
        RAYCAST_ITEMS=$(jq -cn \
          --argjson arr "$RAYCAST_ITEMS" \
          --arg name "$ext_name" \
          '$arr + [{name: $name, type: "extension", enabled: true}]')
      fi
    done < <(find "$EXTENSIONS_DIR" -maxdepth 2 -name "package.json" 2>/dev/null | sort)
  fi

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
[[ -z "$VSCODE_CONNECTIONS" ]] && VSCODE_CONNECTIONS="[]"

# ═════════════════════════════════════════════════════════════════════════════
# COMET (Perplexity AI Browser)
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
# SUPERHUMAN
# Keychain (auth token presence) + preferences plist (account email)
# ═════════════════════════════════════════════════════════════════════════════
SUPERHUMAN_VERSION=$(app_version "/Applications/Superhuman.app")
SUPERHUMAN_CONNECTIONS="[]"

if [[ "$SUPERHUMAN_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  SUPERHUMAN_ITEMS="[]"

  for svc in "Superhuman" "com.superhuman.mail" "superhuman.com"; do
    if /usr/bin/security find-generic-password -s "$svc" &>/dev/null 2>&1; then
      SUPERHUMAN_ITEMS=$(jq -cn --argjson arr "$SUPERHUMAN_ITEMS" \
        '$arr + [{name: "Superhuman Account", type: "account", enabled: true}]')
      break
    fi
  done

  for pref_key in "userEmail" "primaryEmail" "accountEmail"; do
    email=$(/usr/bin/defaults read com.superhuman.mail "$pref_key" 2>/dev/null || true)
    if [[ -n "$email" && "$email" =~ @ ]]; then
      SUPERHUMAN_ITEMS=$(jq -cn --argjson arr "$SUPERHUMAN_ITEMS" \
        --arg name "$email" \
        '$arr + [{name: $name, type: "email_account", enabled: true}]')
    fi
  done

  SUPERHUMAN_CONNECTIONS="$SUPERHUMAN_ITEMS"
fi

# ═════════════════════════════════════════════════════════════════════════════
# BEAR
# iCloud container presence (sync indicator) + preferences plist (API token)
# ═════════════════════════════════════════════════════════════════════════════
BEAR_VERSION=$(app_version "/Applications/Bear.app")
BEAR_CONNECTIONS="[]"

if [[ "$BEAR_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  BEAR_ITEMS="[]"

  BEAR_ICLOUD="${USER_HOME}/Library/Mobile Documents/iCloud~net~shinyfrog~bear"
  BEAR_GROUP="${USER_HOME}/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear"
  if [[ -d "$BEAR_ICLOUD" || -d "$BEAR_GROUP" ]]; then
    BEAR_ITEMS=$(jq -cn --argjson arr "$BEAR_ITEMS" \
      '$arr + [{name: "iCloud Sync", type: "sync", enabled: true}]')
  fi

  api_token=$(/usr/bin/defaults read net.shinyfrog.bear APIToken 2>/dev/null || \
              /usr/bin/defaults read net.shinyfrog.bear bearAPIToken 2>/dev/null || true)
  if [[ -n "$api_token" ]]; then
    BEAR_ITEMS=$(jq -cn --argjson arr "$BEAR_ITEMS" \
      '$arr + [{name: "Bear API", type: "api", enabled: true}]')
  fi

  BEAR_CONNECTIONS="$BEAR_ITEMS"
fi

# ═════════════════════════════════════════════════════════════════════════════
# TICKTICK
# Preferences plist (enabled integrations) + Keychain (account token)
# ═════════════════════════════════════════════════════════════════════════════
TICKTICK_VERSION=$(app_version "/Applications/TickTick.app")
TICKTICK_CONNECTIONS="[]"

if [[ "$TICKTICK_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  TICKTICK_ITEMS="[]"

  declare -A TICKTICK_SVC_MAP
  TICKTICK_SVC_MAP["googleCalendarEnabled"]="Google Calendar"
  TICKTICK_SVC_MAP["outlookCalendarEnabled"]="Outlook Calendar"
  TICKTICK_SVC_MAP["caldavEnabled"]="CalDAV"
  TICKTICK_SVC_MAP["slackEnabled"]="Slack"
  TICKTICK_SVC_MAP["alexaEnabled"]="Alexa"
  TICKTICK_SVC_MAP["googleAssistantEnabled"]="Google Assistant"

  for pref_key in \
      "googleCalendarEnabled" "outlookCalendarEnabled" "caldavEnabled" \
      "slackEnabled" "alexaEnabled" "googleAssistantEnabled"; do
    val=$(/usr/bin/defaults read com.TickTick.task.mac "$pref_key" 2>/dev/null || echo "")
    if [[ "$val" == "1" || "$val" == "true" ]]; then
      svc_label="${TICKTICK_SVC_MAP[$pref_key]}"
      TICKTICK_ITEMS=$(jq -cn --argjson arr "$TICKTICK_ITEMS" \
        --arg name "$svc_label" \
        '$arr + [{name: $name, type: "integration", enabled: true}]')
    fi
  done

  for svc in "TickTick" "com.TickTick.task" "ticktick.com"; do
    if /usr/bin/security find-generic-password -s "$svc" &>/dev/null 2>&1; then
      TICKTICK_ITEMS=$(jq -cn --argjson arr "$TICKTICK_ITEMS" \
        '$arr + [{name: "TickTick Account", type: "account", enabled: true}]')
      break
    fi
  done

  TICKTICK_CONNECTIONS="$TICKTICK_ITEMS"
fi

# ═════════════════════════════════════════════════════════════════════════════
# PERPLEXITY
# Keychain (account/OAuth token) + preferences plist (API key)
# ═════════════════════════════════════════════════════════════════════════════
PERPLEXITY_VERSION=$(app_version "/Applications/Perplexity.app")
PERPLEXITY_CONNECTIONS="[]"

if [[ "$PERPLEXITY_VERSION" != "not_installed" && -n "$USER_HOME" ]]; then
  PERPLEXITY_ITEMS="[]"

  for svc in "Perplexity" "com.perplexity.mac" "ai.perplexity" "perplexity.ai"; do
    if /usr/bin/security find-generic-password -s "$svc" &>/dev/null 2>&1; then
      PERPLEXITY_ITEMS=$(jq -cn --argjson arr "$PERPLEXITY_ITEMS" \
        '$arr + [{name: "Perplexity Account", type: "account", enabled: true}]')
      break
    fi
  done

  for pref_domain in "ai.perplexity.mac" "com.perplexity.Perplexity" "com.perplexity.mac"; do
    api_key=$(/usr/bin/defaults read "$pref_domain" apiKey 2>/dev/null || \
              /usr/bin/defaults read "$pref_domain" pplxApiKey 2>/dev/null || true)
    if [[ -n "$api_key" ]]; then
      PERPLEXITY_ITEMS=$(jq -cn --argjson arr "$PERPLEXITY_ITEMS" \
        '$arr + [{name: "Perplexity API Key", type: "api", enabled: true}]')
      break
    fi
  done

  PERPLEXITY_CONNECTIONS="$PERPLEXITY_ITEMS"
fi

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
  --argjson  raycast_ext_names    "$RAYCAST_EXT_NAMES" \
  --arg      warp_ver             "$WARP_VERSION" \
  --argjson  warp_conns           "$WARP_CONNECTIONS" \
  --arg      vscode_ver           "$VSCODE_VERSION" \
  --argjson  vscode_conns         "$VSCODE_CONNECTIONS" \
  --arg      comet_ver            "$COMET_VERSION" \
  --argjson  comet_conns          "$COMET_CONNECTIONS" \
  --arg      superhuman_ver       "$SUPERHUMAN_VERSION" \
  --argjson  superhuman_conns     "$SUPERHUMAN_CONNECTIONS" \
  --arg      bear_ver             "$BEAR_VERSION" \
  --argjson  bear_conns           "$BEAR_CONNECTIONS" \
  --arg      ticktick_ver         "$TICKTICK_VERSION" \
  --argjson  ticktick_conns       "$TICKTICK_CONNECTIONS" \
  --arg      perplexity_ver       "$PERPLEXITY_VERSION" \
  --argjson  perplexity_conns     "$PERPLEXITY_CONNECTIONS" \
  '
  def tool($ver; $conns):
    { installed: ($ver != "not_installed"),
      version:   (if $ver == "not_installed" then null else $ver end),
      connections: $conns };

  {
    collected_at: $ts,
    device: {
      hostname:      $hostname,
      serial_number: (if $serial == "" then null else $serial end),
      os_version:    $os_version,
      current_user:  (if $current_user == "" then null else $current_user end)
    },
    tools: {
      claude:              tool($claude_ver;      $claude_conns),
      chatgpt:             tool($chatgpt_ver;     $chatgpt_conns),
      cursor:              tool($cursor_ver;      $cursor_conns),
      gemini:              tool($gemini_ver;      $gemini_conns),
      raycast:            (tool($raycast_ver;     $raycast_conns)
                           + {extensions_installed: ($raycast_ext_names | length),
                              extensions: $raycast_ext_names}),
      warp:                tool($warp_ver;        $warp_conns),
      visual_studio_code:  tool($vscode_ver;      $vscode_conns),
      comet:               tool($comet_ver;       $comet_conns),
      superhuman:          tool($superhuman_ver;  $superhuman_conns),
      bear:                tool($bear_ver;        $bear_conns),
      ticktick:            tool($ticktick_ver;    $ticktick_conns),
      perplexity:          tool($perplexity_ver;  $perplexity_conns)
    }
  }
  ')

# ═════════════════════════════════════════════════════════════════════════════
# OUTPUT + POST
# Print JSON to stdout (visible in Jamf policy log)
# POST to Okta Workflow webhook
# ═════════════════════════════════════════════════════════════════════════════
echo "$OUTPUT_JSON"

OKTA_WEBHOOK_URL="https://wellthy.workflows.okta.com/api/flo/def3267a9e480ae6a58154e7e1740eee/invoke?clientToken=06e2fee7c76c44d2720cd4ed9e53656b0cc24ca5d67a19ed865c63934e7826b2"

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
