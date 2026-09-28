# 🏆 Strategia Hackathon, Pitch & Script Video Demo

> Questo documento sintetizza la **strategia di gara** per massimizzare il punteggio della giuria nell'**Amazon Developer Hackathon 2026**, specificando l'allineamento con i criteri di valutazione, lo script del video demo da 3 minuti e il piano operativo di sviluppo.

---

## 🎯 Criteri di Giudizio & Come EXAMEN Sbaraglia la Concorrenza

I giudici del track **Bee Wearable AI** e della mini-challenge **AWS Builder** hanno requisiti espliciti per distinguere le idee banali da quelle vincenti:

| Requisito Ufficiale dei Giudici | Errore Comune ("Obvious Idea") | La Risposta Vincente di EXAMEN |
| :--- | :--- | :--- |
| **Cross-Device Orchestration** | Notifica semplice rilanciata dallo smartwatch al telefono. | **Bee Wearable + Echo Show (Alexa+):** L'input è passivo e invisibile (Bee); la consultazione è multimodale, vocale e touch (Echo Show). |
| **Ambient Context Capture** | Dover pronunciare keyword esplicite (*"Ehi Bee, salva questo..."*). | **Zero-shot ambient processing:** L'utente parla naturalmente. Il Gatekeeper semantico su Bedrock cattura l'essenza senza alcuna parola di attivazione forzata. |
| **Advanced Facts & Insights** | Semplice lista di log testuali cronologici. | **Enrichment Autonomo:** Quando una discussione tocca nuove tecnologie o concetti complessi, EXAMEN effettua ricerche web in background e genera un briefing completo. |
| **AWS Builder Challenge ($5.000 + $5.000)** | Chiamata generica a un LLM esterno senza architettura cloud. | Utilizzo strutturato di **AWS Bedrock** con multi-tiering (Haiku per routing, Sonnet per sintesi) e harness agentico scalabile con **AgentCore**. |

---

## 💰 Montepremi Target

* 🥇 **1° Posto Track Bee Wearable AI:** **$12.000 cash**
* ⚡ **Vincitore Mini-Challenge AWS Builder:** **$5.000 cash + $5.000 crediti AWS**
* 🎁 **Bonus Opportunità:** Meeting 1:1 con i Director & Senior Leadership di Amazon Alexa & AWS.
* **Potenziale Complessivo:** **$17.000 cash + $5.000 crediti AWS**.

---

## 🎬 Storyboard & Script del Video Demo (3 Minuti)

> **Regola Aurea:** Un video di hackathon vincente deve mostrare il problema nei primi 30 secondi, il funzionamento trasparente della tecnologia nel minuto centrale, e 3 dimostrazioni pratiche indiscutibili e spettacolari.

```
0:00 ─── 0:35 ─── 1:15 ─── 1:50 ─── 2:25 ─── 3:00
  [Il Problema]  [L'Architettura]  [Scena 1: Social]  [Scena 2: Deep Tech]  [Scena 3: Peace of Mind]  [Recap Stack]
```

### [0:00 - 0:35] L'Intro: Il Sovraccarico Cognitivo Quotidiano
* **Visual:** Montaggio rapido e dinamico. L'utente esce di fretta di casa borbottando: *"Spina del ferro staccata, porta chiusa a chiave"*. 
* Arriva a un evento tech o coworking, una persona si presenta: *"Piacere, sono Dario, Tech Lead di CloudScale, mandami la documentazione del tuo progetto entro domani!"*.
* Poi entra in riunione: il team discute animatamente di un nuovo framework (*"Dobbiamo valutare AgentCore di AWS e risolvere il memory leak sulla libreria X"*).
* **Voiceover:** *"Ogni giorno la nostra mente è bombardata da centinaia di micro-informazioni: promesse fatte, ansie domestiche e argomenti tecnici che non abbiamo il tempo di approfondire. I normali assistenti vocali ti costringono a fermarti e digitare. Vi presentiamo EXAMEN."*

### [0:35 - 1:15] Dietro le Quinte: Bee, Bedrock & AgentCore
* **Visual:** Primo piano del microfono/wearable Bee appuntato alla giacca. Sul monitor dello sviluppatore si vede lo stream in tempo reale di `beemcp`.
* Viene mostrato a schermo il log della pipeline:
  1. *Gatekeeper (Claude 3.5 Haiku):* Filtra il 95% di chiacchiere inutili a costo zero.
  2. *Routing:* Smista istantaneamente il parlato tra Social, Azioni e Deep Topic.
* **Voiceover:** *"Alimentato dallo stream continuo di Bee, EXAMEN (dal latino 'sciame d'api' e 'esame attento') utilizza AWS Bedrock con un Gatekeeper semantico ad altissima efficienza. Riconosce ciò che conta davvero, attiva l'harness di AgentCore e arricchisce autonomamente i dati."*

