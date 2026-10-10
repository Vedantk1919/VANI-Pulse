#!/usr/bin/env bash
# Start the demo dashboard. Keys are typed in hidden and only live in this process (never saved).
#   SARVAM_API_KEY        sk_ developer key (speech-to-text, LLM, voice: hands-free + push-to-talk modes)
#   SARVAM_AGENT_API_KEY  Agents API key from indus.sarvam.ai (Sarvam live runtime mode); Enter to skip
cd "$(dirname "$0")"
[ -z "$SARVAM_API_KEY" ] && { read -rsp "Sarvam sk_ developer key: " SARVAM_API_KEY; echo; }
[ -z "$SARVAM_AGENT_API_KEY" ] && { read -rsp "Sarvam Agents API key (Enter to skip): " SARVAM_AGENT_API_KEY; echo; }
export SARVAM_API_KEY SARVAM_AGENT_API_KEY
fuser -k 8601/tcp 8602/tcp 8603/tcp 2>/dev/null
echo "Dashboard: http://localhost:8601/?p=8   (use localhost so the microphone works)"
exec .venv/bin/streamlit run app.py --server.port 8601 --server.address 0.0.0.0 --server.headless true
