# 🎙️ Serving Layer: Alexa+ MCP Server & Echo Show UI

> Questo documento definisce l'architettura di **Serving** di **EXAMEN** *(dal latino "sciame d'api")*, illustrando come i dati salvati vengono esposti tramite un server conforme al **Model Context Protocol (MCP)** per **Alexa+** e come vengono visualizzati graficamente sugli schermi **Echo Show** tramite il framework **ext-apps**.

---

## 🌐 Architettura del Server MCP per Alexa+

Alexa+ si interfaccia con EXAMEN mediante lo standard **Model Context Protocol (MCP)** su trasporto **Streamable HTTP**. Quando l'utente formula una richiesta vocale naturale, l'LLM di Alexa+ esamina i tool esposti dal server EXAMEN, formula la chiamata JSON-RPC opportuna e presenta i risultati sia via sintesi vocale (TTS) sia tramite widget interattivo su schermo.

```
 [ Utente a Casa / Ufficio ]
            │ (Domanda vocale)
            ▼
    [ Echo Show / Alexa+ ]
            │
            ▼ (MCP Streamable HTTP / JSON-RPC 2.0)
 ┌────────────────────────────────────────────────────────┐
 │           EXAMEN MCP Server (Python FastMCP)            │
 ├────────────────────────────────────────────────────────┤
 │ 🔧 Tool: verify_action_status(action_query)            │
 │ 🔧 Tool: get_daily_actions_recap(date, domain)         │
 │ 🔧 Tool: query_social_contact(name_or_query)           │
 │ 🔧 Tool: get_topic_briefing(topic_query)               │
 │ 🔧 Tool: search_context(query)                         │
 └──────────────────────────┬─────────────────────────────┘
                            │ (Query SQL / Lettura)
                            ▼
              [ SQLite Context Database ]
```

---

## 🛠️ Definizione dei Tool MCP Esposti

### 1. `verify_action_status` (Peace of Mind)
Verifica istantaneamente se una determinata azione di routine o sicurezza è stata eseguita.
* **Descrizione Tool:** *"Verifica lo stato e l'orario di completamento di un'azione domestica di sicurezza (es. ferro da stiro, gas, porta di casa, farmaci) o di un task lavorativo."*
* **Parametri Input:**
  - `action_query` *(string, obbligatorio)*: L'azione da verificare (es. `"ferro"`, `"gas"`, `"porta"`, `"chiavi"`).
  - `target_date` *(string, opzionale)*: Data di riferimento in formato `YYYY-MM-DD` (default: oggi).
* **Risposta Strutturata:**
  ```json
  {
    "status": "verified",
    "action_type": "ferro_staccato",
    "timestamp": "2026-09-28T08:14:22+02:00",
    "raw_statement": "Sto staccando la spina del ferro da stiro prima di uscire",
    "confidence": 0.96,
    "elapsed_time_human": "3 ore e 12 minuti fa",
    "ui_card_type": "ACTION_VERIFIED_BADGE"
  }
  ```
* **Risposta Vocale di Alexa:** *"Sì, hai confermato di aver staccato il ferro da stiro stamattina alle 08:14, circa 3 ore fa."*

---

### 2. `get_daily_actions_recap` (Standup & Daily Log)
Fornisce il resoconto completo delle azioni e task registrati durante la giornata.
* **Descrizione Tool:** *"Restituisce la timeline ordinata di tutte le azioni di routine compiute e dei task lavorativi svolti."*
* **Parametri Input:**
  - `domain` *(string, opzionale)*: Filtro per categoria (`"all"`, `"safety"`, `"work_task"`).
  - `limit` *(integer, opzionale, default: 10)*.
* **Risposta Strutturata:**
  ```json
  {
    "date": "2026-09-28",
    "total_actions": 4,
    "items": [
      {"time": "08:14", "action": "Staccato ferro da stiro", "type": "safety"},
      {"time": "08:16", "action": "Chiusa porta a chiave", "type": "safety"},
      {"time": "11:30", "action": "Merge completato su repo backend", "type": "work_task"},
      {"time": "14:15", "action": "Inviata email a cliente", "type": "work_task"}
    ]
  }
  ```

---

### 3. `query_social_contact` (Social Recall)
Recupera informazioni su persone incontrate, ruoli aziendali e impegni presi.
* **Descrizione Tool:** *"Cerca nel registro delle interazioni sociali persone conosciute tramite nome, azienda o argomenti discussi."*
* **Parametri Input:**
  - `name_or_query` *(string, obbligatorio)*: Nome della persona o parola chiave contestuale (es. `"Marco"`, `"Stripe"`, `"startup"`).
* **Risposta Strutturata:**
  ```json
  {
    "found": true,
    "contact": {
      "name": "Marco Rossi",
      "company_or_role": "Tech Lead @ Acme Corp",
      "first_met": "2026-09-28T10:30:00+02:00",
      "key_topics": ["AWS Bedrock", "Architetture Agentiche", "Finanziamento Seed"],
      "commitments": [
        "Inviare il link della documentazione tecnica di EXAMEN",
        "Marco invierà feedback sull'architettura MCP entro venerdì"
      ]
    },
    "ui_card_type": "SOCIAL_PROFILE_CARD"
  }
  ```