### [1:15 - 1:50] Scena 1: Social Recall (Memoria Relazionale)
* **Visual:** L'utente ritrova Dario 40 minuti dopo alla macchinetta del caffè. Guarda per 2 secondi lo smartwatch o il telefono.
* Sullo schermo appare la notifica/card: *"Dario - Tech Lead @ CloudScale | To-do: Inviare documentazione"*.
* L'utente lo saluta chiamandolo per nome senza alcuna esitazione: *"Ciao Dario! Ti invio la documentazione oggi pomeriggio"*.
* **Voiceover:** *"Mai più l'imbarazzo di dimenticare un nome o una promessa appena fatta."*

### [1:50 - 2:25] Scena 2: Deep Meeting Intelligence su Echo Show
* **Visual:** Terminata la riunione, l'utente torna alla scrivania davanti al suo **Echo Show 10/15**.
* Utente: *"Alexa, mostrami il report sulle tecnologie discusse nella riunione di stamattina."*
* Alexa risponde: *"Ho preparato un dossier su AWS AgentCore con le fonti ufficiali e due action item per il team."*
* A schermo, tramite **ext-apps**, appare un'interfaccia interattiva elegante con la spiegazione tecnica, i link alla documentazione e i task da spuntare.
* **Voiceover:** *"Invece di prendere appunti frammentari, EXAMEN ha rilevato i temi chiave, ha effettuato ricerche sul web e ha sintetizzato un dossier esecutivo pronto all'uso."*

### [2:25 - 2:50] Scena 3: Action-State & Peace of Mind
* **Visual:** L'utente è in auto o alla scrivania e viene assalito dalla classica ansia: *"Oddio, ho staccato il ferro da stiro?"*.
* Chiede ad Alexa: *"Alexa, ho staccato il ferro?"*.
* Alexa risponde: *"Sì, alle 08:14 hai confermato di aver staccato la spina del ferro prima di uscire."*
* A schermo compare il badge verde con timestamp certificato e la trascrizione esatta della frase pronunciata.
* **Voiceover:** *"Nessuna ansia, nessuna perdita di tempo. Azioni verificate con timestamp esatto."*

### [2:50 - 3:00] Conclusione & Stack Tecnico
* **Visual:** Schermata riassuntiva finale con i loghi: **Bee Wearable AI + AWS Bedrock + AgentCore + Alexa+ MCP**.
* **Voiceover:** *"EXAMEN trasforma l'ascolto ambientale nella tua mente aumentata per la vita quotidiana e il lavoro. Costruito con AWS Bedrock e Alexa+."*

---

## 📅 Tabella di Marcia di Sviluppo (4 Sprint Settimanali)

```
Settimana 1 (Ingestion & Gatekeeper)
├── Configurazione ambiente Bee CLI & test stream WebSocket con beemcp
├── Richiesta crediti AWS e configurazione modelli Bedrock (Haiku & Sonnet)
└── Test del prompt Gatekeeper per scremaggio accurato (>90% drop rate su noop)

Settimana 2 (AgentCore Harness & Deep Research)
├── Costruzione del grafo LangGraph / AgentCore con i 3 nodi specialistici
├── Integrazione del tool di Web Search per il canale Deep Topic
└── Setup database SQLite locale con indicizzazione full-text

Settimana 3 (Server MCP per Alexa+ & Ext-Apps UI)
├── Implementazione del server MCP (FastMCP Python) con i 4 tool core
├── Test interazione vocale locale tramite alexa-ai CLI e Cloudflare Tunnel
└── Realizzazione interfaccia grafica touch per Echo Show tramite ext-apps iframe

Settimana 4 (Polishing, Video Demo & Submission)
├── Test integrato end-to-end dello scenario video
├── Registrazione e montaggio video demo (1080p, audio pulito, sottotitoli in inglese)
├── Finalizzazione repository GitHub e documentazione Devpost
└── Submission entro la deadline ufficiale
```

---

## 📝 Regola del "Friction Log" (+10% Punteggio Bonus)

Il regolamento dell'hackathon premia con un **bonus del 10%** i team che tengono un diario di bordo trasparente (*Friction Log*) delle difficoltà incontrate e risolte usando gli SDK (Bee CLI, Alexa+ CLI, Bedrock). 

Durante lo sviluppo, aggiornare regolarmente un file dedicato `FRICTION_LOG.md` annotando:
1. Eventuali bug o ambiguità riscontrate nelle librerie ufficiali.
2. Come il team ha aggirato il problema (workaround o pull request).
3. Feedback costruttivo per i team ingegneristici di Amazon e Bee.
