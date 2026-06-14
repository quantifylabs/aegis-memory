"""A multi-channel anti-demo-tuning fixture (acceptance §3.5).

Deliberately unlike the firewall demo: class-based, different variable names, and a *vector
store* (not a LangGraph store) for the web-fetch sink. Four untrusted channels — request body,
web crawl, tool API, and email — each write into a different sink family with **no** screening.
The general sink catalog + same-scope taint check must still flag every untrusted flow, proving
no rule keys off the demo's filenames or strings.
"""


class Absorber:
    def __init__(self, fact_store, kb_index, scratchpad, session_saver) -> None:
        self.fact_store = fact_store
        self.kb_index = kb_index
        self.scratchpad = scratchpad
        self.session_saver = session_saver

    def from_request(self, req) -> None:
        # request body -> LangGraph store write
        blob = req["payload"]
        self.fact_store.put(("g", "notes"), "k1", {"text": blob})

    def from_crawler(self, crawler, link) -> None:
        # web fetch -> vector store write (different framework idiom for the web channel)
        grabbed = crawler.fetch(link).text
        self.kb_index.add([{"text": grabbed}])

    def from_api(self, connector, account) -> None:
        # tool/API egress -> custom memory write
        observation = connector.invoke(account)
        self.scratchpad.remember(observation)

    def from_mail(self, cfg, mail) -> None:
        # email body -> checkpointer write
        self.session_saver.put(cfg, "slot", {"body": mail.body})
