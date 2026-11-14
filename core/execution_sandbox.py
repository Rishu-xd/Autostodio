"""Execution Sandbox Abstraction for AutoStudio.

Runs untrusted generated Python code in an isolated subprocess with strict safety checks:
- Project-isolated working directory
- Cleaned environment (GEMINI_API_KEY and secrets stripped)
- Static AST inspection against forbidden syscalls and unsafe imports
- Subprocess timeout enforcement
- Explicit security documentation
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import SANDBOX_RESTRICTED_MODE


class SandboxSecurityViolation(Exception):
    """Raised when generated code contains dangerous constructs."""
    pass


# Forbidden modules in generated Manim scripts
FORBIDDEN_MODULES = {
    "subprocess",
    "socket",
    "http",
    "urllib",
    "requests",
    "httpx",
    "ctypes",
    "pty",
    "paramiko",
    "telnetlib",
    "ftplib",
    "webbrowser",
}

# Forbidden function calls
FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "__import__",
    "compile",
    "open_new",
    "open_new_tab",
}

# Forbidden attributes on os/sys
FORBIDDEN_ATTRIBUTES = {
    "system",
    "popen",
    "spawn",
    "fork",
    "kill",
    "unlink",
    "remove",
    "rmdir",
}


class CodeSafetyInspector(ast.NodeVisitor):
    """Inspects AST of generated Python code for security violations."""

    def __init__(self):
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_module = alias.name.split(".")[0]
            if base_module in FORBIDDEN_MODULES:
                self.violations.append(f"Forbidden module import: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_module = node.module.split(".")[0]
            if base_module in FORBIDDEN_MODULES:
                self.violations.append(f"Forbidden module import: from '{node.module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Check direct calls like eval(...) or exec(...)
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                self.violations.append(f"Forbidden built-in call: '{node.func.id}()'")
        # Check attribute calls like os.system(...)
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_ATTRIBUTES:
                if isinstance(node.func.value, ast.Name) and node.func.value.id in ("os", "sys", "shutil"):
                    self.violations.append(f"Forbidden system call: '{node.func.value.id}.{node.func.attr}()'")
        self.generic_visit(node)


class ExecutionSandbox:
    """Manages secure execution of generated Python scripts."""

    def __init__(self, restricted_mode: bool = SANDBOX_RESTRICTED_MODE):
        self.restricted_mode = restricted_mode

    def inspect_code(self, code_str: str) -> Tuple[bool, List[str]]:
        """Perform static AST inspection of code for safety."""
        try:
            tree = ast.parse(code_str)
        except SyntaxError as e:
            return False, [f"SyntaxError during AST inspection: {e}"]

        inspector = CodeSafetyInspector()
        inspector.visit(tree)

        if inspector.violations:
            return False, inspector.violations
        return True, []

    def prepare_safe_env(self) -> Dict[str, str]:
        """Create a clean environment for the subprocess, stripping sensitive credentials."""
        safe_env = dict(os.environ)

        # Strip API keys and sensitive tokens
        sensitive_keys = [
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "GITHUB_TOKEN",
        ]
        for key in sensitive_keys:
            safe_env.pop(key, None)

        # Ensure Python path includes current workspace
        safe_env["PYTHONUNBUFFERED"] = "1"
        return safe_env

    def run_process(
        self,
        command: List[str],
        working_dir: Path,
        timeout_seconds: int = 300,
        log_file: Optional[Path] = None,
    ) -> Tuple[int, str, str]:
        """Execute a command in a child subprocess within the project-specific working directory."""
        working_dir.mkdir(parents=True, exist_ok=True)
        env = self.prepare_safe_env()

        stdout_chunks: List[str] = []
        stderr_chunks: List[str] = []

        try:
            process = subprocess.Popen(
                command,
                cwd=str(working_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            stdout, stderr = process.communicate(timeout=timeout_seconds)
            exit_code = process.returncode

            if log_file:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write(f"COMMAND: {' '.join(command)}\n")
                    f.write(f"CWD: {working_dir}\n")
                    f.write(f"EXIT CODE: {exit_code}\n")
                    f.write("\n--- STDOUT ---\n")
                    f.write(stdout)
                    f.write("\n--- STDERR ---\n")
                    f.write(stderr)

            return exit_code, stdout, stderr

        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            msg = f"Execution timed out after {timeout_seconds} seconds."
            if log_file:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n[SANDBOX TIMEOUT] {msg}\n")
            return -1, stdout, f"{stderr}\n{msg}"

        except Exception as e:
            return -1, "", str(e)

