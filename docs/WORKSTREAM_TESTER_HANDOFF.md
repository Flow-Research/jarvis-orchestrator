# Workstream Tester Handoff

This runbook provisions external testers for the Jarvis workstream API.

## Generated Credential Pack

Generate a server-side operator secret map plus a tester handoff file:

```bash
python3 scripts/generate_workstream_operator_credentials.py \
  --count 20 \
  --prefix company_tester \
  --base-url https://YOUR-NGROK-URL
```

The generator always writes to the same stable paths by default. Running it again overwrites those files in place.

Outputs:

- `data/workstream/tester-pack/operators.server-operator-secrets.json`
- `data/workstream/tester-pack/operators.tester-handoff.json`
- `data/workstream/tester-pack/operators.operators/company_tester_01.json`
- `data/workstream/tester-pack/operators.operators/company_tester_02.json`
- ...

Use the server-side file with:

```bash
export JARVIS_WORKSTREAM_OPERATOR_SECRETS_FILE=data/workstream/tester-pack/operators.server-operator-secrets.json
```

The tester handoff file contains the exact values to distribute:

- `base_url`
- `operator_id`
- `operator_secret`

Distribution rule:

- do not give testers the server secret map
- give each tester only that tester's single JSON file from `operators.operators/`
- the combined `operators.tester-handoff.json` is for internal admin use

## Local HTTPS Exposure

When external testers need HTTPS, expose the local workstream API with ngrok:

```bash
ngrok http 8787
```

Use the generated ngrok HTTPS URL as `--base-url` when creating the tester handoff pack.
After regeneration, restart `workstream-api` so the running process reloads the updated secrets from disk.

## Start the Stack

```bash
docker compose -f docker-compose.local.yaml up -d workstream-api registration-monitor sn13-scheduler
```

The human dashboard remains at:

- `/`

The signed operator API remains at:

- `/v1/tasks`
- `/v1/tasks/{task_id}`
- `/v1/submissions`
- `/v1/operators/{operator_id}/stats`

## What Testers Receive

Each tester only needs:

- the published workstream skill at `docs/skills/jarvis-workstream/SKILL.md`
- one `base_url`
- one `operator_id`
- one `operator_secret`

They do not need Jarvis admin CLI access, wallet access, or server-side environment files.
