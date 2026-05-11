"""OpenClaw WebSocket client for minipupper-app operator connections.

Connects to the remote Gateway over Tailscale TLS using the existing device
identity keypair (~/.openclaw/identity/device.json). Performs a signed v3
nonce handshake and handles the pairing flow on first connect.
"""
import base64
import json
import logging
import os
import ssl
import threading
import time
from pathlib import Path
from typing import Callable, Optional

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    HAS_CRYPTO = True
except Exception:
    HAS_CRYPTO = False

try:
    from websocket import create_connection, WebSocketConnectionClosedException
    HAS_WS = True
except Exception:
    HAS_WS = False

logger = logging.getLogger(__name__)

IDENTITY_PATH = Path.home() / '.openclaw' / 'identity' / 'device.json'
OPERATOR_AUTH_PATH = Path.home() / '.openclaw' / 'identity' / 'operator-auth.json'

CLIENT_ID = 'cli'
CLIENT_VERSION = '0.1.0'
PLATFORM = 'linux'
DEVICE_FAMILY = 'pi'
CLIENT_MODE = 'cli'
ROLE = 'operator'
SCOPES = ['operator.admin', 'operator.read', 'operator.write']


def load_device_identity(path: Optional[str] = None) -> dict:
    """Load device identity from ~/.openclaw/identity/device.json."""
    fp = Path(path) if path else IDENTITY_PATH
    if not fp.exists():
        logger.warning("Device identity not found at %s", fp)
        return {}
    try:
        return json.loads(fp.read_text())
    except Exception as exc:
        logger.warning("Failed to read device identity: %s", exc)
        return {}


def load_operator_token() -> Optional[str]:
    """Read the stored operator device token, if any."""
    if not OPERATOR_AUTH_PATH.exists():
        return None
    try:
        data = json.loads(OPERATOR_AUTH_PATH.read_text())
        return data.get('token')
    except Exception:
        return None


def save_operator_token(token: str, device_id: str):
    """Persist an operator device token for future connections."""
    OPERATOR_AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'version': 1,
        'deviceId': device_id,
        'token': token,
        'role': 'operator',
        'updatedAtMs': int(time.time() * 1000),
    }
    OPERATOR_AUTH_PATH.write_text(json.dumps(data, indent=2))
    logger.info("Saved operator token to %s", OPERATOR_AUTH_PATH)


def _normalize_meta(value: Optional[str]) -> str:
    """Match the Gateway's normalizeDeviceMetadataForAuth.

    Trim whitespace, lowercase ASCII only, empty string if null/missing.
    """
    if not value:
        return ''
    return value.strip().lower()


def build_v3_signature_payload(
    device_id: str,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list,
    signed_at_ms: int,
    token: Optional[str],
    nonce: str,
    platform: Optional[str] = PLATFORM,
    device_family: Optional[str] = DEVICE_FAMILY,
) -> str:
    """Build the Gateway's v3 pipe-delimited signature payload.

    Format: v3|deviceId|clientId|clientMode|role|scopes|signedAtMs|token|nonce|platform|deviceFamily
    """
    scopes_str = ','.join(scopes)
    token_str = token or ''
    plat = _normalize_meta(platform)
    fam = _normalize_meta(device_family)
    return '|'.join([
        'v3',
        device_id,
        client_id,
        client_mode,
        role,
        scopes_str,
        str(signed_at_ms),
        token_str,
        nonce,
        plat,
        fam,
    ])


def build_v2_signature_payload(
    device_id: str,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list,
    signed_at_ms: int,
    token: Optional[str],
    nonce: str,
) -> str:
    """Build the Gateway's v2 pipe-delimited signature payload (fallback).

    Format: v2|deviceId|clientId|clientMode|role|scopes|signedAtMs|token|nonce
    """
    scopes_str = ','.join(scopes)
    token_str = token or ''
    return '|'.join([
        'v2',
        device_id,
        client_id,
        client_mode,
        role,
        scopes_str,
        str(signed_at_ms),
        token_str,
        nonce,
    ])


