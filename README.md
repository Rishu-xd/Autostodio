# AutoStudio 🎬

AutoStudio is an autonomous, locally running, multi-agent AI video production studio. It transforms a topic, prompt, or technical concept into a researched, storyboarded, animated, reviewed, and rendered Manim educational video.

Powered by Google Gen AI (Gemini API) and Manim Community Edition, AutoStudio operates with a dual-agent pattern (Creator + Critic) across every creative phase.

---

## 🌟 Features

- **Multi-Agent Architecture**: 7 specialized agents collaborate in an automated loop:
  - **Researcher**: Analyzes topics, breaks down core concepts, analogies, and misconceptions.
  - **Research Critic**: Audits factual accuracy and educational suitability.
  - **Storyboard Planner**: Designs a scene-by-scene animation plan with narration and formulas.
  - **Storyboard Critic**: Validates visual clarity, narrative flow, and Manim feasibility.
  - **Code Generator**: Writes executable Manim Community Python code with chosen visual themes.
  - **Code Critic**: Inspects Python syntax, imports, variable scoping, and scene hygiene.
  - **Video Reviewer**: Inspects rendered video frames multimodally using Gemini vision.
- **Local Rendering**: Renders animations locally on CPU/GPU using Manim Community Edition and FFmpeg.
- **Execution Sandbox**: Static AST inspection blocks forbidden modules and system calls. Environment variables (such as API keys) are stripped before subprocess execution.
- **Resumable Pipeline**: Backed by SQLite and structured artifact storage. If interrupted, projects resume seamlessly from the last completed stage.
- **Visual Themes**: Built-in palettes including *Dark Technical*, *Minimal Scientific*, *Mathematical Whiteboard*, *Modern Educational*, and *Cinematic Abstract*.
- **Token & Cost Tracking**: Accurately tracks token usage and calculates estimated USD API costs.

---

## 📁 Project Structure

```
autostudio/
├── main.py                     # CLI entry point
├── cli.py                      # Rich terminal command interface
├── config.py                   # Centralized configuration & environment loader
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Build & pytest configuration
├── .env.example                # Example environment configuration
├── .gitignore                  # Git ignore rules
├── README.md                   # Complete documentation
│
├── agents/                     # Specialized agent modules
│   ├── base.py                 # Abstract BaseAgent foundation
│   ├── researcher.py           # Domain concept research
│   ├── research_critic.py      # Research peer review & validation
│   ├── storyboard_planner.py   # Scene-by-scene storyboard generator
│   ├── storyboard_critic.py    # Visual flow & feasibility critic
│   ├── code_generator.py       # Executable Manim code author
│   ├── code_critic.py          # AST & semantic code reviewer
│   └── video_reviewer.py       # Multimodal frame reviewer
│
├── core/                       # Studio engine & utilities
│   ├── gemini_client.py        # Centralized Google GenAI SDK wrapper
│   ├── orchestrator.py         # End-to-end pipeline coordinator
│   ├── state_manager.py        # SQLite project metadata & history
│   ├── artifact_manager.py     # Atomic writes & versioned archiving
│   ├── renderer.py             # Manim rendering manager
│   ├── video_inspector.py      # Frame extractor & probe analyzer
│   ├── execution_sandbox.py    # Subprocess safety & AST inspector
│   ├── retry_manager.py        # Revision limits & backoff tracking
│   └── visual_themes.py        # Reusable animation color themes
│
├── schemas/                    # Pydantic validation schemas
│   ├── project.py              # Configuration & metadata models
│   ├── research.py             # Research artifact models
│   ├── storyboard.py           # Storyboard & scene models
│   ├── review.py               # Critic & review models
│   └── generation.py           # Code generation artifact models
│
├── prompts/                    # Markdown system prompts for agents
│   ├── researcher.md
│   ├── research_critic.md
│   ├── storyboard_planner.md
│   ├── storyboard_critic.md
│   ├── code_generator.md
│   ├── code_critic.md
│   └── video_reviewer.md
│
├── storage/                    # Persistent storage
│   ├── autostudio.db           # SQLite database
│   └── projects/               # Per-project artifact folders
│
├── tests/                      # Automated test suite
│   ├── test_schemas.py
│   ├── test_artifacts.py
│   ├── test_orchestrator.py
│   ├── test_gemini_client.py
│   ├── test_renderer.py
│   └── test_manim_integration.py
│
└── docs/
    └── architecture.md         # Detailed architecture diagram & notes
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11 or newer (tested on Python 3.11, 3.12, 3.13, 3.14).
- [FFmpeg](https://ffmpeg.org/download.html) installed and accessible in your system `PATH`.

#### Platform Setup:
- **Windows**:
  - Install FFmpeg using winget or Chocolatey:
    ```powershell
    winget install Gyan.FFmpeg
    ```
- **Linux (Ubuntu/Debian)**:
  ```bash
  sudo apt update && sudo apt install -y ffmpeg libpango1.0-dev libcairo2-dev
  ```
- **macOS**:
  ```bash
  brew install ffmpeg pango cairo
  ```

### 2. Setup Virtual Environment & Install Dependencies

```bash
# Clone the repository and enter directory
cd autostudio

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment:
# Windows (PowerShell - if script execution is disabled, run: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned):
.venv\Scripts\Activate.ps1
# Windows (Command Prompt / cmd.exe):
.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

