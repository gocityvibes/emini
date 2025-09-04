import time

def decide(signal):
    # Rate limiting + fallback demo
    time.sleep(0.1)
    return {"decision": "hold", "signal": signal}
