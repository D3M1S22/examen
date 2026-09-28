# ⚙️ Pipeline Tecnica: AWS Bedrock, AgentCore & LangGraph

> Questo documento fornisce le specifiche di implementazione per la pipeline agentica di **EXAMEN** *(dal latino "sciame d'api")*, dettagliando i modelli di **AWS Bedrock**, l'architettura dello stato con **LangGraph / AgentCore**, gli schemi di dati Pydantic, i prompt di sistema e l'arricchimento autonomo con web search.

---

## 🧠 Selezione dei Modelli AWS Bedrock & Strategia Costi/Latenza

La pipeline implementa un pattern **Multi-Model Tiering** su AWS Bedrock per garantire reattività istantanea e costi di inferenza sostenibili per un dispositivo sempre attivo:

| Ruolo Pipeline | Modello AWS Bedrock Primario | Modello Alternativo AWS | Temperatura | Latenza Target |
| :--- | :--- | :--- | :--- | :--- |
| **Stadio 1: Gatekeeper / Scremaggio** | `anthropic.claude-3-5-haiku-20241022-v1:0` | `amazon.nova-micro-v1:0` | `0.0` | $< 350\text{ ms}$ |
| **Stadio 3A: Social Recall Extractor** | `anthropic.claude-3-5-haiku-20241022-v1:0` | `amazon.nova-lite-v1:0` | `0.0` | $< 500\text{ ms}$ |
| **Stadio 3B: Action-State Verifier** | `anthropic.claude-3-5-haiku-20241022-v1:0` | `amazon.nova-lite-v1:0` | `0.0` | $< 400\text{ ms}$ |
| **Stadio 3C: Deep Research & Briefing** | `anthropic.claude-3-5-sonnet-20241022-v2:0` | `amazon.nova-pro-v1:0` | `0.2` | $< 2500\text{ ms}$ |

* **Perché Haiku/Nova Micro per lo Scremaggio:** Gestisce migliaia di token orari con un costo irrisorio (~$0.25 per milione di token di input) scartando il 90%+ dei dati irrilevanti a monte.
* **Perché Sonnet/Nova Pro per il Canale 3C:** Solo quando viene identificato un tema tecnologico, un bug o una lezione universitaria si attiva il modello ad alto ragionamento, capace di elaborare i risultati della ricerca web e redigere un dossier tecnico approfondito.

---

## 📐 Schemi Dati e Contratti Pydantic

Tutte le interazioni tra i nodi dell'harness sono rigorosamente tipizzate tramite **Pydantic V2**:

```python
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

# ----------------------------------------------------
# 1. Output Classificatore Gatekeeper
# ----------------------------------------------------
class ChunkClassification(BaseModel):
    categories: List[Literal["social", "action", "deep_topic", "noop"]] = Field(
        description="Categorie rilevate nel chunk di trascrizione. 'noop' se irrilevante."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, 
        description="Livello di confidenza generale della classificazione."
    )
    summary_hint: str = Field(
        description="Breve frase di 1 riga che riassume il contenuto utile rilevato."
    )

# ----------------------------------------------------
# 2. Canale Social Recall
# ----------------------------------------------------
class SocialEntity(BaseModel):
    person_name: str = Field(description="Nome e/o cognome della persona incontrata.")
    company_or_role: Optional[str] = Field(None, description="Azienda, ruolo o contesto professionale.")
    contact_info: Optional[str] = Field(None, description="Email, handle social, telefono se menzionati.")
    commitments: List[str] = Field(
        default_factory=list, 
        description="Promesse fatte all'interlocutore o che l'interlocutore ha fatto all'utente."
    )
    key_topics: List[str] = Field(
        default_factory=list, 
        description="Tag o argomenti salienti discussi durante l'interazione."
    )

# ----------------------------------------------------
# 3. Canale Action-State & Routine Task
# ----------------------------------------------------
class VerifiedAction(BaseModel):
    action_type: str = Field(
        description="Tipo di azione normalizzata: porta_chiusa, gas_spento, ferro_staccato, farmaco_preso, pr_merged, email_inviata."
    )
    domain: Literal["safety", "routine", "work_task"] = Field(
        description="Dominio dell'azione (sicurezza domestica, routine personale o task lavorativo)."
    )
    raw_statement: str = Field(
        description="Frase esatta pronunciata dall'utente attestante l'azione compiuta."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, 
        description="Score di certezza che l'azione sia effettivamente avvenuta (filtrare dubbi o frasi al futuro)."
    )

# ----------------------------------------------------
# 4. Canale Deep Topic Research (Tech / Education)
# ----------------------------------------------------
class TopicExtraction(BaseModel):
    topic_title: str = Field(description="Titolo sintetico dell'argomento, bug o tecnologia.")
    context_type: Literal["bug", "feature_discussion", "tech_stack", "academic_lecture"] = Field(
        description="Tipologia di contesto da cui è scaturito il tema."
    )
    search_queries: List[str] = Field(
        description="1-3 query di ricerca web formulate per approfondire l'argomento su fonti autorevoli."
    )
    key_questions: List[str] = Field(
        description="Domande aperte o aspetti tecnici da chiarire nel report."
    )

class BriefingReport(BaseModel):
    topic_title: str
    context_type: str
    executive_summary: str = Field(description="Sintesi esecutiva in 3-4 punti elenco.")
    deep_dive_markdown: str = Field(description="Dossier approfondito con definizioni, soluzioni o documentazione.")
    web_sources: List[str] = Field(description="URL e fonti esterne consultate.")
    action_items: List[str] = Field(description="Task suggeriti o step successivi per il team o lo studente.")
```

