""" 
This is the module for establishing pyth network connectionself.
Taking the price feed from solana dev-net

For demonstration purpose, price from one symbol will be filtered 
out for visualization
"""

import asyncio, json, os, sys, signal, logging

from typing import List, Any
from pythclient.solana import SOLANA_DEVNET_HTTP_ENDPOINT, SOLANA_DEVNET_WS_ENDPOINT

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pythclient.pythclient import (
    PythClient,
)  # noqa
from pythclient.pythaccounts import PythPriceAccount  # noqa
from pythclient.utils import get_key  # noqa


# Set of user connection to maintain globally
# It will be accessed upon new client connection or
# during broadcasting of new pricing updates
USER = None
to_exit = False


def set_to_exit(sig: Any, frame: Any):
    global to_exit
    to_exit = True


signal.signal(signal.SIGINT, set_to_exit)


async def price_feed():
    global to_exit, USER
    use_program = len(sys.argv) >= 2 and sys.argv[1] == "program"
    v2_first_mapping_account_key = get_key("devnet", "mapping")
    if v2_first_mapping_account_key is None:
        # if there is no mapping account key from dns resolver, do nothing
        print("Unable to get the devnet account mapping key")
        v2_first_mapping_account_key = ""

    v2_program_key = get_key("devnet", "program")
    if v2_program_key is None:
        # unable to retrieve v2 program key
        print("Unable to get the devnet program key")
        v2_program_key = ""

    async with PythClient(
        first_mapping_account_key=v2_first_mapping_account_key,
        program_key=v2_program_key if use_program else None,
        solana_endpoint=SOLANA_DEVNET_HTTP_ENDPOINT,  # replace with the relevant cluster endpoints
        solana_ws_endpoint=SOLANA_DEVNET_WS_ENDPOINT,  # replace with the relevant cluster endpoints
    ) as c:
        await c.refresh_all_prices()
        products = await c.get_products()
        all_prices: List[PythPriceAccount] = []
        for p in products:
            print(p.key, p.attrs)
            prices = await p.get_prices()
            for _, pr in prices.items():
                all_prices.append(pr)
        print("Total number of price items available is", len(all_prices))

        ws = c.create_watch_session()
        await ws.connect()
        if use_program:
            print("Subscribing to program account")
            await ws.program_subscribe(v2_program_key, await c.get_all_accounts())
        else:
            focus = all_prices[0]
            print("Subscribing to the first price item", focus.key)
            await ws.subscribe(focus)
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
                            pr.product.symbol,
                            pr.price_type,
                            pr.aggregate_price_status,
                            pr.aggregate_price,
                            "p/m",
                            pr.aggregate_price_confidence_interval,
                        )
                        if USER is not None:
                            print("sending to user...")
                            await USER.send(
                                json.dumps(
                                    {
                                        "type": "price",
                                        "symbol": pr.product.symbol,
                                        "price_type": str(pr.price_type),
                                        "status": str(pr.aggregate_price_status),
                                        "price": pr.aggregate_price,
                                        "confidence": pr.aggregate_price_confidence_interval,
                                    }
                                ),
                            )
                    break

        print("Unsubscribing...")
        if use_program:
            await ws.program_unsubscribe(v2_program_key)
        else:
            for account in all_prices:
                await ws.unsubscribe(account)
        await ws.disconnect()
        print("Disconnected")


"""
This is just a demostration programs for visualization of the pricing data
provided by pyth network

Setting up of websocket server that pulls data from pyth development network
And broadcast it to the local websocket subscribers.

dependency requirements: pythclient, websockets
"""

logging.basicConfig()


async def new_connection(conn):
    global USER
    try:
        USER = conn
        await USER.send(json.dumps({"type": "message", "content": "welcome"}))
        await price_feed() # run forever
    except:
        logging.error("Error occurred during user subscription")
        print("Error occurred during user subscription")
    finally:
        # Unregister user
        pass


async def main(): async with websockets.serve(new_connection, "localhost", 6789):
        logging.info("Price data server started @ localhost: port 6789")
        print("Price data server started @ localhost: port 6789")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
