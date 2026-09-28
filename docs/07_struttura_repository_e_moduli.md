# 📁 Struttura della Repository & Architettura dei Moduli

> Questo documento fornisce una panoramica esaustiva dell'**organizzazione dei file e dei moduli** del progetto **EXAMEN** *(dal latino "sciame d'api" ed "esame attento")*, illustrando la logica architetturale, i confini di responsabilità e la mappatura tra cartelle e rispettivi **target di deployment**.

---

## 🏛️ Filosofia di Design: Modular Monorepo per Target di Deploy

Il repository adotta il pattern **Modular Monorepo orientato ai Target di Deployment**:
1. **Unico Core Dati Condiviso (`src/core/`):** Tutti i contratti (schemi Pydantic V2) e l'astrazione dello storage sono definiti in un unico punto, garantendo consistenza tra pipeline e serving.
2. **Isolamento dei Target di Esecuzione:**
   - La **pipeline agentica** risiede in `src/pipeline/` ed è strutturata per essere zippata e deployata direttamente sulle microVM Graviton di **AWS Bedrock AgentCore Runtime**.
   - Il **serving layer** risiede in `src/serving/` ed espone un server **FastMCP** conforme allo standard di **Alexa+**.
   - Il modulo di **ingestion** risiede in `src/ingestion/` ed è concepito per girare all'edge / companion (laptop/telefono/micro-istanza).
   - L'interfaccia **visuale** risiede in `src/web_ui/` ed è una Web App statica ultra-leggera per **Echo Show (ext-apps)** servita via S3 + CloudFront.
3. **Sviluppo Locale a Zero Attrito:** Ogni componente può essere eseguito e testato offline in locale (usando SQLite con indice FTS5 e mock audio) prima del deployment cloud.

---

## 🌳 Albero Completo del Repository

