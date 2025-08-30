from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

@dataclass
class TxInfo:
    tx_hash: str
    signed_raw_tx: str
    from_account: str
    allowed: bool = False
    accepted_warning: str = ""

class CamelCaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class RPC(CamelCaseModel):
    method: str
    params: list
    id: int | str
    jsonrpc: str
