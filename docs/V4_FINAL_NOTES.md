# IRAS v4.0.0 FINAL

IRAS v4.0.0 is the production promotion of the RC2 line after automated regression, hosted Render, and real Windows acceptance. The remote protocol remains version `1`; this promotion does not introduce a wire-protocol break.

## Production acceptance completed

- Full regression and v4 validation suite passes.
- Hosted Render `/health` advertises `service_id=iras-cloud`, version `4.0.0`, and `remote_protocol=1` after deployment.
- Windows pairing verifies the master API token before persisting configuration.
- Device and API credentials are protected with Windows DPAPI.
- `iras --doctor` validates the remote transport, pairing, protocol, startup task, emergency stop, microphone, voice stack, OmniParser, provider configuration, and disk health.
- Real cloud-to-Windows status retrieval, app launch, and text entry were exercised on the target Windows machine.
- Descriptive screenshot requests route through multimodal computer observation instead of returning only local screenshot metadata.
- The scheduled Windows bridge launches hidden while remaining in the interactive user session required for UI/screen automation.
- Emergency-stop delivery is hardened: stopped or locally disarmed devices reject work explicitly, and commands that time out before being claimed are expired so they cannot execute later.
- Clearing an emergency stop does not silently re-arm remote access; re-arm remains a separate local action.

## Security model retained

- The Windows bridge is outbound-only; no inbound laptop port is opened.
- A cloud remote session and the local Windows policy are both required.
- The local emergency-stop gate is enforced below model planning.
- `full` mode does not silently enable shell or power operations; those remain separate opt-ins.
- Live UI state and semantic end-state verification remain authoritative.

## Upgrade from RC2

Deploy the final code to the same Render service and update the local Windows checkout. Existing compatible protocol-1 bridge configuration can be reused. Re-run `iras --doctor` after deployment and confirm `/health` reports version `4.0.0`.
