# AutoStudio Architecture Overview

AutoStudio is an autonomous, multi-agent AI video production studio that turns a prompt or educational topic into a researched, storyboarded, animated, reviewed, and locally rendered Manim educational video.

---

## 1. Multi-Agent Pipeline

AutoStudio employs a dual-agent pattern (Creator + Critic) across every creative phase to ensure rigor, factual correctness, and aesthetic quality:

```
+-------------------------------------------------------------------------------+
|                             USER PROMPT OR TOPIC                              |
+-------------------------------------------------------------------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |       Agent A: RESEARCHER         |
                     +-----------------------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |     Agent B: RESEARCH CRITIC      |<----+
                     +-----------------------------------+     | (Revisions)
                                       |                       |
                               [Score >= 80?] -----------------+
                                       |
                                       v
                     +-----------------------------------+
                     |   Agent C: STORYBOARD PLANNER     |
                     +-----------------------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |   Agent D: STORYBOARD CRITIC      |<----+
                     +-----------------------------------+     | (Revisions)
                                       |                       |
                               [Score >= 80?] -----------------+
                                       |
                                       v
                     +-----------------------------------+
                     |     Agent E: CODE GENERATOR       |
                     +-----------------------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |       Agent F: CODE CRITIC        |<----+
                     +-----------------------------------+     | (Revisions)
                                       |                       |
                               [Score >= 80?] -----------------+
                                       |
                                       v
                     +-----------------------------------+
                     |   LOCAL RENDERER (Manim CE)       |
                     +-----------------------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |     VIDEO INSPECTOR & PROBER      |
                     | (Frame extraction & Contact Sheet)|
                     +-----------------------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |     Agent G: VIDEO REVIEWER       |
                     |  (Multimodal Visual Frame Review) |
                     +-----------------------------------+
                                       |
                             [Visual Quality OK?]
                              /                 \
                          (Yes)                 (No, auto-revise)
                            /                     \
                           v                       v
                   +---------------+        Back to CODE GENERATOR
                   |   FINAL MP4   |
                   +---------------+
```

---

## 2. Core Subsystems

### Centralized Gemini Client (`core/gemini_client.py`)
- Official `google-genai` Python SDK (`from google import genai`).
- Structured JSON output validation directly mapped to Pydantic models.
- Multimodal capability: passes extracted video frames directly to Gemini for inspection.
- Exponential backoff with random jitter for transient errors (429, 500, 503).
- Token usage and cost tracking in USD per project.

### State & Execution Persistence (`core/state_manager.py`)
- Local SQLite database (`storage/autostudio.db`).
- Tracks projects, stage attempts, execution durations, and errors.
- Allows pipeline execution to be interrupted and cleanly resumed from the last completed stage.

### Project Artifact Manager (`core/artifact_manager.py`)
- Isolated directory structure per project:
  - `storage/projects/<project_id>/`
    - `project.json`
    - `research/` (research.json, history)
    - `storyboard/` (storyboard.json, history)
    - `src/` (main.py, code_artifact.json)
    - `rendering/` (logs, frames, temporary files)
    - `reviews/` (code_review.json, video_review.json, history)
    - `output/` (final.mp4)
    - `metadata/` (execution.json, usage.json)
- Atomic file writes using temporary swap files.
- Version archiving before replacing approved artifacts.

### Execution Sandbox (`core/execution_sandbox.py`)
- Untrusted code safety:
  - Subprocess isolation with project-specific working directory.
  - Strips API keys (`GEMINI_API_KEY`, etc.) from environment before rendering.
  - AST static analysis: blocks dangerous imports (`subprocess`, `socket`, `urllib`, `requests`) and syscalls (`os.system`, `eval`, `exec`).
  - Execution timeouts to prevent infinite loops.

### Video Inspector (`core/video_inspector.py`)
- Uses OpenCV and FFmpeg/ffprobe to probe video streams.
- Extracts representative frames at key intervals.
- Compiles contact sheet grids for fast visual overview.
- Flags blank, zero-byte, or abnormally short videos.

### Visual Themes System (`core/visual_themes.py`)
Predefined palettes and visual themes:
- **Dark Technical**: Deep slate navy background with high-contrast cyan, violet, and emerald accents.
- **Minimal Scientific**: Refined 3Blue1Brown academic aesthetic.
- **Mathematical Whiteboard**: Deep forest-green blackboard with pastel chalk colors.
- **Modern Educational**: Inviting, warm space-blue with amber, mint, and coral.
- **Cinematic Abstract**: AMOLED black with vivid neon gradients.

