"""TPs: custom memory handles bound by their *constructor class name* (no library import needed).
Covers the corpus idioms the name-hint tiers miss: ``manager.store``, tiered ``self.warm.put`` /
``self.hot.put``, ``router.write``, ``self.backend.save``, and the bound-only ``store.update``."""


class MemoryManager:
    def store(self, item): ...


class WarmTier:
    def put(self, value): ...


class HotTier:
    def put(self, value): ...


class MemoryRouter:
    def write(self, value): ...


class StorageBackend:
    def save(self, value): ...


class MemoryStore:
    def update(self, value): ...


def manager_store(item):
    manager = MemoryManager()
    manager.store(item)


class Tiered:
    def __init__(self):
        self.warm = WarmTier()
        self.hot = HotTier()

    def remember(self, value):
        self.warm.put(value)
        self.hot.put(value)


class Pipeline:
    def __init__(self):
        self.backend = StorageBackend()

    def persist(self, value):
        router = MemoryRouter()
        router.write(value)
        self.backend.save(value)


def store_update(value):
    store = MemoryStore()
    store.update(value)
