# 🛡️ Context-Catcher (Anti-Spoiler Companion)

> **Track:** Fire TV (Vega OS & Fire OS / React Native)  
> **Mini-Challenge Eleggibile:** AWS Builder ($5.000 cash + $5.000 AWS credits) & Open Source ($5.000)  
> **Target Platform:** Fire TV Stick 4K / Vega OS TV Simulator  
> **Tagline:** *"Metti in pausa, scopri chi è sullo schermo. Zero spoiler, 100% contesto."*

---

## 1. Visione & Valore Unico

### Il Problema Reale
Serie TV complesse e corali (*House of the Dragon*, *Dark*, *Succession*, *Il Trono di Spade*, *Dune*, *Severance*) presentano decine di personaggi, casate, parentele segrete e alleanze mutevoli. Lo spettatore medio dimentica continuamente chi sia un personaggio secondario o quale sia il suo legame con il protagonista. 
Tuttavia, **cercare su Google o Wikipedia dallo smartphone è letale**: i suggerimenti di ricerca e le prime righe contengono spoiler devastanti (*"Morte di [Personaggio] nell'episodio 7"*).
Amazon X-Ray esiste già, ma offre solo elenchi statici di attori e curiosità da IMDB, non spiegando **cosa quel personaggio ha fatto e con chi è alleato fino a quel preciso istante narrativo**.

### La Soluzione "Clever"
**Context-Catcher** è un companion overlay nativo per Fire TV / Vega OS:
* Quando lo spettatore preme **PAUSA** sul telecomando, l'app aggancia l'evento del player video e visualizza un overlay semitrasparente fluido ed elegante.
* Mostra i personaggi attualmente in scena e una **mappa interattiva delle relazioni**, rigorosamente bloccata e filtrata temporalmente alla **Stagione S, Episodio E, Minuto M**.
* Qualsiasi evento, tradimento o morte che avverrà negli episodi successivi è oscurato ("Classificato / Evento Futuro").
* Navigabile intuitivamente tramite **telecomando D-Pad** o interrogabile via voce (*"Alexa, chi è il tipo con la cicatrice e perché odia il re?"*).

---

## 2. Allineamento con i Criteri dei Giudici Amazon

| Criterio Ufficiale | Come lo soddisfa Context-Catcher |
| :--- | :--- |
| **Tech Implementation (25%)** | App completa **React Native per Vega OS**, integrata con l'interfaccia W3C Media Player, focus engine per telecomando TV (`react-native-tvos` / Vega SDK) e API di intelligenza temporale. |
| **Design TV First (25%)** | Interfaccia living-room ottimizzata per 10-foot UI: contrasti elevati, focus highlight animati, nessun cursore mouse, leggibilità da 3 metri di distanza. |
| **Potential Impact (25%)** | Migliora l'esperienza di visione per milioni di abbonati Prime Video e piattaforme di streaming. Adattabile a qualsiasi film o serie TV. |
| **Quality of Idea (Creative vs Obvious) (25%)** | I criteri ufficiali di Fire TV penalizzano esplicitamente *"basic streaming UI, simple video player"* e premiano *"AI-enhanced viewing that adapts to household patterns, multi-modal UX combining voice + D-pad + visual in a single flow"*. Context-Catcher rientra precisamente in questa definizione. |

---

## 3. Architettura Tecnica & Stack

```mermaid
graph TD
    User([Utente / Telecomando]) -->|Pressione PAUSA| VideoPlayer[Vega W3C Media Player]
    VideoPlayer -->|Event: onPause(timestamp, episode_id)| ContextEngine[Context-Catcher Core]
    
    subgraph Fire TV / Vega OS Client
        ContextEngine --> FocusManager[TV Focus & D-Pad Manager]
        FocusManager --> OverlayUI[React Native TV Overlay]
        OverlayUI --> CharCarousel[Carosello Personaggi in Scena]
        OverlayUI --> RelationDrawer[Grafo Relazioni & Segreti]
    end

    subgraph AWS Backend & Data Pipeline - Mini Challenge
        ContextEngine -->|Query API| Gateway[AWS API Gateway]
        Gateway --> Lambda[AWS Lambda Context Resolver]
        Lambda --> Bedrock[AWS Bedrock - Claude 3.5]
        Bedrock --> KnowledgeBase[(Bedrock Knowledge Base - Episodic Synopses)]
        Lambda --> TMDB[(TMDB & TVMaze Data)]
    end

    Lambda -->|Grafo filtrato senza spoiler| ContextEngine
```

