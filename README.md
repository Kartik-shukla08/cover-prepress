# Markee Books — Cover Prepress Skill & Studio

Standalone repository containing:
1. **Markee Books Cover Studio (`mbooks.studio.server:app`)**: Interactive Canva-style cover prepress web editor, ready for 1-click deployment on **Railway**.
2. **`cover-prepress` Cross-Harness AI Skill (`SKILL.md` + `mbooks` CLI)**: Deterministic cover calculation, 3-panel wrap segmentation, spine crease detection, luminance glyph optical centering, diagnostic proofing, and PDF/X export across **Amazon KDP**, **IngramSpark**, and **Lulu** for **Antigravity**, **Claude Code**, and **OpenAI Codex**.

---

## 1. Install the AI Skill & CLI (For Staff Using Antigravity, Claude Code, or Codex)

Run this **single command** in PowerShell or Terminal:

```bash
pip install git+https://github.com/Kartik-shukla08/cover-prepress.git && mbooks install-skill
```

This installs the `mbooks` CLI and registers the `cover-prepress` skill globally across:
- **Google Antigravity:** `~/.gemini/config/skills/cover-prepress/SKILL.md`
- **Claude Code:** `~/.claude/skills/cover-prepress/SKILL.md`
- **OpenAI Codex:** `~/.codex/skills/cover-prepress/SKILL.md`

Alternatively, install via the `skills` CLI:

```bash
npx skills add Kartik-shukla08/cover-prepress --skill cover-prepress -g
```

---

## 2. Deploy Cover Studio to Railway (For Non-AI Staff)

This repository includes a root `Dockerfile` and `railway.toml` configured out of the box:
1. Connect this GitHub repository to a **Railway** project.
2. Railway automatically builds the container and starts:
   ```bash
   uvicorn mbooks.studio.server:app --host 0.0.0.0 --port $PORT
   ```
3. Generate a public domain in Railway — your staff can open the URL in any browser to visually upload, split, crop, resize, and export print-ready cover PDFs.

To run Cover Studio locally:
```bash
mbooks cover-studio --host 127.0.0.1 --port 8080
```
