"""TP: ``app = App()`` (embedchain import present) -> ``app.add`` is an embedchain sink via binding.
``App`` carries no memory token, so it binds ONLY because the embedchain import gate passes."""

from embedchain import App


def ingest(url):
    app = App()
    app.add(url)