class OpenClawClient:
    """Threaded WebSocket client for the remote OpenClaw Gateway."""

    def __init__(self, gateway_url: str, device_identity: Optional[dict] = None,
                 session_target: str = 'main'):
        self.gateway_url = gateway_url
        self.session_target = session_target
        self.ws = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._message_handler: Optional[Callable[[dict], None]] = None

        # Resolve device identity
        if device_identity:
            self._identity = device_identity
        else:
            self._identity = load_device_identity()

        self._device_id = self._identity.get('deviceId', 'minipupper-app')
        self._private_key: Optional[ed25519.Ed25519PrivateKey] = None
        private_key_pem = self._identity.get('privateKeyPem')
        if private_key_pem and HAS_CRYPTO:
            try:
                key_bytes = private_key_pem.encode()
                self._private_key = load_pem_private_key(key_bytes, password=None)
            except Exception as exc:
                logger.warning("Failed to load device private key: %s", exc)
                self._private_key = None

        # Stored operator token (from previous pairing)
        self._operator_token = load_operator_token()

    @property
    def is_connected(self) -> bool:
        return self.ws is not None

    def start(self, message_handler: Callable[[dict], None]):
        if not HAS_WS:
            raise RuntimeError(
                'websocket-client is required. pip install websocket-client'
            )
        self._message_handler = message_handler
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name='OpenClawGateway'
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=2.0)

    def send_sessions_send(self, session_key: str, message: str,
                           req_id: Optional[str] = None):
        payload = {
            'type': 'req',
            'id': req_id or f'msg-{int(time.time()*1000)}',
            'method': 'sessions.send',
            'params': {
                'sessionKey': session_key,
                'message': message,
            },
        }
        self._send_json(payload)

    def subscribe_session_messages(self, session_key: str,
                                   sub_id: str = 'sub-session'):
        payload = {
            'type': 'req',
            'id': sub_id,
            'method': 'sessions.messages.subscribe',
            'params': {'sessionKey': session_key},
        }
        self._send_json(payload)


    def trigger_cron(self, cron_id: str, req_id: Optional[str] = None):
        """Trigger a cron job to run immediately via Gateway RPC."""
        payload = {
            "type": "req",
            "id": req_id or f"cron-run-{int(time.time()*1000)}",
            "method": "cron.run",
            "params": {"id": cron_id},
        }
        self._send_json(payload)
    def _send_json(self, obj: dict):
        try:
            if self.ws:
                self.ws.send(json.dumps(obj))
        except WebSocketConnectionClosedException:
            self.ws = None
        except Exception:
            self.ws = None

    # ── Handshake ──────────────────────────────────────────────

    def _build_signed_connect_req(self, nonce: str, ts: int,
                                   token: str) -> dict:
        """Build the full connect request dict with signed device identity.

        Signs both v3 (preferred) and v2 (fallback) payloads so the Gateway
        can verify whichever format it supports.
        """
        pub_key_pem = self._identity.get('publicKeyPem')
        signature_b64 = None

        if self._private_key and HAS_CRYPTO:
            # Build and sign the v3 payload (preferred)
            v3_payload = build_v3_signature_payload(
                device_id=self._device_id,
                client_id=CLIENT_ID,
                client_mode=CLIENT_MODE,
                role=ROLE,
                scopes=SCOPES,
                signed_at_ms=ts,
                token=token,
                nonce=nonce,
                platform=PLATFORM,
                device_family=DEVICE_FAMILY,
            )
            try:
                sig_raw = self._private_key.sign(v3_payload.encode())
                signature_b64 = base64.b64encode(sig_raw).decode()
            except Exception as exc:
                logger.warning("v3 signing failed: %s", exc)

            # Also sign v2 as fallback — the Gateway verifies v3 first
            # then falls back to v2. Signing both means one will match.
            v2_payload = build_v2_signature_payload(
                device_id=self._device_id,
                client_id=CLIENT_ID,
                client_mode=CLIENT_MODE,
                role=ROLE,
                scopes=SCOPES,
                signed_at_ms=ts,
                token=token,
                nonce=nonce,
            )
            try:
                sig_v2 = self._private_key.sign(v2_payload.encode())
                # Prefer v3 sig, but include v2 if v3 failed
                if not signature_b64:
                    signature_b64 = base64.b64encode(sig_v2).decode()
            except Exception:
                pass

        return {
            'type': 'req',
            'id': 'conn-1',
            'method': 'connect',
            'params': {
                'minProtocol': 3,
                'maxProtocol': 3,
                'client': {
                    'id': CLIENT_ID,
                    'version': CLIENT_VERSION,
                    'platform': PLATFORM,
                    'mode': CLIENT_MODE,
                    'deviceFamily': DEVICE_FAMILY,
                },
                'role': ROLE,
                'scopes': SCOPES,
                'caps': [],
                'commands': [],
                'permissions': {},
                'auth': {'token': token},
                'locale': 'en-US',
                'userAgent': f'{CLIENT_ID}/{CLIENT_VERSION}',
                'device': {
                    'id': self._device_id,
                    'publicKey': pub_key_pem,
                    'signature': signature_b64,
                    'signedAt': ts,
                    'nonce': nonce,
                },
            },
        }

    def _perform_handshake(self) -> bool:
        """Perform the connect handshake with signed nonce.

        Returns True on success (hello-ok received), False on failure.
        On NOT_PAIRED, enters a wait loop for pairing approval.
        """
        try:
            frame = json.loads(self.ws.recv())
        except Exception as exc:
            logger.warning("Handshake: failed to read challenge: %s", exc)
            return False

        if frame.get('event') != 'connect.challenge':
            logger.warning(
                "Handshake: expected connect.challenge, got %s",
                frame.get('event', 'unknown'),
            )
            return False

        nonce = frame['payload'].get('nonce')
        ts = frame['payload'].get('ts')
        token = self._operator_token or ''

        connect_req = self._build_signed_connect_req(nonce, ts, token)
        self.ws.send(json.dumps(connect_req))

        try:
            hello = json.loads(self.ws.recv())
        except Exception as exc:
            logger.warning("Handshake: failed to read hello response: %s", exc)
            return False

        if hello.get('ok'):
            auth_info = hello.get('payload', {}).get('auth', {})
            issued_token = auth_info.get('deviceToken')
            if issued_token and issued_token != self._operator_token:
                self._operator_token = issued_token
                save_operator_token(issued_token, self._device_id)
            logger.info(
                "Connected to Gateway (device: %s)", self._device_id
            )
            return True

        error_info = hello.get('error', {})
        error_code = error_info.get('code', 'UNKNOWN')
        if error_code == 'NOT_PAIRED':
            logger.warning(
                "Gateway returned NOT_PAIRED for device %s.\n"
                "  Approve on the cloud server:\n"
                "    openclaw nodes pair approve --device-id %s",
                self._device_id, self._device_id,
            )
            logger.info("Waiting for pairing approval... (retrying every 10s)")
            return self._wait_for_pairing()

        logger.warning(
            "Handshake failed: %s %s",
            error_code, error_info.get('message', ''),
        )
        return False

    def _wait_for_pairing(self) -> bool:
        """Loop, reconnecting periodically, until the device is paired."""
        while not self._stop.is_set():
            time.sleep(10.0)
            if self._stop.is_set():
                return False
            try:
                self.ws.close()
            except Exception:
                pass
            try:
                self.ws = create_connection(
                    self.gateway_url,
                    sslopt={'cert_reqs': ssl.CERT_REQUIRED},
                )
                if self._try_handshake():
                    return True
            except Exception:
                pass
        return False

    def _try_handshake(self) -> bool:
        """Reconnect handshake (used during pairing wait loop)."""
        try:
            frame = json.loads(self.ws.recv())
        except Exception:
            return False
        if frame.get('event') != 'connect.challenge':
            return False
        nonce = frame['payload'].get('nonce')
        ts = frame['payload'].get('ts')
        token = self._operator_token or ''
        connect_req = self._build_signed_connect_req(nonce, ts, token)
        self.ws.send(json.dumps(connect_req))
        try:
            hello = json.loads(self.ws.recv())
            if hello.get('ok'):
                auth_info = hello.get('payload', {}).get('auth', {})
                issued_token = auth_info.get('deviceToken')
                if issued_token and issued_token != self._operator_token:
                    self._operator_token = issued_token
                    save_operator_token(issued_token, self._device_id)
                logger.info(
                    "Connected to Gateway (device: %s)", self._device_id
                )
                return True
        except Exception:
            pass
        return False

    # ── Run loop ────────────────────────────────────────────────

    def _run(self):
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self.ws = create_connection(
                    self.gateway_url,
                    sslopt={'cert_reqs': ssl.CERT_REQUIRED},
                )
                ok = self._perform_handshake()
                if not ok:
                    self._close_ws()
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    continue

                backoff = 1.0
                self.subscribe_session_messages(self.session_target)

                while not self._stop.is_set():
                    try:
                        raw = self.ws.recv()
                        if not raw:
                            break
                        frame = json.loads(raw)
                        if self._message_handler:
                            try:
                                self._message_handler(frame)
                            except Exception:
                                pass
                    except WebSocketConnectionClosedException:
                        break
                    except Exception:
                        time.sleep(0.1)

            except Exception as exc:
                logger.debug("Gateway connection failed: %s", exc)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            finally:
                self._close_ws()

    def _close_ws(self):
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        self.ws = None
