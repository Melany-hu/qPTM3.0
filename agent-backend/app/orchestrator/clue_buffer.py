"""Session-scoped literature clue accumulation."""

from __future__ import annotations

from app.orchestrator.schemas import LiteratureClue


class ClueBuffer:
    def __init__(self) -> None:
        self._clues: dict[str, LiteratureClue] = {}

    def add(self, clue: LiteratureClue) -> bool:
        if clue.pmid in self._clues:
            return False
        self._clues[clue.pmid] = clue
        return True

    def add_many(self, clues: list[LiteratureClue]) -> list[LiteratureClue]:
        new: list[LiteratureClue] = []
        for c in clues:
            if self.add(c):
                new.append(c)
        return new

    def all(self) -> list[LiteratureClue]:
        return list(self._clues.values())

    def pmids(self) -> list[str]:
        return list(self._clues.keys())

    def __len__(self) -> int:
        return len(self._clues)
