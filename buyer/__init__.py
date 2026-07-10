# BUYER — the consumer side of SNHP: the buyer's agent as a first-class player.
# See buyer/DESIGN.md (binding architecture) and buyer/RESULTS.md (findings).
#
# Coupling rule: the BuyerAgent depends ONLY on the Merchant protocol in
# buyer/merchant.py. vend is imported read-only behind the VendMerchant
# adapter; a ToyMerchant stands in when vend is mid-refactor.
