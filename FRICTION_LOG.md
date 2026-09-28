# 📝 EXAMEN Friction Log (+10% Hackathon Bonus)

> Questo documento tiene traccia quotidiana delle difficoltà tecniche, bug, attriti di integrazione e soluzioni adottate durante l'utilizzo degli SDK e delle piattaforme ufficiali: **Bee CLI / beemcp**, **AWS Bedrock & AgentCore**, e **Alexa+ CLI / ext-apps**.

---

## Modello di Registrazione Evento

Ogni volta che si incontra un problema durante lo sviluppo, documentarlo secondo il seguente formato:

```markdown
### [YYYY-MM-DD] - Componente / SDK
* **Contesto:** Cosa stavamo cercando di fare.
* **Problema Riscontrato (Friction):** Errore, crash, documentazione incompleta o comportamento imprevisto.
* **Workaround / Soluzione:** Come abbiamo superato il blocco.
* **Feedback per il team della piattaforma:** Come Amazon o Bee potrebbero migliorare l'esperienza per gli sviluppatori in futuro.
```

---

## Log delle Sessioni

### [2026-09-28] - Setup Architetturale & Decisione di Routing
* **Contesto:** Definizione dell'ingestion layer tra lo stream continuo di Bee e l'harness di elaborazione.
* **Problema Riscontrato (Friction):** Inviare ogni singolo frammento audio trascritto a modelli di ragionamento complessi (es. Claude 3.5 Sonnet) comporterebbe latenze elevate (>2-3s) e consumo insostenibile di token per il 90% di conversazioni irrilevanti.
* **Workaround / Soluzione:** Implementato un pattern a due stadi: un **Gatekeeper Semantico** ultra-veloce con modello compatto (Claude 3.5 Haiku o Amazon Nova Micro) con sliding window da 30-45s che scarta immediatamente i blocchi `noop`, attivando i nodi di estrazione e ricerca solo in caso di trigger rilevato.
* **Feedback per il team della piattaforma:** Sarebbe estremamente utile disporre a livello di SDK Bee di un flag nativo di VAD (Voice Activity Detection) e segmentation semantica basata su pause prolungate direttamente nel flusso WebSocket.
