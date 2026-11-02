"""Внешние заказы. Основано на §7.14 и §16.7 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContractType(str, Enum):
    MONSTER_PARTS = "monster_parts"
    LIVE_MONSTER = "live_monster"
    ARTIFACT = "artifact"
    ANOMALY_DESTRUCTION = "anomaly_destruction"
    ANOMALY_PARTS = "anomaly_parts"
    KNOWLEDGE = "knowledge"


class ContractStatus(str, Enum):
    ACTIVE = "active"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class Contract:
    """Внешний заказ. (§7.14)"""
    id: int
    trader_id: int
    contract_type: ContractType
    required_item_type: str
    quantity: int
    min_quality: int = 0  # минимальное состояние предмета
    deadline_hour: int = 0
    reward: float = 0.0
    advance: float = 0.0
    advance_items: list[dict] = field(default_factory=list)
    penalty: float = 0.0
    difficulty: int = 50  # сложность 1-100
    status: ContractStatus = ContractStatus.ACTIVE
    accepted_by: int = -1  # npc_id или group_id
    accepted_hour: int = 0
    accepted_at_sector: int = 0

    @property
    def days_remaining(self) -> int:
        # caller должен передать current_hour
        return 0

    def is_expired(self, current_hour: int) -> bool:
        return current_hour > self.deadline_hour

    def is_accepted_expired(self, current_hour: int) -> bool:
        """Проверяет просрочку принятого заказа."""
        return current_hour > self.deadline_hour and self.status == ContractStatus.ACCEPTED and self.status == ContractStatus.ACCEPTED

    def is_active(self, current_hour: int) -> bool:
        if self.status != ContractStatus.ACTIVE:
            return False
        return current_hour <= self.deadline_hour

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "trader_id": self.trader_id,
            "contract_type": self.contract_type.value,
            "required_item_type": self.required_item_type,
            "quantity": self.quantity,
            "min_quality": self.min_quality,
            "deadline_hour": self.deadline_hour,
            "reward": self.reward,
            "advance": self.advance,
            "advance_items": self.advance_items,
            "penalty": self.penalty,
            "difficulty": self.difficulty,
            "status": self.status.value,
            "accepted_by": self.accepted_by,
        }


class ContractManager:
    """Управление контрактами."""

    def __init__(self):
        self.contracts: dict[int, Contract] = {}
        self._next_id: int = 0

    def create_contract(
        self,
        trader_id: int,
        contract_type: ContractType,
        required_item_type: str,
        quantity: int,
        reward: float,
        deadline_hours: int = 48,
        advance: float = 0.0,
        advance_items: list[dict] | None = None,
        penalty: float = 0.0,
        difficulty: int = 50,
        current_hour: int = 0,
    ) -> Contract:
        """Создаёт новый заказ (§16.7)."""
        deadline = current_hour + deadline_hours

        contract = Contract(
            id=self._next_id,
            trader_id=trader_id,
            contract_type=contract_type,
            required_item_type=required_item_type,
            quantity=quantity,
            min_quality=0,
            deadline_hour=deadline,
            reward=reward,
            advance=advance,
            advance_items=advance_items or [],
            penalty=penalty,
            difficulty=difficulty,
        )
        self._next_id += 1
        self.contracts[contract.id] = contract
        return contract

    def accept_contract(
        self,
        contract_id: int,
        npc_id: int,
        sector_id: int,
        current_hour: int,
    ) -> bool:
        """NPC принимает заказ."""
        contract = self.contracts.get(contract_id)
        if not contract:
            return False
        if contract.status != ContractStatus.ACTIVE:
            return False
        if contract.is_expired(current_hour):
            return False

        contract.accepted_by = npc_id
        contract.accepted_hour = current_hour
        contract.accepted_at_sector = sector_id
        contract.status = ContractStatus.ACCEPTED
        return True

    def complete_contract(
        self,
        contract_id: int,
        current_hour: int,
    ) -> tuple[bool, float, dict]:
        """
        Завершает заказ.
        Возвращает (успех, reward, result_details).
        """
        contract = self.contracts.get(contract_id)
        if not contract:
            return False, 0.0, {}

        if contract.status != ContractStatus.ACCEPTED:
            return False, 0.0, {"error": "not_accepted"}

        if contract.is_expired(current_hour):
            contract.status = ContractStatus.FAILED
            return False, 0.0, {"error": "expired"}

        contract.status = ContractStatus.COMPLETED
        return True, contract.reward, {
            "contract_id": contract.id,
            "reward": contract.reward,
            "completed_hour": current_hour,
        }

    def fail_contract(
        self,
        contract_id: int,
        current_hour: int,
    ) -> tuple[bool, float, float, str]:
        """
        Провал заказа.
        Возвращает (успешно_проблема, penalty, debt, reason).
        """
        contract = self.contracts.get(contract_id)
        if not contract:
            return False, 0.0, 0.0, "not_found"

        if contract.status != ContractStatus.ACCEPTED:
            return False, 0.0, 0.0, "not_accepted"

        if contract.is_accepted_expired(current_hour):
            contract.status = ContractStatus.FAILED
            return True, contract.penalty, 0.0, "expired"

        contract.status = ContractStatus.FAILED
        return True, contract.penalty, contract.penalty, "not_completed_in_time"

    def expire_inactive_contracts(self, current_hour: int) -> list[int]:
        """Просрочивает не принятые заказы."""
        expired = []
        for cid, contract in self.contracts.items():
            if contract.status == ContractStatus.ACTIVE and contract.is_expired(current_hour):
                expired.append(cid)
        return expired

    def get_active_contracts(self, trader_id: int, current_hour: int) -> list[Contract]:
        """Получает активные заказы торговца (максимум 5 по ТЗ)."""
        max_active = 5
        result = []
        for c in self.contracts.values():
            if c.trader_id == trader_id and c.is_active(current_hour):
                result.append(c)
                if len(result) >= max_active:
                    break
        return result

    def get_accepted_contracts(self, npc_id: int) -> list[Contract]:
        """Получает принятые NPC заказы."""
        return [c for c in self.contracts.values()
                if c.accepted_by == npc_id and c.status == ContractStatus.ACCEPTED]

    def get_contract(self, contract_id: int) -> Contract | None:
        return self.contracts.get(contract_id)
