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

## Instalação universal

O Vector possui um único instalador multiplataforma. O mesmo comando funciona em
Linux, macOS, Windows, PowerShell, CMD e WSL, desde que Python 3 esteja disponível:

```text
python -c "import urllib.request; exec(compile(urllib.request.urlopen('https://raw.githubusercontent.com/stoltembergg-png/hermes-agent/main/scripts/install-vector.py').read(), 'install-vector.py', 'exec'))"
```

O instalador detecta o sistema operacional e:

- usa o instalador nativo do Hermes quando o CLI ainda não existe;
- instala o backend e o pacote Vector em `HERMES_HOME`;
- compila o plugin desktop quando Node.js 22+ está disponível;
- habilita `vector-channels`;
- instala o hook de atualização automaticamente;
- não exige comandos adicionais de `git`, `pip`, `npm` ou `curl`.

Para validar sem alterar o sistema:

```text
python -c "import urllib.request; exec(compile(urllib.request.urlopen('https://raw.githubusercontent.com/stoltembergg-png/hermes-agent/main/scripts/install-vector.py').read(), 'install-vector.py', 'exec'))" --dry-run
```

O instalador também pode ser executado a partir de um checkout local:

```text
python scripts/install-vector.py --source .
```

Após a instalação, reinicie o Hermes. O hook instalado reexecuta o mesmo
instalador automaticamente quando `hermes update` remover ou substituir o plugin.

### Desenvolvimento

A instalação de desenvolvimento é deliberadamente separada da instalação de usuário:

```text
git clone https://github.com/stoltembergg-png/hermes-agent.git
cd hermes-agent
uv sync --all-extras
```

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
