# AI Remediation Control Plane — single container: API + worker + built dashboard.
# Claude Code inside a container cannot use the macOS keychain login: provide ANTHROPIC_API_KEY
# or CLAUDE_CODE_OAUTH_TOKEN (`claude setup-token`) and GITHUB_TOKEN via the environment.

FROM node:22-bookworm-slim AS ui
WORKDIR /src/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim-bookworm
ARG HELM_VERSION=v3.16.2
ARG KUBECONFORM_VERSION=v0.6.7
ARG TARGETARCH=amd64
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates gnupg openssh-client \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /usr/share/keyrings/githubcli.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends gh nodejs \
 && curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${TARGETARCH}.tar.gz" | tar -xz --strip-components=1 -C /usr/local/bin "linux-${TARGETARCH}/helm" \
 && curl -fsSL "https://github.com/yannh/kubeconform/releases/download/${KUBECONFORM_VERSION}/kubeconform-linux-${TARGETARCH}.tar.gz" | tar -xz -C /usr/local/bin kubeconform \
 && npm install -g @anthropic-ai/claude-code \
 && pip install --no-cache-dir uv \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 rcp
WORKDIR /app
COPY --chown=rcp backend/pyproject.toml backend/uv.lock backend/
RUN cd backend && uv sync --frozen --no-dev --python /usr/local/bin/python3.12
COPY --chown=rcp . .
COPY --from=ui --chown=rcp /src/frontend/dist frontend/dist
USER rcp
ENV DATA_DIR=/data API_HOST=0.0.0.0 VALIDATOR_PYTHON=/app/backend/.venv/bin/python \
    GIT_REMOTE_TEMPLATE=https://github.com/{repo}.git PATH=/app/backend/.venv/bin:$PATH
RUN git config --global credential.helper '!f() { echo username=x-access-token; echo "password=${GITHUB_TOKEN}"; }; f'
EXPOSE 8000
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
