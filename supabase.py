
class mock_table:
    def insert(self, *args): return self
    def execute(self): pass
class Client:
    def table(self, name): return mock_table()
def create_client(url, key): return Client()
