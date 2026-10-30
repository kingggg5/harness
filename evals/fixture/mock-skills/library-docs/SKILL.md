---
name: library-docs
description: "Version-correct library and standard-library API documentation lookup. Use before relying on how a library, framework or standard-library API behaves."
---

# Library Docs

1. Identify the exact library or module and the installed version (`python -c "import sys; print(sys.version)"`, package `__version__`).
2. Confirm the behavior you rely on from the installed documentation (`python -c "import mod; help(mod.name)"`) or installed source.
3. End your report with one line per lookup: `docs: <module> <version> — <fact relied on>`.
