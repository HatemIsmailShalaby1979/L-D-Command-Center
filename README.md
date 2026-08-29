# L&D Command Center

> **A local-first learning, career, language, and media workstation.**

L&D Command Center is a desktop-oriented toolkit powered by a local model runtime. It brings learning journeys, language practice, career-document workflows, media tools, audio production, and export capabilities into one local application.

## Capabilities

- Learning journeys with lessons, quizzes, and evaluation
- Bilingual language-learning packs and listening practice
- Resume and cover-letter workflows with inspectable changes
- Job-board search and application-package preparation
- Audio narration and two-voice podcast creation
- PDF, DOCX, PPTX, XLSX, TXT, and audio export
- Local media workspace and connector hub

## Status

**V1 ship in progress.**

- Core engines are functional
- Linux desktop packaging is verified
- Windows packaging remains pending
- Some UI rough edges remain
- Job-board production use requires appropriate API configuration
- Local LM Studio is the primary model path
- No production SaaS or autonomous-agent claim is made

## Run locally

    pip install -r requirements.txt
    python desktop-shell/app.py

Start LM Studio at http://localhost:1234/v1 with a compatible local model.

Optional audio support: pip install piper-tts

## Design principle

The Command Center is built for practical operators and learners: modest hardware, inspectable outputs, local control, and useful exports. It is a product layer in the broader Helix ecosystem—not a replacement for the governed Helix Codex core.

## Related projects

- [Helix Prime](https://github.com/HatemIsmailShalaby1979/Helix-Prime)
- [Helix Education](https://github.com/HatemIsmailShalaby1979/Helix-Education)
- [Study Studio](https://github.com/HatemIsmailShalaby1979/Study-Studio)
- [Portfolio](https://github.com/HatemIsmailShalaby1979/HatemIsmailShalaby1979)

## License

MIT