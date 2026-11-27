**Language / Ngôn ngữ:** [Tiếng Việt](README.md) · English

English counterpart of `tools/verify-egress/README.md`. The Vietnamese file is the original.

# verify-egress

The egress-check tool has not been packaged in the current round. It needs to be run on the target Windows machine after the firewall allowlist is applied.

- It must try both DNS and HTTP/HTTPS to the Internet.
- Only approved loopback/LAN is permitted.
- Do not relax the firewall or change the route on your own.
- The output must record the time, the profile, the policy revision, and the result of each probe.

The Local Mode gate is met only when there is a real probe log on the target machine, not only a unit test.
