from __future__ import annotations
from abc import ABC,abstractmethod
from iras.models import ProviderReply
class Provider(ABC):
    @abstractmethod
    def complete(self,messages:list[dict],tools:list[dict])->ProviderReply: ...