---

## 🔄 Definizione dello Stato e del Grafo (AgentCore / LangGraph)

```python
from typing import TypedDict, Optional, List
from langchain_aws import ChatBedrock
from langgraph.graph import StateGraph, END

# --- Stato Condiviso del Grafo ---
class ExamenState(TypedDict):
    raw_transcript: str
    timestamp: str
    session_id: str
    categories: List[str]
    social_data: Optional[SocialEntity]
    action_data: Optional[VerifiedAction]
    topic_extracted: Optional[TopicExtraction]
    briefing_report: Optional[BriefingReport]
    error: Optional[str]

# --- Inizializzazione Client AWS Bedrock ---
llm_gatekeeper = ChatBedrock(
    model_id="anthropic.claude-3-5-haiku-20241022-v1:0",
    region_name="us-east-1",
    model_kwargs={"temperature": 0.0}
)

llm_reasoner = ChatBedrock(
    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
    region_name="us-east-1",
    model_kwargs={"temperature": 0.2}
)
```

### Implementazione dei Nodi

```python
# 1. NODO GATEKEEPER / SCREMAGGIO
def node_gatekeeper(state: ExamenState) -> dict:
    prompt = (
        "Sei il filtro semantico ad alta efficienza per l'assistente indossabile EXAMEN.\n"
        "Analizza il seguente chunk audio trascritto ed etichettalo identificando se contiene:\n"
        "- 'social': presentazioni, scambio di nomi, ruoli o promesse a persone;\n"
        "- 'action': dichiarazioni esplicite di azioni di sicurezza compiute o task lavorativi completati;\n"
        "- 'deep_topic': discussione su tecnologie, librerie, architetture, bug di codice, feature o lezioni accademiche;\n"
        "- 'noop': se il frammento è privo di informazioni stabili (chiacchiere banali, saluti informali, silenzio).\n\n"
        f"Trascrizione: \"{state['raw_transcript']}\""
    )
    classifier = llm_gatekeeper.with_structured_output(ChunkClassification)
    res = classifier.invoke(prompt)
    return {"categories": res.categories}

# 2. NODO SOCIAL RECALL
def node_extract_social(state: ExamenState) -> dict:
    prompt = (
        "Estrai i dati della persona incontrata e gli impegni reciproci presi.\n"
        f"Testo: \"{state['raw_transcript']}\""
    )
    extractor = llm_gatekeeper.with_structured_output(SocialEntity)
    return {"social_data": extractor.invoke(prompt)}

# 3. NODO ACTION-STATE
def node_extract_action(state: ExamenState) -> dict:
    prompt = (
        "Analizza se l'utente ha affermato di aver appena compiuto un'azione di routine o sicurezza "
        "(es. 'ho spento il fornello', 'porta chiusa a chiave', 'ho deployato in staging').\n"
        "ATTENZIONE: Ignora categoricamente frasi al futuro o dubbi ('devo ricordarmi di chiudere il gas').\n"
        f"Testo: \"{state['raw_transcript']}\""
    )
    extractor = llm_gatekeeper.with_structured_output(VerifiedAction)
    return {"action_data": extractor.invoke(prompt)}

# 4. NODO TOPIC EXTRACTION & RESEARCH
def node_topic_research(state: ExamenState) -> dict:
    # Passo 1: Estrazione argomenti e formulazione query
    prompt_extract = (
        "Identifica l'argomento tecnico, il bug discusso, la tecnologia citata o il tema della lezione accademica.\n"
        "Genera query di ricerca per reperire documentazione e approfondimenti.\n"
        f"Testo: \"{state['raw_transcript']}\""
    )
    topic_parser = llm_gatekeeper.with_structured_output(TopicExtraction)
    extracted: TopicExtraction = topic_parser.invoke(prompt_extract)

    # Passo 2: Web Search via Bedrock Agent Tool / Search API
    # Simulazione / Chiamata reale a tool di ricerca web
    search_context = execute_web_search(extracted.search_queries)

    # Passo 3: Sintesi e generazione Report con Claude 3.5 Sonnet
    prompt_report = (
        f"Sei un assistente di ricerca tecnica. L'utente ha discusso durante un incontro di: '{extracted.topic_title}'.\n"
        f"Contesto discussione: \"{state['raw_transcript']}\"\n"
        f"Risultati documentazione web reperiti:\n{search_context}\n\n"
        "Genera un Briefing Esecutivo approfondito con markdown formattato per Echo Show e sviluppatori."
    )
    synthesizer = llm_reasoner.with_structured_output(BriefingReport)
    report = synthesizer.invoke(prompt_report)

    return {"topic_extracted": extracted, "briefing_report": report}

# 5. NODO PERSISTENZA
def node_persist(state: ExamenState) -> dict:
    from examen_db import save_context_event
    save_context_event(state)
    return {}
```

