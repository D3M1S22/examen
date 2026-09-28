# 🐝 EXAMEN: Ambient Knowledge & Action Engine

> **Amazon Developer Hackathon 2026**  
> **Track Principale:** Bee Wearable AI (Ambient Intelligence)  
> **Integrazioni Ecosistema:** Alexa+ (Echo Show MCP Server & Ext-Apps UI)  
> **Mini-Challenge:** AWS Builder Challenge (AWS Bedrock & AgentCore)  
> **Etimo & Visione:** *Dal latino "exāmen" (sciame d'api, ma anche esame attento e ponderazione).*  
> **Tagline:** *Dall'ascolto ambientale all'azione aumentata: memoria relazionale, tranquillità quotidiana e ricerca autonoma cross-device.*

---

## 🌟 Visione & Valore Chiave

La maggior parte degli assistenti vocali e delle app per wearable soffre di due limiti strutturali:
1. **Richiedono input attivo:** Devi fermarti, aprire un'app, premere un tasto o pronunciare keyword innaturali (*"Alexa, aggiungi alla lista..."*).
2. **Archiviazione passiva priva di intelligenza:** I wearable attuali si limitano a registrare o trascrivere log grezzi, riversando sull'utente il carico di rileggere e organizzare i dati.

**EXAMEN** trasforma il flusso audio continuo catturato dal wearable **Bee** in un **Knowledge & Action Fabric proattivo**. Grazie a una pipeline agentica intelligente su **AWS Bedrock** e **AgentCore**, il sistema filtra passivamente il parlato naturale, estrae entità e intenzioni, arricchisce autonomamente i contenuti tramite ricerche web e serve le informazioni su richiesta tramite **Alexa+** su **Echo Show**.

```
    [ Bee Wearable AI ] (Ascolto passivo continuo)
            │
            ▼ (beemcp / audio transcript stream)
 ┌────────────────────────────────────────────────────────┐
 │ 1. SCREMAGGIO (Semantic Gatekeeper su AWS Bedrock)      │ ──> [ Scarta Parlato Irrilevante (90%+) ]
 └──────────────────────────┬─────────────────────────────┘
                            │ (Chunk di valore categorizzati)
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 2. ROUTING & STATE GRAPH (AgentCore / LangGraph)        │
 └──────┬───────────────────┼────────────────────┬────────┘
        │                   │                    │
        ▼                   ▼                    ▼
 ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐
 │ 3A. SOCIAL   │   │ 3B. ACTION   │   │ 3C. DEEP TOPIC & LECTURE │
 │     RECALL   │   │     STATE    │   │     RESEARCH ENGINE      │
 │ (Nomi, Ruoli,│   │ (Routine &   │   │ (Bug, Feature, Tech &    │
 │  Promesse)   │   │  Task Ledger)│   │  Lezioni + Web Search)   │
 └──────┬───────┘   └───────┬──────┘   └─────────────┬────────────┘
        │                   │                        │
        └───────────────────┼────────────────────────┘
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 4. PERSISTENT CONTEXT STORE (SQLite / DynamoDB)        │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 5. SERVING VIA MCP SERVER (Alexa+ & Echo Show UI)       │
 └────────────────────────────────────────────────────────┘
            │                               │
            ▼ (Interazione Vocale)          ▼ (Visual Dashboard)
     "Alexa, ho staccato             Schede Relazionali,
      il ferro da stiro?"            Task Timeline, Report Tech
```

---

## 🎯 I Tre Domini Applicativi di EXAMEN

| Canale | Input Rilevato da Bee | Elaborazione & Enrichment | Output su Alexa+ / Echo Show |
| :--- | :--- | :--- | :--- |
| **🧠 Social Recall** | *"Piacere Marco, sono tech lead di Acme Corp, mandami la repo..."* | Estrazione anagrafica, ruolo aziendale, argomenti trattati e impegni bidirezionali presi. | *"Alexa, chi ho conosciuto oggi?"* ➔ Scheda anagrafica visiva su Echo Show con task di follow-up collegati. |
| **🔒 Action-State & Routine** | *"Sto chiudendo il gas e staccando il ferro da stiro."* oppure *"Ho fatto il merge della PR #42."* | Verifica asserzione in prima persona, classificazione del dominio (sicurezza domestica vs produttività) e marcatura timestamp con score di confidenza. | *"Alexa, ho staccato il ferro?"* ➔ Conferma vocale istantanea e badge verde di stato verificato a schermo. |
| **📚 Deep Meeting & Lecture Intelligence** | Discussione di bug complessi, architetture, nuove tecnologie (es. *AgentCore, DuckDB*) o concetti accademici. | Rilevamento topic, ricerca web autonoma per documentazione/esempi, sintesi di un **Briefing Esecutivo** o **Study Sheet**. | *"Alexa, mostrami il report sulle tecnologie discusse oggi"* ➔ Report interattivo su Echo Show e invio sintesi. |

---

## 🏗️ I 5 Livelli dell'Architettura

1. **Scremaggio (Semantic Gatekeeper):** Valutazione ultrarapida ed economica dei chunk di trascrizione tramite modello ultra-light su Bedrock (es. *Claude 3.5 Haiku* o *Amazon Nova Micro*). Se il testo è chiacchiericcio o rumore di fondo viene scartato a costo computazionale nullo per i moduli successivi.
2. **Routing Semantico:** I chunk ammessi vengono categorizzati (`social`, `action`, `deep_research`) e instradati al rispettivo sub-agent/nodo del grafo.
3. **Estrazione & Arricchimento:**
   - **Social:** Schema JSON strutturato dei contatti e promesse.
   - **Action-State:** Filtraggio stringente per evitare falsi positivi (solo azioni compiute, non intenzioni future o dubbi).
   - **Deep Topic Research:** Query automatica verso tool di web search (documentazione tecnica, articoli, basi di conoscenza) e stesura del dossier di approfondimento.
4. **Salvataggio Dati:** Context Database unificato (SQLite locale per latenza zero o AWS DynamoDB per cloud storage), indicizzato per query semantiche e temporali.
5. **Serving Layer (MCP Server per Alexa+):** Server basato su **Model Context Protocol (MCP)** che espone tool specialistici ad Alexa+, corredato da una GUI per Echo Show tramite **ext-apps iframe SDK**.

---

## 💻 Tech Stack & Integrazioni Ecosistema

- **Input Wearable:** Bee Wearable AI via bridge [`beemcp`](https://github.com/OkGoDoIt/beemcp) / Bee CLI transcript stream.
- **LLM Provider:** **AWS Bedrock**
  - *Claude 3.5 Haiku / Nova Micro:* Scremaggio e Routing a latenza minima e costo irrisorio.
  - *Claude 3.5 Sonnet / Nova Pro:* Estrazione avanzata, sintesi dossier e report di ricerca.
- **Agent Harness:** **AgentCore** / LangGraph per la gestione asincrona del grafo di stati e l'invocazione di tool.
- **Tool di Ricerca:** Bedrock Web Search / Tavily API per l'arricchimento autonomo dei topic.
- **Storage:** SQLite strutturato con tabelle dedicate e supporto full-text.
- **Serving & Voice UI:** Alexa+ (Echo Show) tramite Model Context Protocol (Streamable HTTP / Cloudflare Tunnel / AWS Lambda).
- **Frontend UI:** Ext-Apps Iframe SDK per schermi multimodali Echo Show.

---

## 🏆 Allineamento Criteri Hackathon & Premi Target

| Criterio / Track | Come EXAMEN Massimizza il Punteggio |
| :--- | :--- |
| **Track 1: Bee Wearable AI ($12.000)** | Supera il banale "data logging" integrando estrazione semantica in tempo reale, arricchimento autonomo con web search e self-improvement cognitivo. |
| **Mini-Challenge: AWS Builder ($5.000 + $5.000 crediti)** | Utilizzo nativo di AWS Bedrock con multi-model routing (Haiku per gatekeeper, Sonnet per sintesi) e orchestrazione agentica tramite AgentCore. |
| **Cross-Device Orchestration** | Esperienza simbiotica continua: **Bee** cattura il contesto nel mondo fisico in mobilità, **Alexa+ su Echo Show** lo sintetizza a casa o in ufficio sia a voce che visivamente. |

---

## 📂 Struttura della Documentazione di Progetto

I dettagli operativi, tecnici e strategici sono organizzati nei seguenti documenti dedicati:

* 📄 [01_architettura_flusso.md](file:///home/deggio/Desktop/coding/hackathon/amazon_challenge/docs/01_architettura_flusso.md): Dettaglio tecnico dei 5 stadi (Scremaggio, Routing, Estrazione/Enrichment, Storage, Serving).
* 📄 [02_pipeline_bedrock_agentcore.md](file:///home/deggio/Desktop/coding/hackathon/amazon_challenge/docs/02_pipeline_bedrock_agentcore.md): Implementazione del grafo con AWS Bedrock, AgentCore/LangGraph, schemi Pydantic, prompt e tool di ricerca.
* 📄 [03_mcp_alexa_serving.md](file:///home/deggio/Desktop/coding/hackathon/amazon_challenge/docs/03_mcp_alexa_serving.md): Specifiche del server MCP per Alexa+, definizione dei tool, schemi JSON-RPC e wireframe UI per Echo Show (ext-apps).
* 📄 [04_hackathon_strategia_demo.md](file:///home/deggio/Desktop/coding/hackathon/amazon_challenge/docs/04_hackathon_strategia_demo.md): Script e storyboard del video demo da 3 minuti, allineamento ai criteri di valutazione e piano di sviluppo.
