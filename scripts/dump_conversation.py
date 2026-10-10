#!/usr/bin/env python3
"""
Conversation Dump & Session Archiver.

Dumps agent session transcripts from the IDE brain log into a standardized,
human-readable Markdown dossier and raw JSONL format under backups/conversations/
to maintain an auditable session ledger for cross-session continuity.
"""

import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_CONV_DIR = os.path.join(ROOT_DIR, "backups", "conversations")

def format_timestamp_ist(ts_str: str) -> str:
    if not ts_str:
        return "Unknown Time"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        return ts_str

def parse_transcript(transcript_path: str):
    turns = []
    current_turn = None

    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                src = entry.get("source")
                typ = entry.get("type")
                content = entry.get("content")
                ts = entry.get("created_at")

                if src == "USER_EXPLICIT" and typ == "USER_INPUT":
                    req_match = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content or "", re.DOTALL)
                    clean_req = req_match.group(1).strip() if req_match else (content or "").strip()
                    
                    if current_turn:
                        turns.append(current_turn)
                    current_turn = {
                        "timestamp": ts,
                        "formatted_time": format_timestamp_ist(ts),
                        "user_request": clean_req,
                        "assistant_responses": [],
                        "tool_calls": []
                    }
                elif current_turn and src == "MODEL" and typ == "PLANNER_RESPONSE":
                    if content and content.strip():
                        current_turn["assistant_responses"].append(content.strip())
                    for tc in entry.get("tool_calls", []):
                        name = tc.get("name")
                        if name and name not in current_turn["tool_calls"]:
                            current_turn["tool_calls"].append(name)
            except Exception:
                pass

    if current_turn:
        turns.append(current_turn)

    return turns

def generate_markdown(turns, conversation_id: str, date_str: str) -> str:
    lines = [
        f"# Session Conversation Dossier: {date_str}",
        f"**Conversation ID:** `{conversation_id}`  ",
        f"**Archived At:** {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}  ",
        f"**Total Conversation Turns:** {len(turns)}  ",
        "",
        "---",
        "",
        "## Executive Summary of Session",
        "This session archive preserves user prompts, engineering deliberations, technical audits, and final assistant responses to provide complete context continuity prior to initiating new development sessions.",
        "",
        "---",
        "",
        "## Complete Turn-by-Turn Dialogue Ledger",
        ""
    ]

    for idx, turn in enumerate(turns, start=1):
        lines.append(f"### Turn {idx} ({turn['formatted_time']})")
        lines.append(f"#### 👤 User Prompt")
        lines.append(f"> {turn['user_request']}")
        lines.append("")
        
        if turn["tool_calls"]:
            tools_str = ", ".join(f"`{t}`" for t in turn["tool_calls"])
            lines.append(f"**Tools Executed:** {tools_str}  ")
            lines.append("")

        lines.append(f"#### 🤖 Assistant Response")
        if turn["assistant_responses"]:
            # If multiple responses (e.g. progress updates + final response), show final with expanders
            if len(turn["assistant_responses"]) == 1:
                lines.append(turn["assistant_responses"][0])
            else:
                lines.append("**Final Output & Resolution:**")
                lines.append("")
                lines.append(turn["assistant_responses"][-1])
                lines.append("")
                lines.append("<details><summary><b>View Intermediate Progress Updates (" + str(len(turn['assistant_responses']) - 1) + " updates)</b></summary>")
                lines.append("")
                for p_idx, p_text in enumerate(turn["assistant_responses"][:-1], start=1):
                    lines.append(f"**Update {p_idx}:**")
                    lines.append(p_text)
                    lines.append("")
                lines.append("</details>")
        else:
            lines.append("*(In progress / awaiting response)*")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)

