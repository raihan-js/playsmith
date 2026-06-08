# Playsmith in a box — Python + Godot 4.x headless + Playsmith.
# Lets you run the full pipeline (prompt -> real Godot game -> verify) without installing Godot
# on the host. Point the LLM at any OpenAI-compatible API (an OpenAI key by default).
FROM python:3.12-slim

# Godot 4.x links a few shared libs even when run with --headless.
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget unzip ca-certificates \
        libfontconfig1 libfreetype6 libx11-6 libxcursor1 libxinerama1 \
        libxi6 libxrandr2 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Standard Godot 4.x editor binary (supports --headless). Override at build time with --build-arg.
ARG GODOT_VERSION=4.3-stable
RUN wget -q "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/Godot_v${GODOT_VERSION}_linux.x86_64.zip" -O /tmp/godot.zip \
    && unzip -q /tmp/godot.zip -d /tmp \
    && mv "/tmp/Godot_v${GODOT_VERSION}_linux.x86_64" /usr/local/bin/godot \
    && chmod +x /usr/local/bin/godot \
    && rm /tmp/godot.zip

# HTML5 export templates (only the web ones) so the web UI can export + play in the browser.
# The full .tpz is large but transient — we keep just web_* (~30MB) in the final layer.
ARG WITH_WEB_TEMPLATES=true
RUN if [ "$WITH_WEB_TEMPLATES" = "true" ]; then \
        wget -q "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/Godot_v${GODOT_VERSION}_export_templates.tpz" -O /tmp/tpl.tpz \
        && mkdir -p /root/.local/share/godot/export_templates/4.3.stable \
        && unzip -q -j /tmp/tpl.tpz "templates/web*" "templates/version.txt" -d /root/.local/share/godot/export_templates/4.3.stable/ \
        && rm -f /tmp/tpl.tpz ; \
    fi

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY playsmith ./playsmith
COPY game-skills ./game-skills
COPY config ./config
RUN pip install --no-cache-dir -e ".[web]"
EXPOSE 8000

# Generated games and installed community skills live on mounted volumes.
ENV PLAYSMITH_CONFIG=/app/config/playsmith.docker.yaml \
    HOME=/root \
    PYTHONUNBUFFERED=1
RUN mkdir -p /workspace /root/.playsmith/skills

ENTRYPOINT ["playsmith"]
CMD ["--help"]
