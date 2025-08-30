import aiohttp
import os
import logging

from fastapi import APIRouter, HTTPException
from hexbytes import HexBytes
from eth_typing import HexStr
from eth_account import Account
from eth_account.typed_transactions.typed_transaction import TypedTransaction

from models import RPC, TxInfo
from web3 import Web3

w3c = Web3(Web3.HTTPProvider(f"{os.environ['QUICKNODE_URL']}{os.environ['QUICKNODE_API_KEY']}"))

logger = logging.getLogger(__name__)

rpc_router = APIRouter()

txs: dict[str, TxInfo] = {}

RELEASED_TX = 1
ACCEPTED_WARNING = 2

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
                print(f"Error response from TxSentinel API: {response_body}")
                return {
                    "status": "failed",
                    "message": f"Error evaluating transaction: HTTP {resp.status}",
                    "risks_detected": []
                }
            else:
                print(f"Successfully invoked TxSentinel API: {response_body}")
                agent_validations = response_body.get("validations", {}).get("agent", {})
                request_result = {
                    "status": agent_validations.get("status", "approved"),
                    "message": agent_validations.get("message", "Transaction evaluated successfully."),
                    "risks_detected": agent_validations.get("risks_detected", [])
                }
                print(f"Request result: {request_result}")
                return request_result

async def process_tx(tx_hash: str) -> tuple[int, str]:
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
        "reason": ""
    })

    if veredict["status"] != "approved":
        logger.warning(f"TX {tx_hash}, CANCELED.")
        return (ACCEPTED_WARNING, "")

    logger.info(f"TX {tx_hash} ALLOWED, RELEASING.")
    return (RELEASED_TX, await release_tx(tx_hash))

@rpc_router.post("/")
async def rpc_handler(rpc: RPC) -> dict:
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

    try:
        t, s = await process_tx(tx_hash)
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
async def set_intent(body: dict):
    logger.info(f"Setting intent: {body['intent']}")
    # TODO guardar intent
    return {"status": "ok"}
