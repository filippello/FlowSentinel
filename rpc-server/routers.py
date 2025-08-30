import aiohttp
import os
import logging

from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from hexbytes import HexBytes
from eth_typing import HexStr
from eth_account import Account
from eth_account.typed_transactions.typed_transaction import TypedTransaction

from models import RPC, TxInfo, IntentRequest
from web3 import Web3

w3c = Web3(Web3.HTTPProvider(f"{os.environ['QUICKNODE_URL']}{os.environ['QUICKNODE_API_KEY']}"))

logger = logging.getLogger(__name__)

rpc_router = APIRouter()

txs: dict[str, TxInfo] = {}
intents: dict[str, str] = {}

INTENT_TIMEOUT = 3600

RELEASED_TX = 1
ACCEPTED_WARNING = 2

def clean_intents():
    global intents
    logger.info(f"Cleaning old intents {intents}")
    now = datetime.now()
    intents = {k: v for k, v in intents.items() if (now - datetime.strptime(k[-12:], "%Y%m%d%H%M")).seconds < INTENT_TIMEOUT}
    logger.info(f"Finished cleaning old intents {intents}")

async def release_tx(tx_hash: str) -> str:
    tx_info = txs[tx_hash]
    signed_raw_tx = HexStr(tx_info.signed_raw_tx)

    # send tx to blockchain
    # XXX: here we're using the qn_broadcastRawTransaction method
    # instead of the regular eth_sendRawTransaction method
    actual_hash = HexBytes(
        w3c.provider.make_request(
            "qn_broadcastRawTransaction",
            [signed_raw_tx]
        )["result"] # type: ignore
    ).to_0x_hex()

    txs.pop(tx_hash, None)

    return actual_hash

async def perform_request(body):
    async with aiohttp.ClientSession() as session:
        async with session.post(os.environ["API_URL"], json=body) as resp:
            response_body = await resp.json()
            if resp.status > 299:
                logger.info(f"Error response from TxSentinel API: {response_body}")
                return {
                    "status": "failed",
                    "message": f"Error evaluating transaction: HTTP {resp.status}",
                    "risks_detected": []
                }
            else:
                logger.info(f"Successfully invoked TxSentinel API: {response_body}")
                agent_validations = response_body.get("validations", {}).get("agent", {})
                request_result = {
                    "status": agent_validations.get("status", "approved"),
                    "message": agent_validations.get("message", "Transaction evaluated successfully."),
                    "risks_detected": agent_validations.get("risks_detected", [])
                }
                logger.info(f"Request result: {request_result}")
                return request_result

async def process_tx(tx_hash: str, intent: str) -> tuple[int, str]:
    tx_info = txs[tx_hash]

    tx_decoded = TypedTransaction.from_bytes(
        HexBytes(tx_info.signed_raw_tx)
    ).as_dict()

    to_raw = tx_decoded.get("to")
    to_address = HexBytes(to_raw).to_0x_hex() if to_raw is not None else None

    data_raw = tx_decoded.get("data", b"")
    data_hex = HexBytes(data_raw).to_0x_hex() if data_raw else "0x"

    value = int(tx_decoded.get("value", 0))

    veredict = await perform_request({
        "chainId": w3c.eth.chain_id,
        "from_address": tx_info.from_account,
        "to_address": to_address,
        "data": data_hex,
        "value": str(value),  # <-- string
        "reason": intent
    })

    if veredict["status"] != "approved":
        logger.warning(f"TX {tx_hash}, CANCELED.")
        return (ACCEPTED_WARNING, veredict["message"])

    logger.info(f"TX {tx_hash} ALLOWED, RELEASING.")
    return (RELEASED_TX, await release_tx(tx_hash))

def get_intent_key(request: Request) -> str:
    return str(f"{request.client.host}:{datetime.now().strftime('%Y%m%d%H%M')}")

@rpc_router.post("/")
async def rpc_handler(rpc: RPC, request: Request) -> dict:
    clean_intents()
    if rpc.method != "eth_sendRawTransaction":
        logger.debug(f"DELEGATING REQUEST TO PROVIDER: {rpc.method}")
        return w3c.provider.make_request(rpc.method, rpc.params) # type: ignore
    logger.info(f"INTERCEPTING REQUEST: {rpc.method}")

    tx = TypedTransaction.from_bytes(
        HexBytes(rpc.params[0])
    ).as_dict()

    from_account = Account.recover_transaction(rpc.params[0])
    tx["from"] = from_account

    tx_hash = w3c.keccak(
        HexBytes(rpc.params[0])
    ).to_0x_hex()

    # unsign the tx
    del tx["v"]
    del tx["r"]
    del tx["s"]

    txs[tx_hash] = TxInfo(
        tx_hash=tx_hash,
        signed_raw_tx=rpc.params[0],
        from_account=from_account,
    )

    intent = intents[get_intent_key(request)]

    try:
        t, s = await process_tx(tx_hash, intent)
    except Exception as e:
        logger.error(f"ERROR PROCESSING TX: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error processing transaction."
        )
    if t == RELEASED_TX:
        return {"result": s, "id": rpc.id, "jsonrpc": "2.0"}
    elif t == ACCEPTED_WARNING:
        raise HTTPException(
            status_code=410,
            detail=f"WARNING ACCEPTED: {s}"
        )
    raise

@rpc_router.post("/intents")
async def set_intent(intent_request: IntentRequest, request: Request):
    clean_intents()
    intent = intent_request.intent
    if intent is None:
        raise HTTPException(status_code=400, detail="Intent is required.")
    intents[get_intent_key(request)] = intent
    return {"status": "ok"}
