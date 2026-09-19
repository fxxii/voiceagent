# IVRS Cloud Voice Platform

An IPv6-first voice infrastructure project for building an internet-facing IVR and conversational voice system with FreeSWITCH on Google Cloud and an application layer on Render.

The project separates real-time telephony from application intelligence:

```text
SIP carrier
    │ IPv6 SIP + RTP
    ▼
GCP Compute Engine
e2-micro / FreeSWITCH
    │ IPv6 WSS
    ▼
Cloudflare
IPv6 → IPv4 WebSocket boundary
    │
    ▼
Render Voice Gateway
STT · RAG · LLM · TTS
```

## Why this architecture

FreeSWITCH handles the timing-sensitive telephony layer:

- SIP signaling
- RTP media
- codec negotiation
- registrations and dial plans
- call control

The application layer remains independently deployable and can handle:

- speech-to-text
- retrieval-augmented generation
- LLM streaming
- text-to-speech
- barge-in and call state

This keeps SIP/RTP operations isolated from application changes and avoids placing arbitrary UDP telephony traffic on an HTTP-only application platform.

## Current deployment

| Component | Configuration |
| --- | --- |
| Cloud | Google Cloud Compute Engine |
| Project | `voice-agent-509021` |
| VM | `voice-freeswitch` |
| Machine type | `e2-micro` |
| Zone | `us-central1-a` |
| Operating system | Debian 13 (Trixie) |
| Boot disk | 30 GB `pd-standard` |
| Network | Custom VPC `voice-vpc` |
| Subnet | `voice-us-central1` (`10.10.0.0/24`) |
| Public IPv4 | None |
| Public IPv6 | Reserved regional `/96`; guest uses the first `/128` |
| FreeSWITCH | 1.11.3 vanilla package |
| Swap | 4 GiB, `vm.swappiness=10` |
| SSH | IAP tunnel, TCP/22 restricted to Google's IAP range |

The reserved IPv6 allocation is attached to the VM as `freeswitch-ipv6`. The current guest address is:

```text
2600:1900:4000:8f0::
```

## FreeSWITCH configuration

The deployment uses native IPv6 Sofia profiles:

```text
internal-ipv6  → SIP 5060
external-ipv6  → SIP 5080
```

Both profiles bind directly to the public IPv6 address. IPv4 NAT-oriented `ext-sip-ip` and `ext-rtp-ip` settings are not used for the public edge.

The default IPv4 profile files are retained as recoverable backups but disabled because this VM has no external IPv4. FreeSWITCH Event Socket is bound to loopback only:

```text
127.0.0.1:8021
```

## Security model

- SSH is accessed through Identity-Aware Proxy rather than public SSH exposure.
- The custom VPC is used instead of the default auto-mode network.
- SIP and RTP ingress remain closed until a test client or carrier IPv6 CIDR is known.
- Broad `::/0` SIP/RTP rules are intentionally avoided.
- Event Socket is not publicly reachable.
- SignalWire PATs, FreeSWITCH passwords, OAuth codes, and private keys stay outside the repository.
- Render connectivity is designed to pass through a Cloudflare proxied hostname for IPv6-to-IPv4 WebSocket compatibility.

## Verified status

Completed:

- GCP CLI installation and project configuration
- IAP SSH connectivity
- Debian system update
- 4 GiB persistent swap
- SignalWire repository authentication
- Vanilla FreeSWITCH installation
- FreeSWITCH systemd enablement
- IPv6 Sofia profile startup
- Default extension password replacement
- Loopback-only Event Socket binding
- Reboot recovery
- Static IPv6 reservation
- GCP-local SIP registration, authenticated `9196` call setup, 148 inbound RTP packets, and BYE cleanup

Pending external integration:

- Carrier IPv6 SIP and RTP compatibility confirmation
- IPv6 SIP/RTP firewall rules restricted to approved sources
- External IPv6 softphone registration for extension `1000`
- External two-way `9196` echo test
- FreeSWITCH-to-Cloudflare-to-Render WebSocket media streaming

## Connect to the VM

```bash
gcloud compute ssh \
  --zone "us-central1-a" \
  "voice-freeswitch" \
  --tunnel-through-iap \
  --project "voice-agent-509021"
```

Useful verification commands:

```bash
sudo systemctl status freeswitch --no-pager
sudo fs_cli -x "status"
sudo fs_cli -x "sofia status"
ip -6 addr show
ip -6 route show default
```

## Test Roadmap item 1

