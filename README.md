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

## Render voice gateway scaffold

The repository now contains a deployable Python 3.12 gateway scaffold for the Render `voiceagent` project:

```text
FastAPI + Uvicorn
    ├── GET  /health
    ├── GET  /ready
    ├── WS   /v1/audio/{call_id}
    ├── POST /v1/admin/reindex
    └── POST /v1/admin/documents
```

The WebSocket currently echoes binary frames and acknowledges text frames. This validates the transport path and is not yet production audio, RTP, STT, LLM, TTS, or RAG processing. Document and reindex state is process-local and intentionally non-persistent.

Run locally:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
PORT=8000 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Render uses:

```text
Build: pip install -r requirements.txt
Start: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The service is designed as a lightweight orchestration gateway for the Render Free instance. Local STT, LLM, embeddings, TTS, and Qdrant remain outside its resource budget and are planned as external integrations.

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
- Render connectivity passes through the Cloudflare-proxied `voice.fxxii.com` hostname for IPv6-to-IPv4 WebSocket compatibility.

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

The detailed deployment plan and local operating notes are maintained separately from this README. This README documents the public architecture and verified test surface.

- [Project roadmap](docs/plan/roadmap.md)
- [Installation guide](docs/INSTALLATION.md)
- [Free IVRS architecture notes](doc/plan/free%20ivrs%20solutions.md)
- [Repository operating instructions](AGENTS.md)

## Limitations

- The public telephony edge currently depends on a SIP provider that supports both IPv6 signaling and IPv6 RTP.
- SIP/RTP ingress is not open yet; carrier or test-client IPv6 CIDRs are required before external call testing.
- The deployment is a single `e2-micro` VM without high availability or automatic failover.
- The VM's 1 GiB RAM and 4 GiB swap are intended for FreeSWITCH, not local STT, LLM, embedding, or TTS workloads.
- GCP Free Tier quotas apply; outbound media traffic is not unlimited.
- Render's public services are IPv4-oriented; Cloudflare now provides the IPv6-to-IPv4 media boundary for `voice.fxxii.com`.
- The TLS-enabled `mod_audio_stream` module, IPv6 patch, 8-kHz mono L16 contract, and HMAC handshake are implemented. Live HMAC enforcement still requires deploying the pending gateway code to Render.

## License

License information will be added when the project distribution model is finalized.
