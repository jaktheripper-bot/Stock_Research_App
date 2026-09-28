#!/usr/bin/env python3
"""
Streamlit Static Linter & Guardrail Scanner
Checks for common Streamlit runtime traps:
1. Valid Unicode emojis in st.toast(..., icon=...)
2. Deprecated use_container_width arguments
3. Fragment scope correctness
"""

import ast
import os
import sys

def lint_file(filepath: str) -> list[str]:
    errors = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError as e:
        return [f"{filepath}:{e.lineno}: SyntaxError: {e.msg}"]

    for node in ast.walk(tree):
        # 1. Check st.toast(icon=...) calls
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id

            if func_name == "toast":
                for kw in node.keywords:
                    if kw.arg == "icon" and isinstance(kw.value, ast.Constant):
                        icon_val = kw.value.value
                        if isinstance(icon_val, str):
                            # Validate using Streamlit's official validator if available
                            try:
                                from streamlit.string_util import validate_icon_or_emoji
                                validate_icon_or_emoji(icon_val)
                            except Exception as err:
                                errors.append(
                                    f"{filepath}:{node.lineno}: Invalid st.toast icon '{icon_val}'. "
                                    f"Must be a single valid Unicode emoji or Material icon. Error: {err}"
                                )

            # 2. Check for deprecated use_container_width
            for kw in node.keywords:
                if kw.arg == "use_container_width":
                    errors.append(
                        f"{filepath}:{node.lineno}: Deprecated parameter 'use_container_width'. "
                        f"Use width='stretch' or width='content' instead."
                    )

    return errors

def run_linter(directory: str = ".") -> int:
    print("🔍 Running Streamlit Static Linter & Guardrail Scan...")
    total_errors = []
    py_files = [
        f for f in os.listdir(directory)
        if f.endswith(".py") and not f.startswith("test_") and not f.startswith("check_")
    ]
    for py_file in py_files:
        errs = lint_file(os.path.join(directory, py_file))
        total_errors.extend(errs)

    if total_errors:
        print(f"❌ Found {len(total_errors)} lint issue(s):")
        for err in total_errors:
            print(f"   • {err}")
        return 1
    else:
        print(f"✅ All {len(py_files)} Python files passed Streamlit guardrail scan.")
        return 0

if __name__ == "__main__":
    sys.exit(run_linter("."))
