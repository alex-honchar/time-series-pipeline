from collections import deque

state = {
    "system": {
        "reader": None,
        "active": False,
        "tick_connected": False,
        "tick": 0,
        "start_time": None,
    },
    "metrics": {
        "broken_ticks": 0,
        "disconnected_ticks": 0,
    },
    "market": {
        "trades": deque(maxlen=100000),
        "last_price": None,
    },
}
