"""Answer models of the platform API (feature 022, research R-04).

One module per router. Every model derives from :class:`base.ApiModel`, which refuses keys it
does not declare, so a service that starts returning a new key fails loudly in the tests instead
of the key being dropped from the answer. Field names are exactly the keys the services return.
"""
