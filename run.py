from state import state
from ingest.stream_reader import init_reader, ingest_tick

def run(state):
    init_reader(state)
    while state["system"]["active"] is True:
        ingest_tick(state)

if __name__ == "__main__":
     run(state)