### 3. Configure Gemini API Key

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and set your Google Gemini API key:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

---

## 🖥️ Command-Line Interface (CLI)

AutoStudio features a Rich-powered CLI.

### Create a Project
```bash
python main.py create "Explain how gradient descent optimizes a neural network" --title "Gradient Descent Explainer" --duration 60 --style "Dark Technical"
```

Available options:
- `--title`: Custom title for the video.
- `--duration`: Target duration in seconds (default: 60).
- `--audience`: Target audience description.
- `--style`: Visual theme (`"Dark Technical"`, `"Minimal Scientific"`, `"Mathematical Whiteboard"`, `"Modern Educational"`, `"Cinematic Abstract"`).
- `--quality`: Render quality (`low`, `medium`, `high`).
- `--run`: Automatically launch the production pipeline immediately after creating.

### Run the Pipeline
```bash
python main.py run <project_id>
```

### Resume an Interrupted Project
If a pipeline stops or fails at any stage, resume picks up from the last successful stage:
```bash
python main.py resume <project_id>
```

### Render Preview
Render a fast, low-resolution preview of the generated animation code:
```bash
python main.py preview <project_id>
```

### Render Final Video
```bash
python main.py render <project_id> --quality high
```

### Inspect Reviews
View the multimodal visual review and any flagged issues:
```bash
python main.py review <project_id>
```

### List Projects
```bash
python main.py list
```

### Check Project Status & Execution History
```bash
python main.py status <project_id>
```

### Reconfigure Project Settings
```bash
python main.py configure <project_id> --duration 45 --style "Minimal Scientific"
```

---

## 📦 Project Artifact Structure

Each video production project maintains an isolated directory under `storage/projects/<project_id>/`:

```
storage/projects/<project_id>/
├── project.json                    # Project configuration and metadata
├── research/
│   ├── research.json               # Approved research artifact
│   ├── research_review.json        # Research critic review
│   └── research_history/           # Versioned history of past revisions
├── storyboard/
│   ├── storyboard.json             # Approved scene-by-scene storyboard
│   ├── storyboard_review.json      # Storyboard critic review
│   └── storyboard_history/         # Prior storyboard versions
├── src/
│   ├── main.py                     # Executable Manim Python code
│   └── code_artifact.json          # Code metadata and theme settings
├── rendering/
│   ├── logs/                       # Full rendering stdout/stderr logs
│   ├── frames/                     # Extracted frames & contact sheet
│   └── temporary/                  # Subprocess scratch space
├── reviews/
│   ├── code_review.json            # Code critic review
│   ├── video_review.json           # Multimodal visual quality review
│   └── revision_history/           # Archived reviews
└── output/
    └── final.mp4                   # Completed MP4 video
```

---

## 🔒 Execution Safety & Sandbox

AutoStudio generates and executes Python code locally. Untrusted code execution is secured via multi-layer isolation:
1. **Static AST Analysis**: The code inspector parses the Python Abstract Syntax Tree before execution, rejecting forbidden imports (`subprocess`, `socket`, `http`, `urllib`, `requests`) and dangerous built-ins (`os.system`, `eval`, `exec`).
2. **Environment Sanitization**: Sensitive environment variables (`GEMINI_API_KEY`, etc.) are stripped from the subprocess environment before rendering.
3. **Subprocess Isolation**: Animations run in a separate subprocess with a project-isolated working directory and enforced execution timeouts.

> **Security Note**: Subprocess isolation restricts accidental system access. To run in fully hostile untrusted environments, consider wrapping local execution within a containerized Docker or OS sandbox.

---

## 🧪 Testing

AutoStudio includes an extensive test suite that runs without requiring an active Gemini API key:

```bash
# Run all tests
python -m pytest -v
```

Tests include:
- `test_schemas.py`: Validation of all Pydantic models, duration checks, unique scene ID constraints.
- `test_artifacts.py`: Atomic writes, version archiving, directory tree management.
- `test_orchestrator.py`: State transitions, pipeline resumption, revision limit enforcement.
- `test_gemini_client.py`: API key validation, markdown stripping, structured response parsing, token tracking.
- `test_renderer.py`: Scene class detection, syntax error trapping, sandbox security checks.
- `test_manim_integration.py`: End-to-end local Manim rendering and OpenCV/FFmpeg frame extraction.

---

## 🛠️ Troubleshooting

### 1. `Manim` fails to render LaTeX formulas
If you use complex LaTeX in `MathTex` formulas and receive LaTeX compilation errors:
- Install a LaTeX distribution like **MiKTeX** (Windows) or **TeX Live** (Linux/macOS).
- Alternatively, standard `Text` objects render without LaTeX dependencies.

### 2. Missing `GEMINI_API_KEY`
Ensure your `.env` file exists in the project root:
```env
GEMINI_API_KEY=AIzaSy...
```
Verify your key by running:
```bash
python -c "import config; print('Configured:', config.validate_api_key())"
```

### 3. Rendering Times Out
For longer or complex animations, adjust `RENDER_TIMEOUT_SECONDS` in `.env`:
```env
RENDER_TIMEOUT_SECONDS=600
```