The dependency-free client validates the FreeSWITCH SIP/RTP path with a synthetic PCMU tone. Run it from an IPv6-capable host after allowing that host's IPv6 `/128` in the GCP SIP/RTP firewall rules:

```bash
read -rsp 'SIP password: ' SIP_PASSWORD; echo
export SIP_PASSWORD
python3 tools/sip_test_client.py \
  --server 2600:1900:4000:8f0:: \
  --user 1000 \
  --target 9196 \
  --duration 10 \
  --verbose
unset SIP_PASSWORD
```

The client exits successfully only after authenticated registration, a `9196` call, inbound RTP, and a clean BYE. The GCP-local validation passed; an external IPv6 softphone/carrier test remains pending.

## Documentation

The detailed deployment plan and local operating notes are intentionally kept outside the public repository. This README documents the public architecture and verified test surface.

## Limitations

- The public telephony edge currently depends on a SIP provider that supports both IPv6 signaling and IPv6 RTP.
- SIP/RTP ingress is not open yet; carrier or test-client IPv6 CIDRs are required before external call testing.
- The deployment is a single `e2-micro` VM without high availability or automatic failover.
- The VM's 1 GiB RAM and 4 GiB swap are intended for FreeSWITCH, not local STT, LLM, embedding, or TTS workloads.
- GCP Free Tier quotas apply; outbound media traffic is not unlimited.
- Render's public services are IPv4-oriented, so the planned application connection requires a Cloudflare IPv6-to-IPv4 WebSocket boundary.
- External SIP registration, the `9196` echo test, and FreeSWITCH-to-Cloudflare-to-Render media streaming remain to be validated.

## Roadmap

### 1. Validate the IPv6 telephony edge

- [x] Build the dependency-free IPv6 SIP test client and local protocol tests.
- [x] Run the client locally on the GCP VM: REGISTER `200`, authenticated INVITE `200`, RTP received, BYE `200`.
- [ ] Confirm that the SIP provider supports both IPv6 signaling and IPv6 RTP.
- [ ] Add SIP/RTP firewall rules restricted to the provider or test client IPv6 CIDRs.
- [ ] Run `tools/sip_test_client.py` from an external IPv6-capable test host to register extension `1000`, call `9196`, and verify echoed RTP.

### 2. Build the IPv6-to-IPv4 media boundary

- [ ] Create a Cloudflare proxied hostname for the Render WebSocket endpoint.
- [ ] Verify `FreeSWITCH IPv6 → Cloudflare WSS → Render IPv4` connectivity.
- [ ] Install/configure `mod_audio_stream` for 8-kHz, mono, signed 16-bit PCM.
- [ ] Add an HMAC-authenticated WebSocket handshake with timestamp and nonce replay protection.

### 3. Implement the free turn-based voice gateway

- [ ] Deploy one Render Free Web Service with a maximum of one concurrent call initially.
- [ ] Implement VAD and bounded utterance buffering rather than continuous audio-to-audio inference.
- [ ] Use Cloudflare Workers AI `@cf/openai/whisper` for STT.
- [ ] Use Cloudflare Workers AI `@cf/meta/llama-3.2-1b-instruct` for the text LLM.
- [ ] Use Cloudflare Workers AI `@cf/myshell-ai/melotts` for TTS.
- [ ] Stream sentence-level TTS output back as 8-kHz PCM and implement barge-in cancellation.

### 4. Add retrieval and call-state reliability

- [ ] Create and verify the Upstash Vector index with BGE-M3; enable hybrid/BM25 only after confirming free-tier support.
- [ ] Store only short-lived call state, summaries, locks, generations, and rate limits in Upstash Redis.
- [ ] Reconnect calls after gateway restarts when possible; otherwise route to the local fallback IVR.
- [ ] Enforce the shared Workers AI daily quota and add provider-error fallback prompts.

### 5. End-to-end validation

- [ ] Test an inbound call from SIP signaling through STT, RAG, text LLM, TTS, and FreeSWITCH playback.
- [ ] Measure first-response latency, turn latency, barge-in latency, CPU/memory, Render bandwidth, and AI quota usage.
- [ ] Verify Render restart, WebSocket reconnect, expired HMAC nonce, provider timeout, and quota-exhaustion behavior.
- [ ] Document the final test limits and known failure modes.

The application infrastructure is intended to remain free within provider quotas. DID fees, SIP trunk charges, PSTN minutes, and possible network egress charges are outside the `$0` guarantee; a truly free test uses a SIP softphone or internal FreeSWITCH extension.

## License

License information will be added when the project distribution model is finalized.
