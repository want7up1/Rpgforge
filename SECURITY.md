# Security Policy

## Supported Versions

RPGForge is currently in early public preview. Security fixes target the latest `main` branch.

## Reporting a Vulnerability

Please report security issues privately instead of opening a public issue. If GitHub private vulnerability reporting is enabled for the repository, use that channel. Otherwise contact the repository owner directly.

Include:

- A short description of the issue.
- Steps to reproduce.
- Impact and affected versions or commits.
- Any suggested mitigation.

## Self-Hosting Notes

- Set `SETTINGS_ADMIN_TOKEN` before exposing the settings page.
- Do not commit `.env`.
- Do not publish Docker volumes or database dumps.
- Treat generated games, character portraits, and saved API settings as private user data.
- Put the service behind HTTPS and authentication if it is exposed outside a trusted network.