```
amazon_challenge/
├── docs/                                 # 📚 Documentazione tecnica, architetturale e strategica
│   ├── 01_architettura_flusso.md         # I 5 stadi della pipeline end-to-end
│   ├── 02_pipeline_bedrock_agentcore.md  # Dettagli del grafo LangGraph e schemi Bedrock
│   ├── 03_mcp_alexa_serving.md           # Specifiche server MCP e wireframe Echo Show
│   ├── 04_hackathon_strategia_demo.md    # Storyboard video da 3 min e piano sprint
│   ├── 05_stack_tecnologico_risorse.md   # Stack tecnologico, framework e dipendenze
│   ├── 06_architettura_deployment_cloud_aws.md # Topologia cloud AWS e hosting managed
│   └── 07_struttura_repository_e_moduli.md     # Questo documento
│
├── resources/                            # 📦 Sottomoduli Git esterni di consultazione offline
│   ├── agentcore-samples/                # Esempi e architetture di riferimento AWS Labs
│   │   └── 03-integrations/agentic-frameworks/langgraph/  # Esempio chiave LangGraph + AgentCore
│   └── bee-cli/                          # Client ufficiale Bee AI & server MCP nativo
│
├── src/                                  # 💻 Codice Sorgente Applicativo di EXAMEN
│   ├── core/                             # 🧱 Modulo condiviso tra tutti i componenti
│   │   ├── __init__.py                   # Export delle entità core
│   │   ├── config.py                     # Configurazione centralizzata (Pydantic Settings & .env)
│   │   ├── schemas.py                    # Contratti dati Pydantic V2 & TypedDict dello stato
│   │   └── storage/                      # Layer di persistenza agnostico (Repository Pattern)
│   │       ├── __init__.py               # Factory get_storage_store()
│   │       ├── base.py                   # AbstractContextStore (interfaccia comune)
│   │       ├── sqlite_store.py           # [Locale] SQLite thread-safe con supporto FTS5
│   │       ├── dynamo_store.py           # [Cloud] Amazon DynamoDB per verified_actions
│   │       └── memory_store.py           # [Cloud] AWS Bedrock AgentCore Memory (fatti/episodi)
│   │
│   ├── pipeline/                         # 🧠 [TARGET: AWS Bedrock AgentCore Runtime]
│   │   ├── __init__.py
│   │   ├── app.py                        # Entrypoint BedrockAgentCoreApp (@app.entrypoint)
│   │   ├── graph.py                      # Definizione StateGraph di LangGraph e conditional routing
│   │   ├── nodes/                        # Nodi specialistici del grafo agentico
│   │   │   ├── __init__.py
│   │   │   ├── gatekeeper.py             # Stadio 1: Scremaggio (Claude 3.5 Haiku / Nova Micro)
│   │   │   ├── social.py                 # Stadio 3A: Social Recall Extractor
│   │   │   ├── action_state.py           # Stadio 3B: Action-State Verifier (Peace of Mind)
│   │   │   └── topic_research.py         # Stadio 3C: Deep Topic & Briefing Generator
│   │   └── tools/                        # Tool invocati dai nodi del grafo
│   │       ├── __init__.py
│   │       └── web_search.py             # Tool di ricerca documentale (DuckDuckGo / Tavily)
│   │
│   ├── serving/                          # 🎙️ [TARGET: Alexa+ Serving / Server MCP]
│   │   ├── __init__.py
│   │   ├── mcp_server.py                 # Server FastMCP (porta 8000 /mcp, streamable-http)
│   │   └── tools/                        # I 4 tool specialistici esposti ad Alexa+
│   │       ├── __init__.py
│   │       ├── action_tools.py           # verify_action_status, get_daily_actions_recap
│   │       ├── social_tools.py           # query_social_contact
│   │       └── topic_tools.py            # get_topic_briefing
│   │
│   ├── ingestion/                        # 🐝 [TARGET: Edge / Companion Bridge]
│   │   ├── __init__.py
│   │   ├── bee_stream_bridge.py          # Bridge live SSE connesso a bee-cli ("new-utterance")
│   │   └── mock_feeder.py                # Simulatore offline di stream audio per test e demo
│   │
│   └── web_ui/                           # 🖥️ [TARGET: S3 + CloudFront / Echo Show Ext-Apps]
│       ├── index.html                    # Dashboard interattiva multimodale
│       ├── styles.css                    # Styling Dark Mode moderno per display touch
│       ├── app.js                        # Logica frontend reattiva e rendering schede
│       └── assets/                       # Icone vettoriali SVG e risorse grafiche
│
├── deploy/                               # 🚀 Automazione e Script di Deployment Cloud
│   ├── build_agentcore_bundle.sh         # Download ruote arm64 con uv e creazione code.zip
│   ├── deploy_agentcore_runtime.py       # Registrazione runtime via boto3 bedrock-agentcore-control
│   ├── deploy_ext_apps_s3.sh             # Sync web_ui su S3 + invalidazione CDN CloudFront
│   └── alexa_addon.json                  # Manifest di registrazione MCP per Alexa+ CLI
│
├── tests/                                # 🧪 Test Suite & Validazione
│   ├── fixtures/                         # Dataset mock di trascrizioni audio (social, azioni, tech)
│   ├── test_storage.py                   # Test unitari sul layer di persistenza (passati al 100%)
│   ├── test_gatekeeper.py                # Test efficienza filtro scremaggio (>90% drop)
│   ├── test_langgraph_pipeline.py        # Test di esecuzione end-to-end del grafo
│   └── test_mcp_server.py                # Test delle chiamate JSON-RPC per i tool Alexa+
│
├── pyproject.toml                        # Configurazione build Python e setup pytest
├── requirements.txt                      # Dipendenze Python unificate
├── .env.example                          # Template delle variabili d'ambiente (AWS, chiavi, porte)
├── .gitignore                            # Esclusione di .venv, cache, database locali e segreti
├── FRICTION_LOG.md                       # Diario di bordo per il bonus +10% dell'hackathon
└── README.md                             # Panoramica del progetto, visione e guida rapida
```

---

## 🔍 Dettaglio dei Moduli Principali

### 1. `src/core/` (Condiviso)
* **`config.py`:** Utilizza `pydantic-settings` per leggere variabili d'ambiente con fallback sicuri per lo sviluppo locale (default: regione `us-east-1`, modelli Claude 3.5 Haiku/Sonnet, backend SQLite `examen.db`, porta MCP 8000).
* **`schemas.py`:** Definisce rigorosamente i modelli Pydantic V2:
  - `ChunkClassification`: Output compatto del Gatekeeper (`categories`, `confidence`, `summary_hint`).
  - `SocialEntity`: Dati anagrafici, ruoli, promesse e topic delle persone incontrate.
  - `VerifiedAction`: Azioni di routine/sicurezza verificate con marcatura oraria e confidenza $\ge 0.80$.
  - `TopicExtraction` & `BriefingReport`: Estrazione dei temi di meeting/lezioni e dossier approfondito sintetizzato con fonti web.
  - `ExamenState`: `TypedDict` per lo stato mutabile del grafo LangGraph.
