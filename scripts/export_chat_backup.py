"""
Chat Transcript Backup & Markdown Exporter
===========================================
Exports the complete conversation transcript (raw JSONL + formatted Markdown)
from the Antigravity conversation log into the repository backups directory.
Supports overwriting the latest backup on demand.
"""

import os
import sys
import json
import shutil
import tarfile
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")
CONVERSATION_ID = "b8438222-9ca8-4687-a897-0574a408db2e"
SOURCE_LOG_DIR = f"/Users/lyndonpinto/.gemini/antigravity-ide/brain/{CONVERSATION_ID}/.system_generated/logs"
ARTIFACT_DIR = f"/Users/lyndonpinto/.gemini/antigravity-ide/brain/{CONVERSATION_ID}"
WORKSPACE_ROOT = "/Users/lyndonpinto/Documents/Stock_Research_App"


def export_chat(overwrite_latest: bool = False):
    now_ist = datetime.now(IST)
    chat_root = os.path.join(WORKSPACE_ROOT, "backups", "chat")
    os.makedirs(chat_root, exist_ok=True)

    if overwrite_latest:
        existing_dirs = sorted([
            d for d in os.listdir(chat_root)
            if os.path.isdir(os.path.join(chat_root, d)) and d.startswith("chat_backup_")
        ])
        if existing_dirs:
            target_folder_name = existing_dirs[-1]
            backup_dir = os.path.join(chat_root, target_folder_name)
            print(f"🔄 Overwriting existing latest chat backup: {target_folder_name}")
        else:
            ts_str = now_ist.strftime("%Y%m%d_%H%M%S")
            backup_dir = os.path.join(chat_root, f"chat_backup_{ts_str}")
            os.makedirs(backup_dir, exist_ok=True)
    else:
        ts_str = now_ist.strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(chat_root, f"chat_backup_{ts_str}")
        os.makedirs(backup_dir, exist_ok=True)

    transcript_full_path = os.path.join(SOURCE_LOG_DIR, "transcript_full.jsonl")
    transcript_compact_path = os.path.join(SOURCE_LOG_DIR, "transcript.jsonl")

    # 1. Copy raw JSONL files
    if os.path.exists(transcript_full_path):
        shutil.copy2(transcript_full_path, os.path.join(backup_dir, "transcript_full.jsonl"))
    if os.path.exists(transcript_compact_path):
        shutil.copy2(transcript_compact_path, os.path.join(backup_dir, "transcript.jsonl"))

    # 2. Parse and format Markdown
    input_file = transcript_full_path if os.path.exists(transcript_full_path) else transcript_compact_path

    md_lines = [
        f"# Conversation Transcript Backup",
        f"",
        f"- **Conversation ID:** `{CONVERSATION_ID}`",
        f"- **Backup Timestamp:** {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}",
        f"- **Source Log:** `{input_file}`",
        f"",
        f"---",
        f"",
    ]

    turn_count = 0
    with open(input_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                step = json.loads(line)
            except Exception:
                continue

            step_type = step.get("type")
            source = step.get("source")
            created_at = step.get("created_at", "")
            content = step.get("content")
            tool_calls = step.get("tool_calls", [])

            # User Turn
            if step_type == "USER_INPUT" and source == "USER_EXPLICIT":
                turn_count += 1
                clean_content = content.strip() if content else "(Empty message / attachment)"
                md_lines.append(f"## 👤 User Prompt #{turn_count}")
                if created_at:
                    md_lines.append(f"*Timestamp: {created_at}*")
                md_lines.append("")
                md_lines.append(clean_content)
                md_lines.append("")
                md_lines.append("---")
                md_lines.append("")

            # Assistant Turn
            elif step_type == "PLANNER_RESPONSE":
                # Check if this planner response had assistant textual output
                if content and content.strip():
                    md_lines.append(f"### 🤖 Assistant Response")
                    if created_at:
                        md_lines.append(f"*Timestamp: {created_at}*")
                    md_lines.append("")
                    md_lines.append(content.strip())
                    md_lines.append("")
                    md_lines.append("---")
                    md_lines.append("")
                elif tool_calls:
                    # Log significant tool actions taken
                    action_summaries = []
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        name = fn.get("name", "tool")
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                pass
                        summary = args.get("toolSummary") or args.get("toolAction") or name
                        action_summaries.append(f"`{name}`: {summary}")
                    if action_summaries:
                        md_lines.append(f"> ⚙️ *Tool Actions executed:* {', '.join(action_summaries)}")
                        md_lines.append("")

    md_content = "\n".join(md_lines)

    # Write formatted Markdown into backup dir
    md_file_path = os.path.join(backup_dir, "chat_history.md")
    with open(md_file_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Also copy to Artifact directory so it is viewable directly in IDE
    artifact_md_path = os.path.join(ARTIFACT_DIR, "chat_history_backup.md")
    with open(artifact_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # 3. Create / Overwrite .tar.gz archive
    tar_path = f"{backup_dir}.tar.gz"
    if os.path.exists(tar_path):
        try:
            os.remove(tar_path)
        except Exception:
            pass

    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(backup_dir, arcname=os.path.basename(backup_dir))

    print(f"✅ Chat backup successfully {'overwritten' if overwrite_latest else 'created'}!")
    print(f"📁 Directory: {backup_dir}")
    print(f"📦 Archive:   {tar_path}")
    print(f"📄 Markdown:  {md_file_path}")
    print(f"🎨 Artifact:  {artifact_md_path}")
    print(f"📊 Total User Prompts Captured: {turn_count}")


if __name__ == "__main__":
    overwrite = any(arg in sys.argv for arg in ("--overwrite-latest", "--overwrite", "-o"))
    export_chat(overwrite_latest=overwrite)