def update_index(backup_dir: str):
    index_file = os.path.join(backup_dir, "INDEX.md")
    
    entries = []
    for f in sorted(os.listdir(backup_dir)):
        if f.startswith("session_") and f.endswith(".md"):
            path = os.path.join(backup_dir, f)
            with open(path, "r", encoding="utf-8") as fp:
                first_line = fp.readline().strip().replace("# ", "")
            entries.append((f, first_line))

    content = [
        "# 📚 Historical Conversation Archive & Session Ledger",
        "",
        "This directory stores complete chronological conversation dossiers and transcripts across development sessions. Review the relevant session files prior to starting each new prompt or sprint.",
        "",
        "## Available Session Archives",
        ""
    ]

    for filename, title in reversed(entries):
        content.append(f"- [{title}](./{filename})")

    content.append("")
    content.append("---")
    content.append("## Pre-Session Quick Reference")
    content.append("Prior to starting each session, consult:")
    content.append("1. The latest `session_*.md` file above for recent decisions, completed tasks, and runtime metrics.")
    content.append("2. [`docs/Site Objective Comparison Analysis.md`](../../docs/Site%20Objective%20Comparison%20Analysis.md) for macro strategic positioning & SEBI constraints.")
    content.append("3. [`docs/competitive_analysis_baseline_and_action_plan.md`](../../docs/competitive_analysis_baseline_and_action_plan.md) for prioritized multi-asset milestones.")
    content.append("4. [`AGENTS.md`](../../AGENTS.md) for mandatory backup protocols, zero-hallucination rules, and entity hygiene.")
    content.append("")

    with open(index_file, "w", encoding="utf-8") as fp:
        fp.write("\n".join(content))

def main():
    conv_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CONVERSATION_ID", "7563b837-aa20-4a95-aed0-32af746d2010")
    session_tag = sys.argv[2] if len(sys.argv) > 2 else "msme_ingestion_and_multi_asset_platform"
    session_title = sys.argv[3] if len(sys.argv) > 3 else "MSME Ingestion, Mutual Fund Top 50, Render Hardening & Vestnomics Domain"
    
    app_data_dir = os.path.expanduser("~/.gemini/antigravity-ide")
    logs_dir = os.path.join(app_data_dir, "brain", conv_id, ".system_generated", "logs")
    transcript_full = os.path.join(logs_dir, "transcript_full.jsonl")
    transcript_compact = os.path.join(logs_dir, "transcript.jsonl")
    transcript_path = transcript_full if os.path.exists(transcript_full) else transcript_compact

    if not os.path.exists(transcript_path):
        print(f"❌ Transcript file not found at: {transcript_path}")
        return 1

    os.makedirs(BACKUP_CONV_DIR, exist_ok=True)
    date_str = datetime.now(IST).strftime("%Y%m%d")
    time_str = datetime.now(IST).strftime("%H%M%S")

    md_filename = f"session_{date_str}_{time_str}_{session_tag}.md"
    jsonl_filename = f"session_{date_str}_{time_str}_raw_transcript.jsonl"

    md_path = os.path.join(BACKUP_CONV_DIR, md_filename)
    jsonl_path = os.path.join(BACKUP_CONV_DIR, jsonl_filename)

    # 1. Copy raw JSONL
    with open(transcript_path, "r", encoding="utf-8") as src, open(jsonl_path, "w", encoding="utf-8") as dst:
        dst.write(src.read())

    # 2. Generate formatted Markdown
    turns = parse_transcript(transcript_path)
    md_content = generate_markdown(turns, conv_id, f"{date_str} ({session_title})")
    with open(md_path, "w", encoding="utf-8") as fp:
        fp.write(md_content)

    # 3. Update master index
    update_index(BACKUP_CONV_DIR)

    print(f"✅ Successfully archived session to:")
    print(f"   • Markdown Dossier: backups/conversations/{md_filename}")
    print(f"   • Raw Transcript:   backups/conversations/{jsonl_filename}")
    print(f"   • Master Index:     backups/conversations/INDEX.md")
    return 0

if __name__ == "__main__":
    sys.exit(main())
