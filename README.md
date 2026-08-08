#                Vector Agent ☤

**Multi-agent orchestration layer for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Vector é um projeto pessoal por [Gabriel Stoltemberg](https://github.com/stoltembergg-png) que adiciona conversação multi-agente ao Hermes — agentes conversam entre si em canais, despacham mensagens com menções `@handle`, e cada agente pode ter seu próprio modelo e provider.

---

## Arquitetura

```
vector/                    — núcleo do projeto (service, runtime, dispatcher, store)
  src/vector/
    service.py            — VectorService (single source of truth)
    runtime.py            — AgentRuntime wrapping delegate_task
    dispatcher.py         — menção parsing + recursion guard
    store.py              — SQLite + FTS5 channel/agent/message store
    cli.py                — CLI com argparse + REPL
  tests/                  — test_pr_001 a test_pr_013 (contrato por PR)

plugins/vector-channels/  — backend FastAPI proxy para o desktop
  dashboard/plugin_api.py — rotas REST sob /api/plugins/vector-channels/

apps/desktop/src/plugins/vector-channels/  — UI React/TypeScript
  api.ts                  — cliente REST tipado
  plugin.tsx              — sidebar, canais, mensagens, modais
  vector-channels.css     — estilos
```

O core do Hermes permanece upstream-compatible. Todo o trabalho vive em `vector/`, `plugins/`, e `apps/desktop/src/plugins/`.

---

## Install Vector Plugin

The vector-channels plugin ships inside this repo. Install it with one command:

```bash
curl -fsSL https://raw.githubusercontent.com/stoltembergg-png/hermes-agent/main/scripts/install-vector.sh | bash
```

This auto-installs Hermes Agent, Python 3.11+, Node.js 22+, and git if missing, then installs the vector-channels plugin (backend + frontend + tests).

### Updating the plugin after Hermes updates

Hermes has a built-in updater (`hermes update`) that can remove the plugin. To avoid a reinstall loop, the vector plugin uses two strategies:

**Option A: Hermes hooks (recommended)**

Add a post-update hook that re-installs the plugin automatically:

```bash
mkdir -p ~/.hermes/hooks
cat > ~/.hermes/hooks/post-update.sh << 'HOOK'
#!/usr/bin/env bash
# Re-install vector plugin after Hermes update
bash "$(dirname "$0")/../plugins/vector-channels/install-vector.sh" 2>/dev/null || \
  curl -fsSL https://raw.githubusercontent.com/stoltembergg-png/hermes-agent/main/scripts/install-vector.sh | bash
HOOK
chmod +x ~/.hermes/hooks/post-update.sh
```

**Option B: Manual re-run**

After any `hermes update`, re-run:

```bash
curl -fsSL https://raw.githubusercontent.com/stoltembergg-png/hermes-agent/main/scripts/install-vector.sh | bash
```

### Development setup

```bash
# Clone + venv + dependências
git clone https://github.com/stoltembergg-png/hermes-agent.git
cd hermes-agent
python3.11 -m venv venv && source venv/bin/activate
pip install -e '.[all]'

# Build web UI
cd web && npm install && npm run build && cd ..

# Rodar
hermes serve     # backend + API
hermes desktop   # app desktop (Electron)
```

<details>
<summary>Windows (PowerShell)</summary>

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

Instala sob `%LOCALAPPDATA%\hermes`. Veja `scripts/install.ps1` para o script completo.
</details>

### Variáveis necessárias

```
~/.hermes/.env:
  NVIDIA_API_KEY=...        (ou OPENROUTER_API_KEY=...)
  TELEGRAM_BOT_TOKEN=...    (opcional — gateway Telegram)
  GITHUB_TOKEN=...          (opcional — skills hub + PRs)
```

---

## Roadmap

| PR | Título | Status |
|---|---|---|
| 001–010 | Agent profiles, mention parser, channel store, runtime, dispatcher, CLI, desktop panel, gateway API, E2E tests, desktop E2E | ✅ Merged |
| 011 | Channel selection + message display | ✅ Merged |
| 012 | Error parsing + clean error display | ✅ Merged |
| 013 | Provider/model picker in Add Agent modal | ✅ Merged (#27) |
| 014 | Visible agent list in sidebar | 🔄 Em implementação |
| 015 | Sidebar button icons + UX clarity | ⏳ Draft |
| 016 | Delete agent + delete channel backend | ⏳ Draft |
| 017 | Delete agent + delete channel frontend | ⏳ Draft |
| 018 | Channel member list + add/remove members | ⏳ Draft |
| 019 | Message timestamps + author avatars | ⏳ Draft |
| 020 | Edit agent profile — system prompt, model, provider | ⏳ Draft |
| 021 | Inject real delegate_task for LLM responses | ⏳ Draft |
| 022 | Register hermes vector CLI subcommand | ⏳ Draft |
| 023 | Config schema for vector namespace in config.yaml | ⏳ Draft |
| 024 | WebSocket live events for real-time updates | ⏳ Draft |

**Estratégia:** 1 PR a cada 3 horas (cron automatizado). Cada PR deve ter implementação real e CI verde antes do merge.

---

## Changelog

### v0.2.0 (2026-08-06)
- **PR-013**: Provider/model picker no AddAgentModal — dropdowns de provider e model filtrados do catálogo do Hermes, seção avançada colapsável
- **PR-012**: Error parsing + clean error display no vector API client
- **PR-011**: Channel selection + message display corrigidos
- **Contribuidor**: `stoltembergg-png` registrado no repo

### v0.1.0 (2026-08-05)
- **PR-010**: Desktop E2E — plugin_api backend, relative paths, UX fixes
- **PR-009**: Vector gateway API + service layer
- **PR-008**: E2E smoke tests for full stack
- **PR-007**: Desktop mention panel plugin
- **PR-006**: CLI com argparse + REPL
- **PR-005**: Channel dispatcher for inter-agent conversation
- **PR-004**: Agent runtime wrapping delegate_task
- **PR-003**: Channel store com SQLite + FTS5
- **PR-002**: Mention parser
- **PR-001**: Agent profile schema

### v0.0.1 (2026-08-04)
- Consolidação do projeto vector no monorepo
- PERSONAL.md estabelecendo propósito e políticas

---

## Infra automatizada

| Componente | Frequência | Descrição |
|---|---|---|
| Vector PR Attack | 3h | Implementa o próximo PR draft da roadmap automaticamente |
| Skill Auto-Evolution | 12h | Evolui skills do Hermes com GLM-5.2 via NVIDIA NIM (MIPROv2) |
| disk-cleanup plugin | contínuo | Limpeza automática de disco |

---

## Upstream

Baseado em [Hermes Agent](https://github.com/NousResearch/hermes-agent) pela [Nous Research](https://nousresearch.com). Licença MIT.

- **Não é um fork** — é uma cópia de referência independente
- O core do Hermes permanece compatível com o upstream
- Todo o trabalho do vector vive em `vector/`, `plugins/`, e `apps/desktop/src/plugins/`
- Rebase periódico com `NousResearch/hermes-agent` `main`

## Contato

Gabriel Stoltemberg — [GitHub](https://github.com/stoltembergg-png)
