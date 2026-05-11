#!/usr/bin/env python3
"""
Minipupper Wake Signal - App → Gateway

Sends a wake signal to the Gateway by triggering the minipupper-task-runner cron
job via WebSocket JSON-RPC (cron.run).

Called automatically by minipupper_operator.py after writing a pending task.
Can also be run manually: python scripts/send_wake.py
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from src.openclaw.client import OpenClawClient, load_device_identity


def load_config():
    config_path = APP_ROOT / 'config' / 'config.yaml'
    if config_path.exists():
        import yaml
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def get_gateway_url():
    try:
        from dotenv import load_dotenv
        dotenv_path = APP_ROOT / 'config' / '.env'
        if dotenv_path.exists():
            load_dotenv(dotenv_path=str(dotenv_path))
    except ImportError:
        pass
    url = os.environ.get('OPENCLAW_GATEWAY_URL')
    if not url:
        config = load_config()
        url = config.get('network', {}).get('gateway_url')
    return url


def get_cron_job_id():
    config = load_config()
    return config.get('network', {}).get('cron_job_id', '')


def send_wake(cron_id=None):
    """Connect to Gateway and trigger cron.run."""
    if cron_id is None:
        cron_id = get_cron_job_id()
    if not cron_id:
        logger.error("No cron_job_id configured")
        return False

    gateway_url = get_gateway_url()
    if not gateway_url:
        logger.error("Gateway URL not configured")
        return False

    device_identity = load_device_identity()
    if not device_identity:
        logger.error("No device identity found")
        return False

    logger.info("Triggering cron %s...", cron_id)

    try:
        client = OpenClawClient(gateway_url, device_identity=device_identity)

        def noop(frame):
            pass

        client.start(noop)

        for _ in range(50):
            if client.ws and client.ws.connected:
                break
            time.sleep(0.1)

        if not client.ws or not client.ws.connected:
            logger.error("Failed to connect to Gateway")
            client.stop()
            return False

        time.sleep(1.0)
        client.trigger_cron(cron_id)
        logger.info("✓ Cron triggered: %s", cron_id)

        time.sleep(0.5)
        client.stop()
        return True

    except Exception as e:
        logger.error("Wake failed: %s", e)
        return False


def main():
    cron_id = get_cron_job_id()
    if not cron_id:
        logger.error("No cron_job_id in config/network section")
        logger.error("Add: network.cron_job_id: <your-cron-id>")
        sys.exit(1)

    success = send_wake(cron_id)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
