---
id: PB-T5-02
version: "1.1.0"
title: LLM red team
owner_role: security_officer
status: active
---
# LLM red team

- Run the platform's fixed, versioned red-team suite against the candidate in test; never write
  attacks of your own against other systems.
- Categories: prompt injection, jailbreak, personal-data extraction and abusive input. Each attack
  is sent inside an otherwise normal incident; its check decides success.
- Report attempts, successes and the rate per category exactly as the suite returns them, with the
  suite version. Injection and jailbreak rates are compared with the tier maximums by controls.
- Any successful personal-data extraction is a privacy finding and a residual risk.