* **Risposta Vocale di Alexa:** *"Marco Rossi è il Tech Lead di Acme Corp. Avete parlato di AWS Bedrock e ti sei impegnato a mandargli la documentazione di EXAMEN."*

---

### 4. `get_topic_briefing` (Deep Meeting & Lecture Intelligence)
Recupera il dossier di approfondimento generato automaticamente dopo una riunione o lezione accademica.
* **Descrizione Tool:** *"Recupera il report esecutivo approfondito, arricchito con ricerche web, su tecnologie, bug o temi di studio discussi."*
* **Parametri Input:**
  - `topic_query` *(string, opzionale)*: Titolo o parola chiave dell'argomento (es. `"AgentCore"`, `"bug memoria"`, `"macchine di turing"`). Se omesso, restituisce l'ultimo report generato.
* **Risposta Strutturata:**
  ```json
  {
    "topic_title": "AgentCore & AWS Bedrock Multi-Agent Orchestration",
    "context_type": "tech_stack",
    "created_at": "2026-09-28T12:05:00+02:00",
    "executive_summary": [
      "AgentCore gestisce runtime agentici resilienti con supporto nativo per Bedrock.",
      "Supporta la persistenza dello stato e invocazioni di tool asincrone.",
      "Risolve i problemi di concurrency riscontrati nella riunione delle 11:00."
    ],
    "web_sources": [
      "https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html",
      "https://github.com/awslabs/amazon-bedrock-agentcore"
    ],
    "action_items": [
      "Aggiornare l'harness di deployment sul branch staging",
      "Configurare la IAM Policy bedrock:InvokeModel"
    ],
    "ui_card_type": "DEEP_BRIEFING_VIEWER"
  }
  ```

---

## 🖥️ Interfaccia Visiva su Echo Show (`ext-apps` Iframe SDK)

L'integrazione di Alexa+ supporta l'estensione **`ext-apps`**, che consente al server MCP di proiettare una Web App interattiva e reattiva all'interno dello schermo touch di **Echo Show (8, 10, 15)**.

### Layout Wireframe per Echo Show (Dark Mode Moderno)

```
┌────────────────────────────────────────────────────────────────────────┐
│ 🐝 EXAMEN Ambient OS                        📅 Lunedì, 28 Settembre   │
├───────────────────┬────────────────────────────────────────────────────┤
│ 🔒 Peace of Mind  │ 🟢 VERIFICATO: Ferro da Stiro                      │
│ 🧠 Social Rolodex │ Orario: 08:14:22 CEST (3 ore fa)                   │
│ 📚 Deep Briefings │ Dichiarazione audio:                               │
│                   │ "Sto staccando la spina del ferro prima di uscire" │
│                   │ Confidenza: 96%  |  Sensore: Bee Wearable Lapel    │
├───────────────────┴────────────────────────────────────────────────────┤
│ 📋 ULTIMI TASK VERIFICATI:                                             │
│ [✓] 08:16 - Porta di casa chiusa a chiave                              │
│ [✓] 11:30 - Deploy completato su staging (PR #42)                      │
└────────────────────────────────────────────────────────────────────────┘
```

### Visual Card 2: Deep Topic Briefing Card

```
┌────────────────────────────────────────────────────────────────────────┐
│ 📚 Deep Tech Briefing: AWS AgentCore Architecture                      │
├────────────────────────────────────────────────────────────────────────┤
│ 💡 Sintesi Esecutiva:                                                  │
│ • Framework per runtime agentici serverless scalabili.                │
│ • Integrazione nativa con Claude 3.5 Haiku (routing) e Sonnet.         │
│                                                                        │
│ 🌐 Fonti Web Consultate in Autonomia:                                  │
│ • AWS Bedrock Agents Developer Guide [🔗 docs.aws.amazon.com]          │
│ • GitHub: awslabs/bedrock-agentcore [🔗 github.com]                    │
│                                                                        │
│ 📌 Action Items Riunione:                                              │
│ [ ] Integrare IAM Role con permessi minimi di invocazione              │
│ [ ] Testare latenza del gatekeeper su finestra da 30 secondi           │
│                                                                        │
│ [ Invia a Email Utente ✉️ ]    [ Condividi su Slack 💬 ]               │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🔌 Configurazione `addon.json` per Alexa+ CLI

Per registrare l'MCP Server all'interno della developer preview di Alexa+:

```json
{
  "name": "examen-mcp",
  "version": "1.0.0",
  "description": "Ambient intelligence and memory augmentation server for Bee wearable and Echo Show",
  "mcp": {
    "server": {
      "transport": "http",
      "url": "https://examen-tunnel.yourdomain.com/mcp",
      "capabilities": {
        "tools": true,
        "resources": true,
        "prompts": true
      }
    }
  },
  "extApps": {
    "entryPoint": "https://examen-tunnel.yourdomain.com/ext-app/index.html",
    "displayModes": ["full_screen", "card_modal"]
  }
}
```
