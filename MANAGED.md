# Parte 2 — Do "Unmanaged" ao "Managed" (Entra Agent ID + Observability)

> **English TL;DR** — Part 1 registered a Google Vertex/ADK agent into Microsoft
> Agent 365 via Registry sync (it shows as *Unmanaged*). Part 2 makes it *Managed*:
> using the **Agent 365 SDK + `a365` CLI**, we give the agent a first-class
> **Microsoft Entra Agent ID (blueprint)** and add **Observability** instrumentation
> to the code — **without touching `agent.py`**. Governance (the Entra identity)
> works on **E5 + Entra ID P2**; telemetry **ingestion** requires **Agent 365 /
> M365 E7**.

---

## Visão geral

No Registry sync (Parte 1), o agente do Vertex aparece como **Unmanaged** —
descoberto, mas sem identidade nem políticas. Aqui a gente cruza a fronteira: dá
ao agente uma **identidade própria no Microsoft Entra** (o *blueprint* / Entra
Agent ID) e instrumenta **observability**, usando o **Agent 365 SDK** + o
**`a365` CLI**.

**A distinção que confunde todo mundo:** o **Agent 365 SDK** *aprimora* um agente
que você já tem (identidade, observabilidade, Work IQ tools) — ele **não** reescreve
nem hospeda o agente. É **diferente** do *Microsoft 365 Agents SDK* (que constrói e
hospeda agentes). Para um agente ADK/Gemini rodando no Vertex, o SDK certo é o
**Agent 365 SDK**.

---

## Pré-requisitos

- **Microsoft Entra Global Administrator** no tenant (para o admin consent).
- Inscrição no **Frontier Preview Program** (o `a365` valida; obrigatória para a
  camada *AI teammate*).
- Ferramentas: **.NET**, **Agent 365 CLI (`a365`)**, **Azure CLI**.
- O agente já **registrado via Registry sync** (Parte 1).
- **Licenciamento (importante):**
  - **Identidade + governança** → funcionam com **E5 + Entra ID P2**.
  - **Ingestão de telemetria (Observability ao vivo)** → requer **Agent 365 /
    M365 E7**. Sem isso, o pipeline existe mas a telemetria é **descartada em
    silêncio**.

---

## Passo a passo (AI-guided ou manual)

A Microsoft oferece um **AI-guided setup** (`aka.ms/agent365enable`) que um agente
de código (GitHub Copilot em *Agent mode*) executa. Por baixo, os comandos do
`a365` são estes:

```bash
# 1) Autenticar no tenant CORRETO (cuidado em máquina corporativa: use o tenant do
#    Agent 365, não o corp). Confirme sempre.
az login --tenant <TENANT_ID>
az account show          # confira tenantId e o usuário

# 2) Checar pré-requisitos (.NET, a365, Azure CLI, Frontier)
a365 setup requirements

# 3) Criar a identidade do agente (blueprint).
#    --no-endpoint: o agente roda no Vertex, não é um endpoint de mensageria do
#    Teams -> cria SÓ a identidade, sem callback de bot.
a365 setup blueprint --agent-name "my-adk-agent" --no-endpoint

# 4) Conceder Observability (S2S / application).
#    No preview NÃO existe flag "só observability": a via 'bot' entrega o
#    OtelWrite application-level (no bundle vêm Bot API + Power Platform).
a365 setup permissions bot --agent-name "my-adk-agent"
#    -> exige ADMIN CONSENT tenant-wide (você é Global Admin)
```

Para a **ingestão de telemetria via S2S** de um agente ADK (que **não** roda o
runtime do M365 Agents SDK), cria-se um **app padrão no Entra** com o role
`Agent365.Observability.OtelWrite` (Application) + client-credentials (MSAL). O
*client secret* desse app é escrito direto no `.env` (**nunca** commitado).

---

## Recursos criados (exemplo — os seus IDs serão diferentes)

| Item | Exemplo |
|---|---|
| Blueprint app (client) ID | `<BLUEPRINT_APP_ID>` |
| Blueprint service principal ID | `<BLUEPRINT_SP_ID>` |
| Telemetry app (client ID / `agentId`) | `<TELEMETRY_APP_ID>` |
| Observability app-role | `Agent365.Observability.OtelWrite` (Application) |

> **App/object IDs não são segredos** — podem aparecer. **Client secrets, sim** —
> nunca commite.

---

## Arquivos adicionados (`agent.py` intocado)

- **`observability.py`** — `init_observability()` (configura o distro
  `microsoft-opentelemetry`, endpoint S2S), um **token resolver MSAL
  client-credentials**, e `observe_agent_run()` para spans manuais (ADK não tem
  auto-instrumentor). Tudo *lazy/guarded* → vira **no-op** se não estiver
  configurado ou se o SDK estiver ausente.
- **`__init__.py`** — carrega o `.env` e chama `init_observability()` no import.
- **`requirements.txt`**, **`.env.sample`** (template versionado), **`.env`**
  (git-ignored, com o secret da telemetria).
- **`.gitignore`** — passa a ignorar também `a365.config.json` e
  `a365.generated.config.json`.

O `root_agent` em `agent.py` **não é alterado** — a instrumentação é aditiva.

---

## Caveats honestos (leia antes de demonstrar)

1. 🔒 **Rotacione o client secret do blueprint** — ele é impresso uma vez no
   terminal durante a criação.
2. 📋 **Ingestão de telemetria exige Agent 365 / M365 E7.** Com só **E5**, a
   **governança/identidade funciona**, mas a **telemetria é descartada em
   silêncio**.
3. **ADK ≠ runtime do M365 Agents SDK** — a cadeia de token *agentic (FMI)* do
   blueprint não está disponível para um agente hospedado fora do M365. Por isso a
   telemetria usa um **token de app padrão (S2S)**.
4. **AI teammate** (mailbox/Teams próprios) requer **Frontier**.

---

## Fazendo com E7 / Agent 365 (cliente licenciado)

- A **telemetria passa a ingerir de verdade** → visível em
  **admin.cloud.microsoft → Agents → seu agente → Activity**.
- Opcionalmente, a via **agentic FMI** do blueprint (telemetria sob a identidade do
  próprio agente, não a de um app padrão).
- A camada **AI teammate**: o agente ganha **mailbox, presença no Teams e org
  chart** — vira um "funcionário" governado.

---

## Matriz de licenciamento (resumo)

| Capacidade | E5 + Entra ID P2 | Agent 365 / E7 |
|---|---|---|
| Registry sync (descoberta / *Unmanaged*) | ✅ | ✅ |
| Entra Agent ID / blueprint (governança) | ✅ | ✅ |
| Observability — instrumentação no código | ✅ | ✅ |
| Observability — **ingestão de telemetria** | ❌ | ✅ |
| *AI teammate* (identidade própria) | ❌ (Frontier) | ✅ (Frontier) |

**Leitura:** um cliente com **E5 + Entra ID P2 já obtém governança de agentes hoje**
(identidade no Entra + Purview/Defender aplicáveis à identidade). A **observability
com ingestão** é o próximo passo de licença (**Agent 365 / E7**).

---

## Segurança

- Nunca commite `.env`, `*-key.json`, `a365.config.json`,
  `a365.generated.config.json` (o `.gitignore` já cobre).
- **Rotacione** o secret do blueprint antes de qualquer uso em produção.
- App/object IDs podem ser versionados; **client secrets, nunca**.

---

MIT © 2026 Paulo Soares