* **`storage/`:** 
  - `base.py`: Classe astratta `AbstractContextStore` che impone il contratto di salvataggio e recupero dati.
  - `sqlite_store.py`: Implementazione locale nativa in Python con indici e tabelle virtuali FTS5 per ricerche full-text ultra-rapide ($<5\text{ ms}$).

---

### 2. `src/pipeline/` (AWS Bedrock AgentCore Runtime)
* **`app.py`:** Inizializza `BedrockAgentCoreApp` ed espone la funzione decorata con `@app.entrypoint`. Quando invocata da AWS via `invoke_agent_runtime`, riceve il chunk audio e avvia l'elaborazione del grafo.
* **`graph.py`:** Costruisce lo `StateGraph` di LangGraph, impostando come entry point il Gatekeeper e orchestrando i collegamenti condizionali verso i sub-agenti specializzati (`social`, `action`, `deep_topic`) e il nodo finale di persistenza.
* **`nodes/`:**
  - `gatekeeper.py`: Valuta il testo con Claude 3.5 Haiku / Nova Micro. Se privo di valore informativo, termina con `noop` a costo computazionale nullo per i moduli successivi.
  - `social.py`: Estrae contatti ed impegni reciproci, deduplicando le persone già presenti nel database.
  - `action_state.py`: Valuta le asserzioni di azioni compiute scartando dubbi o frasi al futuro.
  - `topic_research.py`: Identifica argomenti tecnici, invoca `web_search.py` e genera il report strutturato con Claude 3.5 Sonnet.

---

### 3. `src/serving/` (Alexa+ Serving Layer)
* **`mcp_server.py`:** Implementa un server conforme allo standard **Model Context Protocol (MCP)** utilizzando la libreria `FastMCP` con trasporto `streamable-http` (compatibile sia con l'hosting locale sia con il protocollo nativo MCP di AgentCore Runtime).
* **`tools/`:** Espone i 4 tool invocabili dall'assistente vocale Alexa+:
  - `verify_action_status`: Risponde vocalmente a domande come *"Ho staccato il ferro da stiro?"* con orario e grado di certezza.
  - `get_daily_actions_recap`: Fornisce il resoconto cronologico delle azioni svolte nella giornata.
  - `query_social_contact`: Recupera ruolo aziendale e promesse scambiate con una persona.
  - `get_topic_briefing`: Restituisce il dossier sintetizzato sul meeting o la lezione più recente.

---

### 4. `src/ingestion/` (Edge / Companion Bridge)
* **`bee_stream_bridge.py`:** Client asincrono che si connette all'endpoint Server-Sent Events (SSE) di `bee-cli` (`new-utterance`), accumulando le trascrizioni in una finestra scorrevole da 30-45 secondi con 5 secondi di sovrapposizione.
* **`mock_feeder.py`:** Utilità per simulare flussi realistici di parlato durante lo sviluppo offline o per riprodurre fedelmente la sequenza dimostrativa per il video finale.

---

### 5. `src/web_ui/` (Echo Show Ext-Apps)
* Web application responsive progettata specificamente per gli schermi touch di **Echo Show (8, 10, 15)**.
* Caricata all'interno dell'iframe sandboxed di Alexa Ext-Apps con crittografia HTTPS (erogata tramite CloudFront).
* Mostra i badge di sicurezza domestica (Peace of Mind), il rolodex dei contatti e il viewer a schede scorrevoli per i briefing tecnici.

---

## 🛠️ Guida Rapida ai Comandi di Sviluppo

```bash
# 1. Creazione ambiente virtuale e installazione dipendenze
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Esecuzione della test suite
pytest

# 3. Avvio del server MCP per Alexa+ (porta 8000)
python -m src.serving.mcp_server

# 4. Ingestion di prova tramite simulatore offline
python -m src.ingestion.mock_feeder --scenario morning_routine
```
