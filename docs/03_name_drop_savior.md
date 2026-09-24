# 🤝 The Name-Drop Savior

> **Track:** Bee (Wearable AI / Apple Watch with Bee Software)  
> **Mini-Challenge Eleggibile:** AWS Builder ($5.000 cash + $5.000 AWS credits)  
> **Target Device:** Bee Wearable Hardware / Apple Watch Companion  
> **Tagline:** *"Non scordare mai più un nome. L'intelligenza ambientale che ti salva dall'imbarazzo."*

---

## 1. Visione & Valore Unico

### Il Problema Reale
A conferenze, eventi di networking, cene di lavoro o feste, capita a chiunque: una persona si presenta (*"Piacere, sono Roberto, lavoro in FinTech"*), e 45 secondi dopo il suo nome è già svanito dalla memoria a breve termine. 
Quando 20 minuti più tardi la reincontri al buffet o devi presentarla a un collega, subentra il panico e l'imbarazzo sociale ("Come si chiamava?"). Nessuno ha il tempo né l'educazione di mettersi a digitare appunti sullo smartphone mentre parla.

### La Soluzione "Clever"
**The Name-Drop Savior** sfrutta l'ascolto continuo e passivo del wearable **Bee**:
* Bee cattura l'audio ambientale in background e invia il flusso trascritto via **Bee CLI / Bee Skill**.
* Un modello di Named Entity Recognition (NER) e context extraction rileva pattern di introduzione sociale (*"Piacere, mi chiamo X"*, *"Lui è il mio socio Y"*).
* Estrae istantaneamente: **Nome**, **Ruolo/Azienda**, **Argomento di conversazione** e **Timestamp**.
* Con un semplice doppio tocco sul wearable, un'occhiata all'Apple Watch o aprendo l'app companion sullo smartphone, compare una scheda essenziale:
  > **Ultimo incontro (14 min fa):** Roberto  
  > **Dettaglio:** Founder startup AI a Milano  
  > **Argomento discusso:** Round Seed e GPU clusters

---

## 2. Allineamento con i Criteri dei Giudici Amazon

| Criterio Ufficiale | Come lo soddisfa Name-Drop Savior |
| :--- | :--- |
| **Tech Implementation (25%)** | Utilizzo effettivo della **Bee CLI / Bee Skill** per lo streaming del transcript in tempo reale, combinato con un pipeline di Named Entity Recognition e caching locale a bassa latenza. |
| **Design & Glanceability (25%)** | UI "glanceable" per smartwatch/companion: 3 secondi di lettura per ottenere l'informazione critica senza distogliere l'attenzione dalla vita reale. |
| **Potential Impact (25%)** | Superpotere relazionale e professionale per chiunque partecipi a eventi, vendite, conferenze e incontri pubblici. |
| **Quality of Idea (Creative vs Obvious) (25%)** | Le regole ufficiali per Bee dicono: *"Obvious: simple notification relay, basic data logging. Creative: ambient context capture that informs a productivity workflow, real time functionality"*. Questo progetto cattura contesto ambientale per potenziare le capacità cognitive umane in tempo reale. |

---

## 3. Architettura Tecnica & Stack

```mermaid
graph TD
    Audio[Audio Ambientale] -->|Microfono Continuo| BeeDevice[Bee Wearable / Apple Watch]
    BeeDevice -->|Transcript Stream| BeeSkill[Bee CLI / Bee-Skill Interface]
    
    subgraph Local / Edge Pipeline
        BeeSkill --> StreamFilter[Regex & Acoustic Event Trigger]
        StreamFilter -->|Candidato Intro Rilevato| EntityExtractor[NER & Context Extractor]
    end

    subgraph AWS Intelligence Layer - Mini Challenge
        EntityExtractor -->|Prompt Strutturato| Bedrock[AWS Bedrock - Claude 3.5 / Nova]
        Bedrock -->|JSON: {name, context, role, tags}| KnowledgeGraph[(Local SQLite People Graph)]
    end

    subgraph Glanceable Output UI
        KnowledgeGraph -->|Haptic Vibration / Display| WatchUI[Apple Watch / Companion App]
        KnowledgeGraph -->|Query Vocale Rapida| VoiceQuery["Whisper to Bee: 'Chi era?'"]
    end
```

### Componenti Software
* **Bee Data Ingestion:** Flusso continuo tramite `bee-cli stream` o webhook della `bee-skill`.
* **NLP & Entity Extractor:**
  * Regex rapida di pre-filtraggio per formule di cortesia e presentazioni ("Piacere sono...", "Mi chiamo...", "Lui è...").
  * **AWS Bedrock (Claude 3.5 / Nova Micro):** Riceve la finestra temporale di 30 secondi e restituisce un JSON strutturato:
    ```json
    {
      "person_name": "Roberto Bianchi",
      "company_or_role": "CTO FinTech",
      "key_topics": ["Seed round", "AWS migration"],
      "timestamp": "2026-09-25T11:42:10Z"
    }
    ```
* **Storage & UI:** SQLite locale indicizzato per cronologia temporale. Interfaccia mobile/watch ultra-minimale con card ad alto contrasto.

---

## 4. Nuove Funzionalità ad Alto Impatto

1. **"Social Commitments Tracker":** Se durante la conversazione dici: *"Ti mando il link stasera"* o l'altro dice *"Chiamami martedì"*, Bee estrae l'impegno e lo aggiunge a una lista di promesse non mantenute.
2. **"Face-to-Voice Association":** Se abbinato alla fotocamera dello smartphone o a una foto scattata, abbina il nome alla foto del badge o del volto.
3. **"Topic Resumption Assistant":** Suggerisce una frase rompighiaccio per riagganciare la persona: *"Chiedigli com'è andato il pitch con i VC di cui ti parlava prima"*.

---

## 5. Criticità Tecniche & Strategie di Mitigazione

| Criticità / Rischio | Impatto | Strategia di Mitigazione Hackathon |
| :--- | :--- | :--- |
| **Privacy e consenso registrazione** | Alto | Elaborare solo metadati anonimizzati ed eliminare l'audio grezzo immediatamente dopo la trascrizione. Specificare che Bee funziona in modalità "Local Privacy First". |
| **Rumore di fondo nelle feste/conferenze** | Medio | Impostare una soglia di confidenza nel modello di trascrizione; richiedere pattern espliciti di presentazione. |
| **Hardware Bee fisico non disponibile** | Basso | Gli organizzatori consentono esplicitamente di usare la **Bee CLI** con file di test registrati o un **Apple Watch con software Bee**. |

---

## 6. Mini-Challenges & Friction Log Bonus

* **AWS Builder ($5k cash + $5k credits):**
  Usare AWS Bedrock per l'estrazione semantica zero-shot delle entità dal parlato informale.
* **Friction Log (+10% Bonus):**
  Documentare l'esperienza di configurazione di `bee-cli` e dell'interfacciamento locale via WebSocket con i tool per sviluppatori Bee.
