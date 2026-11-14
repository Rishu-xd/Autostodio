"""Tests for AutoStudio Manim Renderer and Execution Sandbox."""

import os
import pytest
from core.execution_sandbox import ExecutionSandbox
from core.renderer import ManimRenderer


def test_find_scene_class_name():
    renderer = ManimRenderer()

    code1 = """
from manim import *
class IntroAnimation(Scene):
    def construct(self):
        pass
"""
    assert renderer.find_scene_class_name(code1) == "IntroAnimation"

    code2 = """
import numpy as np
def helper():
    return 42
"""
    assert renderer.find_scene_class_name(code2) is None


def test_validate_code_syntax():
    renderer = ManimRenderer()

    valid_code = """
from manim import *
class MainScene(Scene):
    def construct(self):
        dot = Dot()
        self.add(dot)
"""
    is_valid, scene_name, err = renderer.validate_code(valid_code)
    assert is_valid is True
    assert scene_name == "MainScene"
    assert err is None

    # Invalid syntax
    invalid_code = """
from manim import *
class MainScene(Scene)
    def construct(self):
"""
    is_valid, scene_name, err = renderer.validate_code(invalid_code)
    assert is_valid is False
    assert "SyntaxError" in err


def test_sandbox_catches_unsafe_code():
    sandbox = ExecutionSandbox()

    # Unsafe module import
    unsafe_import = """
import subprocess
from manim import *
class MainScene(Scene):
    def construct(self):
        subprocess.run(["ls"])
"""
    safe, violations = sandbox.inspect_code(unsafe_import)
    assert safe is False
    assert any("subprocess" in v for v in violations)

    # Unsafe function call
    unsafe_call = """
from manim import *
import os
class MainScene(Scene):
    def construct(self):
        os.system("echo hacked")
"""
    safe, violations = sandbox.inspect_code(unsafe_call)
    assert safe is False
    assert any("system" in v for v in violations)


def test_sandbox_env_strips_secrets():
    sandbox = ExecutionSandbox()
    os.environ["GEMINI_API_KEY"] = "secret_key_123"
    os.environ["OPENAI_API_KEY"] = "secret_open_ai"

    safe_env = sandbox.prepare_safe_env()

    assert "GEMINI_API_KEY" not in safe_env
    assert "OPENAI_API_KEY" not in safe_env
    assert safe_env["PYTHONUNBUFFERED"] == "1"

