# 🛠️ Stack Tecnologico, Framework, API & Risorse di Riferimento

> Questo documento tiene traccia di tutti i **framework**, **librerie**, **API**, **piattaforme cloud** e **repository di riferimento** impiegati nel progetto **EXAMEN** *(dal latino "sciame d'api" ed "esame attento")*, con i relativi link, percorsi nel repository e note di integrazione.

---

## 📁 Organizzazione Risorse Esterne & Sottomoduli (`resources/`)

Per mantenere pulito il codice sorgente di **EXAMEN** e distinguere i componenti nativi del progetto da librerie, template e codici di consultazione, tutti i sottomoduli Git utilizzati come **risorse di riferimento ed esempi** risiedono nella directory dedicata [`resources/`](../resources/).

In questo modo:
* La directory di progetto principale rimane focalizzata sull'implementazione applicativa (`src/`, `docs/`, `tests/`).
* Gli esempi ufficiali e i client CLI esterni restano consultabili offline in [`resources/`](../resources/).
* Eventuali futuri sottomoduli destinati a diventare librerie runtime dirette del progetto possono essere gestiti distintamente.

---

## 📦 Sottomoduli Git in `resources/`

### 1. AWS Bedrock AgentCore Samples (`resources/agentcore-samples`)
* **Repository Git:** [awslabs/agentcore-samples](https://github.com/awslabs/agentcore-samples.git)
* **Percorso Locale Submodule:** [`resources/agentcore-samples/`](../resources/agentcore-samples/)
* **Descrizione:** Raccolta ufficiale di architetture di riferimento, template e integrazioni per **Amazon Bedrock AgentCore**.
* **Punto di Riferimento Chiave per EXAMEN:**
  * 🎯 **Directory:** [`resources/agentcore-samples/03-integrations/agentic-frameworks/langgraph/`](../resources/agentcore-samples/03-integrations/agentic-frameworks/langgraph/)
  * **File di Esempio:** [`langgraph_agent_web_search.py`](../resources/agentcore-samples/03-integrations/agentic-frameworks/langgraph/langgraph_agent_web_search.py)
  * **Dipendenze:** [`requirements.txt`](../resources/agentcore-samples/03-integrations/agentic-frameworks/langgraph/requirements.txt)
  * **Pattern Architetturale da Adottare:**
    Questo esempio dimostra esattamente come avvolgere un grafo **LangGraph** (`StateGraph`) all'interno del runtime **BedrockAgentCoreApp**:
    ```python
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    from langgraph.graph import StateGraph, START

    # 1. Compilazione del grafo LangGraph con i nodi Bedrock Converse
    graph = graph_builder.compile()

    # 2. Inizializzazione del runtime Bedrock AgentCore
    app = BedrockAgentCoreApp()

    # 3. Entrypoint invocato dal container / event loop
    @app.entrypoint
    def agent_invocation(payload, context):
        prompt = payload.get("prompt", "")
        output = graph.invoke({"messages": [{"role": "user", "content": prompt}]})
        return {"result": output["messages"][-1].content}

    if __name__ == "__main__":
        app.run()
    ```
  * **Pacchetti Chiave:**
    - `bedrock-agentcore`
    - `bedrock-agentcore-starter-toolkit`
    - `langchain-aws` (per `model_provider="bedrock_converse"`)
    - `langgraph`
    - `duckduckgo-search` / tool di ricerca web

---

### 2. Bee AI CLI Client (`resources/bee-cli`)
* **Repository Git:** [bee-computer/bee-cli](https://github.com/bee-computer/bee-cli.git)
* **Percorso Locale Submodule:** [`resources/bee-cli/`](../resources/bee-cli/)
* **Descrizione:** Client ufficiale a riga di comando e SDK TypeScript/Node per **Bee**, il wearable AI per l'ascolto ambientale continuo e l'apprendimento contestuale.
* **Punti di Riferimento Chiave per EXAMEN:**
  * 🎯 **Integrazione MCP (Model Context Protocol):** Bee CLI include nativamente un server MCP sia su stdio che su HTTP locale con Bearer Token:
    ```bash
    bee mcp serve                 # stdio JSON-RPC per assistenti AI
    bee mcp serve-http --port 8000 # HTTP locale con autenticazione Bearer
    ```
    Espone tool MCP nativi (`bee_search`, `bee_list_facts`, `bee_get_daily_summary`, `bee_list_todos`).
  * 🎯 **Streaming Real-time Trascrizioni (SSE):** Supporta l'ascolto di eventi in streaming per ricevere nuovi enunciati audio in tempo reale:
    ```typescript
    import { createBeeClient } from "@beeai/cli/lib";

    const bee = createBeeClient();
    const stream = bee.sse.streamJson({ types: ["new-utterance"] });
    for await (const event of stream.events) {
      console.log(event.data); // Payload audio trascritto per il Gatekeeper
    }
    ```
  * **Utilità per l'Ingestion:** Consente sia l'ingestion live sia l'esportazione di conversazioni e contesti per alimentare il buffer a finestra scorrevole dello Stadio 1 (Gatekeeper).

---

## 🧩 Framework & Librerie del Progetto

| Dominio | Tecnologia / Libreria | Versione / Pacchetto | Ruolo in EXAMEN |
| :--- | :--- | :--- | :--- |
| **Agent Runtime** | **AWS Bedrock AgentCore** | `bedrock-agentcore`, `bedrock-agentcore-starter-toolkit` | Harness di esecuzione per agenti complessi su AWS, gestione stato e lifecyle. |
| **State Graph** | **LangGraph** | `langgraph` ($\ge 0.2.0$) | Orchestrazione a stati: Gatekeeper $\to$ Router $\to$ Sub-Agenti specializzati. |
| **LLM Provider** | **LangChain AWS** | `langchain-aws`, `boto3` | Connessione unificata verso i modelli foundation di AWS Bedrock. |
| **Serving Layer** | **Model Context Protocol (MCP)** | `fastmcp` / `mcp` | Server JSON-RPC su Streamable HTTP che espone le capability di memoria ad Alexa+. |
| **Wearable Bridge** | **Bee CLI & beemcp** | `@beeai/cli`, `beemcp` | Ingestion in tempo reale dello stream audio e delle trascrizioni dal dispositivo Bee. |
| **Frontend UI** | **Echo Show Ext-Apps** | HTML5, Vanilla CSS, JS | Interfaccia touch multimodale per Echo Show (Peace of Mind, Rolodex, Briefing). |
| **Local Store** | **SQLite + FTS5** | Nativo Python (`sqlite3`) | Context store a latenza zero locale con indicizzazione full-text rapida. |
| **Data Validation** | **Pydantic V2** | `pydantic>=2.7` | Schemi tipizzati per output strutturati (entità sociali, stati verificati, report). |
| **Web Research** | **DuckDuckGo / Tavily** | `duckduckgo-search`, `tavily-python` | Tool di ricerca autonoma per l'approfondimento di topic tecnici e lezioni. |

---

## 🤖 Modelli LLM (AWS Bedrock)

| Modello | Identificativo Model ID | Scopo / Stadio | Motivazione Tecnica |
| :--- | :--- | :--- | :--- |
| **Claude 3.5 Haiku** | `anthropic.claude-3-5-haiku-20241022-v1:0` | Stadio 1 (Gatekeeper) & Stadio 3A/3B | Latenza ultra-bassa ($<350\text{ ms}$), costo ridotto (~$0.25/M input tokens), accuratezza elevata nel filtering. |
| **Amazon Nova Micro** | `amazon.nova-micro-v1:0` | Alternativa Stadio 1 (Gatekeeper) | Modello nativo AWS ultra-leggero, eccellente per la classificazione `noop` vs `valido`. |
| **Claude 3.5 Sonnet** | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Stadio 3C (Deep Research & Briefing) | Capacità di ragionamento avanzata, sintesi di documenti tecnici complessi e generazione markdown. |
| **Amazon Nova Pro** | `amazon.nova-pro-v1:0` | Alternativa Stadio 3C | Modello multimodale enterprise per analisi approfondita e reportistica tecnica. |

---

## 🌐 API & Servizi Cloud Esterni

| Servizio / API | Scopo | Note di Configurazione |
| :--- | :--- | :--- |
| **AWS Bedrock Runtime** | Inferenza serverless su modelli fondazionali | Richiede credenziali AWS (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION=us-east-1`). |
| **Bee Wearable API / WebSocket** | Stream audio e trascrizione ambientale | Ingestion da bridge `beemcp` locale o SSE streaming client (`bee-cli`). |
| **Alexa+ Developer Preview** | Invocazione MCP e rendering Ext-Apps | Registrazione tramite `addon.json` e tunnel HTTPS (Cloudflare Tunnel). |
| **Web Search API** | Ricerche documentali per il canale 3C | DuckDuckGo (zero-key locale) o Tavily API (`TAVILY_API_KEY`). |

---

## 📂 Struttura Directory Correlata

```
amazon_challenge/
├── resources/                            <-- Directory dedicata a sottomoduli, risorse ed esempi
│   ├── agentcore-samples/                <-- Sottomodulo Git ufficiale AWS Labs
│   │   └── 03-integrations/
│   │       └── agentic-frameworks/
│   │           └── langgraph/           <-- Esempio Integrazione LangGraph + AgentCore
│   └── bee-cli/                          <-- Sottomodulo Git ufficiale Bee AI CLI Client
├── docs/                                 <-- Specifiche architetturali e guide
│   ├── 01_architettura_flusso.md
│   ├── 02_pipeline_bedrock_agentcore.md
│   ├── 03_mcp_alexa_serving.md
│   ├── 04_hackathon_strategia_demo.md
│   └── 05_stack_tecnologico_risorse.md  <-- Questo documento
├── FRICTION_LOG.md                       <-- Diario di bordo e feedback SDK (+10% Hackathon bonus)
└── README.md                             <-- Panoramica del progetto EXAMEN
```
