class RuntimeMemory:
    def __init__(self):
        self.state = {"symbols": []}  # list of {file, classes[], functions[]}
    def put_symbols(self, entries):
        self.state["symbols"] = entries
    def get_symbols(self):
        return self.state.get("symbols", [])
MEMORY = RuntimeMemory()
