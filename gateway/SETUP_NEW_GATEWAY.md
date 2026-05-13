# Setting Up a New Gateway for Minipupper

## Prerequisites

- OpenClaw gateway with `openclaw` CLI installed
- Node connection to the Mini Pupper Pi

## Copy Gateway Files

The gateway package files (`protocol.py`, `task_handler.py`, `__init__.py`)
need to be in your gateway's workspace at `~/.openclaw/workspace/minipupper/`.

**Method 1 — From the Pi (node exec):**
```bash
mkdir -p ~/.openclaw/workspace/minipupper
for f in protocol.py task_handler.py __init__.py; do
  openclaw exec --node YOUR_NODE "cat ~/minipupper-app/gateway/\$f" --host node \
    > ~/.openclaw/workspace/minipupper/\$f
done
```

**Method 2 — Git clone:**
```bash
git clone <repo-url> /tmp/minipupper-gateway
cp /tmp/minipupper-gateway/gateway/*.py ~/.openclaw/workspace/minipupper/
```

**Method 3 — SCP (SSH access):**
```bash
scp ubuntu@PI-IP:minipupper-app/gateway/*.py ~/.openclaw/workspace/minipupper/
```

## Create Cron Job

The cron config is in `gateway/cron_config.json`. It has a placeholder
`YOUR_NODE_NAME` that you need to replace with your actual node name.

```bash
# Copy cron config and substitute your node name
cat ~/minipupper-app/gateway/cron_config.json \
  | sed 's/YOUR_NODE_NAME/YOUR_ACTUAL_NODE/g' \
  > /tmp/cron_ready.json

# Create the cron job
openclaw cron add --json "$(cat /tmp/cron_ready.json)"

# Note the returned job ID — the app needs it in config.yaml
```

After creation, update `~/minipupper-app/config/config.yaml`:
```yaml
network:
  cron_job_id: "THE_RETURNED_JOB_ID"
```
## Verify

```bash
python3 -c "from minipupper.task_handler import router; print(f'{len(router.list_actions())} actions')"
# Expected: 22 actions
```

## Start the App

On the Pi:
```bash
cd ~/minipupper-app && bash scripts/start_with_aec.sh
```
