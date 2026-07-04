# Ansible Security Hardening Project

**Created:** June 2026 (Athens)  
**Status:** Planned — implement after dev-rag Phase 1 is running  
**Repository:** Extend existing `ansible-personal` project  

---

## Purpose

Write an Ansible playbook that hardens Edward's Pop!_OS laptop and keeps
it secure and up to date. The playbook should be idempotent — safe to run
repeatedly — so it can be applied on a schedule or after any major system
change to verify the security baseline hasn't drifted.

This is both a practical security tool and a real-world Ansible example
for the Python AI agent book.

---

## Why Ansible for This

- **Repeatable** — run it monthly or after any major change
- **Self-documenting** — the playbook IS the security policy
- **Already in the stack** — extends existing laptop management work
- **Book-worthy** — a concrete real-world example beyond toy demos

---

## Planned Playbook Structure

```
ansible-personal/
├── playbooks/
│   ├── laptop-setup.yml         # existing
│   ├── laptop-security.yml      # NEW — this project
│   ├── docker-deploy.yml        # existing
│   └── vps-provision.yml        # existing
├── roles/
│   ├── firewall/                # UFW rules (with Docker conflict fix)
│   ├── ssh-hardening/           # SSH configuration
│   ├── auto-updates/            # Unattended security updates
│   ├── docker-hardening/        # Docker daemon security settings
│   └── dev-environment/         # Dev tool security (npm, pip, etc.)
└── inventory/
    └── localhost.yml
```

---

## Security Areas to Cover

### System Hardening
- UFW firewall rules — careful handling of Docker/UFW conflict
  (already solved in existing Ansible work — reuse that logic)
- Automatic security updates (`unattended-upgrades`)
- Disable unnecessary services and open ports
- File permission auditing on sensitive directories
- Lynis security audit integration (optional — run and save report)

### SSH Hardening
- Disable password authentication (key-only)
- Disable root login
- Set `MaxAuthTries`, `LoginGraceTime`
- Restrict which users can SSH in
- Change default port if remote access is used

### Docker Security
- Docker daemon configuration (`/etc/docker/daemon.json`)
  - `"no-new-privileges": true`
  - `"userns-remap": "default"` (user namespace remapping)
  - Disable experimental features if not needed
- Docker socket permissions — restrict who can access `/var/run/docker.sock`
- Ensure Docker content trust is enabled
- Audit Docker images for known vulnerabilities (Trivy integration)

### Development Environment
- Claude Code npm vulnerability awareness
  - Periodic `npm audit` on global packages
  - Pin Claude Code version, don't auto-update blindly
- Python environment security
  - `uv` for all package management (already established)
  - Audit installed packages periodically
- `.env` file protection
  - Verify `.gitignore` coverage
  - Scan for accidentally committed secrets (git-secrets or trufflehog)
- API key hygiene
  - Rotation reminders
  - Verify keys are not in shell history

### Network Security
- DNS-over-HTTPS or DNS-over-TLS configuration
- Review open ports periodically (`ss -tulnp`)
- Block unused inbound ports

---

## Connection to dev-rag

Ansible security books ingested into the DevOps corpus mean you can ask
dev-rag questions like:

- "What Ansible modules are used for UFW management?"
- "How do you harden SSH with Ansible?"
- "What does userns-remap do in Docker?"

The playbook and the corpus reinforce each other.

---

## Connection to the Book

This project provides a complete, real-world Ansible chapter:

- "Here is how I keep my own development machine secure"
- Shows idempotent playbook design
- Shows role-based organisation
- Shows the Docker/UFW conflict and its resolution
- Shows integration with security tools (Lynis, Trivy)

A concrete personal project is always more compelling than a toy example.

---

## Suggested Books for the Ansible Corpus

*(To be confirmed against what Edward owns)*

- Ansible for DevOps (Geerling) — the standard reference
- Ansible: Up and Running — practical patterns
- Linux Security Cookbook — hardening techniques
- The Linux Command Line — foundational reference

---

## Implementation Notes

- Write the playbook in Claude Code using the existing Ansible project
- Test each role against a VM or a non-critical machine first
- Make every task idempotent — `changed` only when something actually changed
- Add a `--check` dry-run step to the README
- Tag tasks so individual areas can be run selectively:
  `ansible-playbook laptop-security.yml --tags docker`

---

*Project brief written Athens, June 2026. Add to to-do list and implement
after dev-rag Phase 1 is running.*
