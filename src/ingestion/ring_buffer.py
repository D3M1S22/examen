"""Context Ring Buffer for ambient audio streaming in EXAMEN.

Maintains a FIFO rolling buffer of the last N utterance chunks per conversation,
enabling pronoun/anaphora resolution without inflating edge LLM screening costs.
Supports asynchronous speaker diarization patching.
"""

from collections import deque
from datetime import datetime
from typing import Dict, List, Literal, Optional

from src.core.schemas import UtteranceChunk


class ContextRingBuffer:
    """FIFO rolling buffer retaining the last N chunks per active conversation session."""

    def __init__(self, capacity: int = 4):
        self.capacity = max(1, capacity)
        self.buffers: Dict[str, deque[UtteranceChunk]] = {}

    def push(self, *args, **kwargs) -> None:
        """Pushes an incoming utterance chunk into the rolling FIFO buffer.
        
        Supports both push(chunk) and push(conv_id, chunk).
        """
        if len(args) == 2:
            # push(conv_id, chunk) or push(chunk, conv_id)
            if isinstance(args[0], str) and (isinstance(args[1], UtteranceChunk) or isinstance(args[1], dict)):
                conv_id, chunk = args[0], args[1]
            else:
                chunk, conv_id = args[0], args[1]
        elif len(args) == 1:
            chunk = args[0]
            conv_id = kwargs.get("conv_id") or getattr(chunk, "conversation_uuid", "default_session")
        elif "chunk" in kwargs:
            chunk = kwargs["chunk"]
            conv_id = kwargs.get("conv_id") or getattr(chunk, "conversation_uuid", "default_session")
        else:
            raise ValueError("ContextRingBuffer.push requires a chunk argument")

        if not isinstance(chunk, UtteranceChunk) and isinstance(chunk, dict):
            chunk = UtteranceChunk(**chunk)

        conv_id = conv_id or getattr(chunk, "conversation_uuid", "default_session") or "default_session"
        if conv_id not in self.buffers:
            self.buffers[conv_id] = deque(maxlen=self.capacity)
        self.buffers[conv_id].append(chunk)

    def get_historical_context(
        self, conv_id: str = "default_session", exclude_current: bool = True
    ) -> List[UtteranceChunk]:
        """Retrieves prior chunks in chronological order.
        
        Args:
            conv_id: The conversation session identifier.
            exclude_current: If True, excludes the most recently pushed chunk.
        """
        buffer = self.buffers.get(conv_id, deque())
        items = list(buffer)
        if exclude_current and items:
            return items[:-1]
        return items

    def get_concatenated_context_text(
        self, conv_id: str = "default_session", exclude_current: bool = True, max_chars: int = 1000
    ) -> str:
        """Formats prior utterances into dialogue lines for LLM prompts."""
        history = self.get_historical_context(conv_id, exclude_current=exclude_current)
        if not history:
            return ""
        lines = []
        for h in history:
            role_tag = f" ({h.speaker_role})" if h.speaker_role and h.speaker_role != "unknown" else ""
            speaker_label = f"{h.speaker_id or 'Speaker'}{role_tag}"
            lines.append(f"[{speaker_label}]: {h.text}")
        full_text = "\n".join(lines)
        if len(full_text) > max_chars:
            return full_text[-max_chars:]
        return full_text

    def get_rolling_summary_hint(
        self, conv_id: str = "default_session", max_chars: int = 300
    ) -> str:
        """Lightweight 1-line or short summary snippet of recent prior speech for Gatekeeper anaphora resolution."""
        text = self.get_concatenated_context_text(conv_id, exclude_current=True, max_chars=max_chars)
        return text if text.strip() else ""

    def patch_speaker(
        self,
        *args,
        **kwargs,
    ) -> bool:
        """Retrospectively patches diarization speaker info for an earlier chunk in the buffer.
        
        Supports patch_speaker(chunk_id, speaker_id, speaker_role, conv_id)
        and patch_speaker(conv_id, chunk_id, speaker_id, speaker_role).
        """
        if len(args) == 4:
            # Determine if args[0] is conv_id or chunk_id
            if args[0] in self.buffers:
                conv_id, chunk_id, speaker_id, speaker_role = args
            else:
                chunk_id, speaker_id, speaker_role, conv_id = args
        elif len(args) == 3:
            chunk_id, speaker_id, speaker_role = args
            conv_id = kwargs.get("conv_id")
        elif len(args) == 2:
            chunk_id, speaker_id = args
            speaker_role = kwargs.get("speaker_role")
            conv_id = kwargs.get("conv_id")
        else:
            chunk_id = kwargs.get("chunk_id", "")
            speaker_id = kwargs.get("speaker_id", "")
            speaker_role = kwargs.get("speaker_role")
            conv_id = kwargs.get("conv_id")

        target_buffers = [self.buffers[conv_id]] if (conv_id and conv_id in self.buffers) else list(self.buffers.values())
        patched = False
        for buf in target_buffers:
            for chunk in buf:
                if str(chunk.chunk_id) == str(chunk_id) or str(getattr(chunk, "utterance_id", "")) == str(chunk_id):
                    chunk.speaker_id = speaker_id
                    if speaker_role:
                        chunk.speaker_role = speaker_role
                    patched = True
        return patched

    def get_last_chunk(self, conv_id: str = "default_session") -> Optional[UtteranceChunk]:
        """Returns the most recent chunk pushed to the buffer, if any."""
        buffer = self.buffers.get(conv_id)
        if buffer and len(buffer) > 0:
            return buffer[-1]
        return None

    def clear(self, conv_id: Optional[str] = None) -> None:
        """Clears buffer for a specific conversation session or all sessions."""
        if conv_id:
            if conv_id in self.buffers:
                self.buffers[conv_id].clear()
        else:
            self.buffers.clear()