### Costruzione del Grafo Condizionale

```python
def router_dispatch(state: ExamenState):
    cats = state.get("categories", ["noop"])
    routes = []
    if "social" in cats:
        routes.append("extract_social")
    if "action" in cats:
        routes.append("extract_action")
    if "deep_topic" in cats:
        routes.append("topic_research")
    return routes if routes else ["end"]

# Inizializzazione Grafo
builder = StateGraph(ExamenState)

builder.add_node("gatekeeper", node_gatekeeper)
builder.add_node("extract_social", node_extract_social)
builder.add_node("extract_action", node_extract_action)
builder.add_node("topic_research", node_topic_research)
builder.add_node("persist", node_persist)

builder.set_entry_point("gatekeeper")

# Routing dinamico
builder.add_conditional_edges(
    "gatekeeper",
    router_dispatch,
    {
        "extract_social": "extract_social",
        "extract_action": "extract_action",
        "topic_research": "topic_research",
        "end": END
    }
)

builder.add_edge("extract_social", "persist")
builder.add_edge("extract_action", "persist")
builder.add_edge("topic_research", "persist")
builder.add_edge("persist", END)

examen_agent = builder.compile()
```

---

## 🌐 Integrazione Tool di Web Search per il Canale 3C

Quando viene invocato il nodo `topic_research`, l'harness di AgentCore dispone di uno o più tool per reperire documentazione esterna:
1. **AWS Bedrock Agent Action Group:** Configurato con una funzione Lambda integrata a un motore di ricerca (es. Brave Search o Tavily Search API).
2. **DuckDuckGo / Tavily Python Provider:** Per il deployment locale dell'hackathon, una chiamata asincrona restituisce i primi 3 risultati pertinenti con URL, snippet e testo pulito.

```python
def execute_web_search(queries: List[str]) -> str:
    """Interroga il motore di ricerca per ciascuna query e formatta il contesto."""
    results_text = []
    for q in queries[:2]:
        # Chiamata API al search provider
        res = mock_or_live_search(q)
        results_text.append(f"Query: {q}\nRisultati:\n{res}")
    return "\n\n".join(results_text)
```

---

## 🚀 Deployment dell'Harness con AgentCore su AWS

Per concorrere alla mini-challenge **AWS Builder Challenge ($5.000 cash + $5.000 crediti)**:
* **Containerizzazione:** L'harness LangGraph/AgentCore viene impacchettato in un container Docker leggero basato su Python 3.11.
* **Hosting:** 
  - In locale / demo: In esecuzione sul computer di sviluppo esposto tramite Cloudflare Tunnel.
  - In cloud su AWS: Deployato su **AWS App Runner** o **Amazon ECS Fargate**, collegato ad AWS Bedrock via IAM Roles a privilegi minimi (`bedrock:InvokeModel`).
* **Ingestion Event-Driven:** L'ascoltatore WebSocket o il polling da `beemcp` riceve il chunk audio e invoca il grafo asincronamente tramite una coda **Amazon SQS** o un thread worker non bloccante.
