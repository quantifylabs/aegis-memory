"""True negatives: plain in-process containers. None is bound to a memory constructor, so none is a
sink — even when the method name (``add``/``update``) or a receiver name (``store``) collides with a
real sink. Confirms that *binding*, not the receiver's name, drives Batch-B detection."""


def run(x):
    results = []
    results.append(x)            # append is never a sink (the canonical false-positive shape)
    seen = set()
    seen.add(x)                  # set.add on an unbound receiver -> not a sink
    store = {}
    store.update(x)              # dict named "store"; `update` is bound-only -> not a sink
    cfg = {}
    cfg.update({"k": x})         # plain dict update -> not a sink
    notes = []
    notes.append("literal")      # constant/literal write -> not a sink
    return results, seen, store, cfg, notes
