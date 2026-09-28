"""Data contracts and schemas for EXAMEN."""

from datetime import datetime
from typing import Annotated, List, Literal, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ============================================================================
# 1. Output Classificatore Gatekeeper (Stadio 1)
# ============================================================================
class ChunkClassification(BaseModel):
    categories: List[Literal["social", "action", "deep_topic", "noop"]] = Field(
        description="Categorie rilevate nel chunk di trascrizione. 'noop' se privo di valore persistente."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Livello di confidenza generale della classificazione."
    )
    summary_hint: str = Field(
        default="",
        description="Breve sintesi di 1 riga che riassume il contenuto utile rilevato."
    )


# ============================================================================
# 2. Canale Social Recall (Stadio 3A)
# ============================================================================
class SocialEntity(BaseModel):
    id: Optional[str] = Field(default=None, description="Identificativo univoco del record.")
    person_name: str = Field(description="Nome e/o cognome della persona incontrata.")
    company_or_role: Optional[str] = Field(default=None, description="Azienda, ruolo o contesto professionale.")
    contact_info: Optional[str] = Field(default=None, description="Email, handle social, telefono se menzionati.")
    commitments: List[str] = Field(
        default_factory=list,
        description="Promesse fatte all'interlocutore o che l'interlocutore ha fatto all'utente."
    )
    key_topics: List[str] = Field(
        default_factory=list,
        description="Tag o argomenti salienti discussi durante l'interazione."
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Timestamp ISO dell'incontro."
    )


# ============================================================================
# 3. Canale Action-State & Routine Task (Stadio 3B)
# ============================================================================
class VerifiedAction(BaseModel):
    id: Optional[str] = Field(default=None, description="Identificativo univoco dell'azione.")
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
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Timestamp ISO del momento in cui l'azione è stata confermata."
    )
    is_revoked: bool = Field(
        default=False,
        description="True se l'azione è stata successivamente annullata o smentita."
    )


# ============================================================================
# 4. Canale Deep Topic Research (Stadio 3C)
# ============================================================================
class TopicExtraction(BaseModel):
    topic_title: str = Field(description="Titolo sintetico dell'argomento, bug o tecnologia.")
    context_type: Literal["bug", "feature_discussion", "tech_stack", "academic_lecture"] = Field(
        description="Tipologia di contesto da cui è scaturito il tema."
    )
    search_queries: List[str] = Field(
        default_factory=list,
        description="1-3 query di ricerca web formulate per approfondire l'argomento su fonti autorevoli."
    )
    key_questions: List[str] = Field(
        default_factory=list,
        description="Domande aperte o aspetti tecnici da chiarire nel report."
    )


class BriefingReport(BaseModel):
    id: Optional[str] = Field(default=None, description="Identificativo univoco del briefing.")
    topic_title: str = Field(description="Titolo dell'argomento approfondito.")
    context_type: str = Field(description="Tipologia di contesto.")
    executive_summary: List[str] = Field(
        default_factory=list,
        description="Sintesi esecutiva in 3-4 punti elenco."
    )
    deep_dive_markdown: str = Field(
        default="",
        description="Dossier approfondito con definizioni, soluzioni o documentazione in Markdown."
    )
    web_sources: List[str] = Field(
        default_factory=list,
        description="URL e fonti esterne consultate."
    )
    action_items: List[str] = Field(
        default_factory=list,
        description="Task suggeriti o step successivi per il team o lo studente."
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Data e ora di creazione del report."
    )


# ============================================================================
# 5. Stato del Grafo LangGraph
# ============================================================================
class ExamenState(TypedDict, total=False):
    raw_transcript: str
    timestamp: str
    session_id: str
    categories: List[str]
    confidence: float
    summary_hint: str
    social_data: Optional[SocialEntity]
    action_data: Optional[VerifiedAction]
    topic_extracted: Optional[TopicExtraction]
    briefing_report: Optional[BriefingReport]
    error: Optional[str]
