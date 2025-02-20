#!/usr/bin/env python3

from __future__ import annotations
import asyncio
import os
import signal
import sys
from typing import List, Any

from loguru import logger
from pythclient.solana import SOLANA_DEVNET_HTTP_ENDPOINT, SOLANA_DEVNET_WS_ENDPOINT

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pythclient.pythclient import PythClient  # noqa
from pythclient.ratelimit import RateLimit  # noqa
from pythclient.pythaccounts import PythPriceAccount  # noqa
from pythclient.utils import get_key # noqa

logger.enable("pythclient")

RateLimit.configure_default_ratelimit(overall_cps=9, method_cps=3, connection_cps=3)

to_exit = False


def set_to_exit(sig: Any, frame: Any):
    print("Program interrupted, exiting...", sig, frame)
    global to_exit
    to_exit = True


signal.signal(signal.SIGINT, set_to_exit)


async def main():
    global to_exit
    use_program = len(sys.argv) >= 2 and sys.argv[1] == "program"
    network = 'devnet'

    v2_first_mapping_account_key = get_key(network, "mapping")
    v2_program_key = get_key(network, "program")

    print(f"Price dump started with mapping account key: {v2_first_mapping_account_key}")
    print(f"Price dump started with program key: {v2_program_key}")
    
    # Add one level of checking if the first mapping account key exists
    if v2_first_mapping_account_key is None:
        print(f"First mapping account key for {network} not found")
        return

    async with PythClient(
        first_mapping_account_key=v2_first_mapping_account_key,
        program_key=v2_program_key if use_program else None,
        solana_endpoint=SOLANA_DEVNET_HTTP_ENDPOINT, # replace with the relevant cluster endpoints
        solana_ws_endpoint=SOLANA_DEVNET_WS_ENDPOINT # replace with the relevant cluster endpoints
    ) as c:
        await c.refresh_all_prices()
        products = await c.get_products()
        all_prices: List[PythPriceAccount] = []
        for p in products:
            print(p.key, p.attrs)
            prices = await p.get_prices()
            for _, pr in prices.items():
                all_prices.append(pr)
                print(
                    pr.key,
                    pr.product_account_key,
                    pr.price_type,
                    pr.aggregate_price_status,
                    pr.aggregate_price,
                    "p/m",
                    pr.aggregate_price_confidence_interval,
                )
            break
        
        ws = c.create_watch_session()
        await ws.connect()
        if use_program and v2_program_key is not None:
            # Only subscribe to use program when both flag is turned on and 
            # the program key exists from the dns resolver
            print(f"Subscribing to program account with the program key {v2_program_key}")
            await ws.program_subscribe(v2_program_key, await c.get_all_accounts())
        else:
            print("Subscribing to all prices")
            for account in all_prices:
                await ws.subscribe(account)
        print("Subscribed!")

        while True:
            if to_exit:
                break
            update_task = asyncio.create_task(ws.next_update())
            while True:
                if to_exit:
                    update_task.cancel()
                    break
                done, _ = await asyncio.wait({update_task}, timeout=1)
                if update_task in done:
                    pr = update_task.result()
                    if isinstance(pr, PythPriceAccount):
                        assert pr.product
                        print(
                            pr.last_slot,
                            pr.valid_slot,
                            pr.product.symbol,
                            pr.price_type,
                            pr.aggregate_price_status,
                            pr.aggregate_price,
                            "p/m",
                            pr.aggregate_price_confidence_interval,
                        )
                        break

        print("Unsubscribing...")
        if use_program and v2_program_key is not None:
            print("Disconnecting program subscription")
            await ws.program_unsubscribe(v2_program_key)
        else:
            print("Disconnecting all prices subscription")
            for account in all_prices:
                await ws.unsubscribe(account)
        await ws.disconnect()
        print("Disconnected")

asyncio.run(main())