### Componenti Software
* **Vega OS / React Native Client:** Basato sullo starter ufficiale Amazon `AmazonAppDev/react-native-multi-tv-app-sample` o `AmazonAppDev/vega-video-sample`. Focus controller per gestione telecomando (D-pad up/down/left/right, select, back).
* **Motore Temporale Anti-Spoiler (AWS Bedrock):**
  * Database a grafo o JSON strutturato con entità personaggio e archi di relazione aventi proprietà di validità temporale: `{ relationship: "Allied", valid_from: "S01E01", valid_until: "S02E04", spoiler_level: 0 }`.
  * Amazon Bedrock genera su richiesta riassunti sintetici da 2 frasi: *"Chi è X per il personaggio Y in questo episodio?"*.
* **Media Assets:** Video open source di test (es. Blender Foundation Movies con finta metadata serie epica) con riproduzione video fluida nel simulatore Vega.

---

## 4. Nuove Funzionalità ad Alto Impatto

1. **"Quick Voice Whispering":** Tenendo premuto il tasto microfono sul telecomando o parlando a voce alta: *"Alexa, chi è il consigliere vestito di nero?"*. L'overlay si apre direttamente sulla scheda del personaggio corrispondente.
2. **"Relationship Matrix" (Mappa delle Fazioni):** Mostra un mini-radar grafico che illustra le fazioni attuali (es. Alleati, Nemici, Truffatori) aggiornate solo agli accordi stipulati fino a quell'episodio.
3. **"Previously on... Just for This Guy":** Un micro-video o bullet points con 3 flashback veloci: *"L'ultima volta che lo abbiamo visto (S01E08), ha rubato la chiave del castello"*.

---

## 5. Criticità Tecniche & Strategie di Mitigazione

| Criticità / Rischio | Impatto | Strategia di Mitigazione Hackathon |
| :--- | :--- | :--- |
| **Navigazione di grafi complessi con il telecomando (D-Pad)** | Alto | Non tentare di fare una canvas graph 2D libera navigabile con le frecce. Usare invece un **Carosello orizzontale a schede** per i personaggi, con un drawer verticale per le connessioni relazionali. Semplicissimo da usare con sole 4 frecce. |
| **Copyright video reali (HBO, Netflix, Prime)** | Medio | Utilizzare clip video royalty-free (es. trailer cinematografici open-source o Big Buck Bunny/Sintel) e mappargli sopra un finto lore medievale o sci-fi complesso per la demo. |
| **Setup ambiente Vega OS** | Medio | Sfruttare il repository di riferimento Amazon e testare sia su simulatore Vega che come fallback su Fire TV Stick via ADB (`adb install`). |

---

## 6. Mini-Challenges & Friction Log Bonus

* **AWS Builder ($5k cash + $5k credits):**
  Utilizzare **Amazon Bedrock Knowledge Bases** per vettorializzare le sinossi degli episodi e interrogare l'LLM con un filtro sui metadati temporali (`episode <= current_episode`).
* **Open Source ($5k cash + $5k credits):**
  Estrarre il componente TV React Native `react-native-tv-spoiler-free-graph` e pubblicarlo come package open-source per l'ecosistema React Native TV.
* **Friction Log (+10% Bonus):**
  Documentare l'esperienza di sviluppo dell'overlay sopra il W3C Media Player in Vega OS, segnalando eventuali problemi di z-index e focus stealing del player.

---

## 7. Struttura del Video Demo (2:45 min)

* **0:00 - 0:30 (Il Problema):** Schermata divisa: un ragazzo guarda una serie complessa, prende il telefono per cercare un personaggio e legge: *"Morte epica di Jon Snow"* ➔ Grido di frustrazione.
* **0:31 - 1:15 (La Soluzione in Azione):** Premuta del tasto Pausa sulla Fire TV. L'overlay Context-Catcher scivola dolcemente sullo schermo con un look dark-glassmorphism cinematografico.
* **1:16 - 2:00 (Interazione D-Pad & Voice):** Navigazione fluida tra i personaggi con il telecomando, visualizzazione del legame tra due personaggi e riassunto senza spoiler.
* **2:01 - 2:30 (Filtro Temporale):** Mostra cosa succede cambiando episodio: le relazioni cambiano dinamicamente senza mai rivelare il futuro.
* **2:31 - 2:45 (Tech Architecture):** Breve recap dello stack: React Native su Vega OS + AWS Bedrock Knowledge Bases.
