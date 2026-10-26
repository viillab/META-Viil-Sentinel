# Security & privacy policy — local hackathon prototype

This project is a **non-clinical demo**. Do not connect it to real monitoring, real patients or emergency dispatch.

## Data handling
- Only staged or explicitly licensed visual material.
- Never publish recordings or sensitive identifiers without consent.
- Free-credit Meta API may use submitted content for product improvement; use synthetic/staged inputs until terms and rights are reviewed.
- Never commit .env, API keys, secrets, model checkpoints, copyrighted research files or user data.
- Avoid exposing frame images or personal details in audit logs.

## Application boundaries
- Backend currently uses in-memory state and no authentication; bind only to loopback 127.0.0.1.
- DEMO_MODE=true is required for simulated event creation and unauthenticated actions.
- No production monitoring, emergency alerts, treatment guidance, medical severity estimation or patient health advice.
- Introduce authenticated users, access controls, retention policies, TLS and secrets management before external deployment.

## Before opening the GitHub repo Public
Review the full Git history for accidental secrets, personal data, proprietary source, non-distributable assets and license conflicts. Removing only the latest file is not enough to erase historical secrets.
