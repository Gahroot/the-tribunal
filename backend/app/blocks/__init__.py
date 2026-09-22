"""Host-side wiring for extracted, mountable blocks (e.g. tribunal-widget).

Each module here adapts the host app's services to a block's injection ports so
the block stays free of sideways imports into sibling blocks. Importing a wiring
module registers its providers as a side effect.
"""
