from micropython import const, schedule
import uasyncio as asyncio
import binascii
import json
from .core import log_info, log_warn, ble, register_irq_handler
from .device import DeviceConnection
_IRQ_ENCRYPTION_UPDATE = const(28)
_IRQ_GET_SECRET = const(29)
_IRQ_SET_SECRET = const(30)
_IRQ_PASSKEY_ACTION = const(31)
_IO_CAPABILITY_DISPLAY_ONLY = const(0)
_IO_CAPABILITY_DISPLAY_YESNO = const(1)
_IO_CAPABILITY_KEYBOARD_ONLY = const(2)
_IO_CAPABILITY_NO_INPUT_OUTPUT = const(3)
_IO_CAPABILITY_KEYBOARD_DISPLAY = const(4)
_PASSKEY_ACTION_INPUT = const(2)
_PASSKEY_ACTION_DISP = const(3)
_PASSKEY_ACTION_NUMCMP = const(4)
_DEFAULT_PATH = "ble_secrets.json"
_secrets = {}
_modified = False
_path = None
def load_secrets(path=None):
	global _path, _secrets
	_path = path or _path or _DEFAULT_PATH
	_secrets = {}
	try:
		with open(_path, "r") as f:
			entries = json.load(f)
			for sec_type, key, value in entries:
				_secrets[sec_type, binascii.a2b_base64(key)] = binascii.a2b_base64(value)
	except:
		log_warn("No secrets available")
def _save_secrets(arg=None):
	global _modified, _path
	_path = _path or _DEFAULT_PATH
	if not _modified:
		return
	with open(_path, "w") as f:
		json_secrets = [
			(sec_type, binascii.b2a_base64(key), binascii.b2a_base64(value))
			for (sec_type, key), value in _secrets.items()
		]
		json.dump(json_secrets, f)
		_modified = False
def _security_irq(event, data):
	global _modified
	if event == _IRQ_ENCRYPTION_UPDATE:
		conn_handle, encrypted, authenticated, bonded, key_size = data
		log_info("encryption update", conn_handle, encrypted, authenticated, bonded, key_size)
		if connection := DeviceConnection._connected.get(conn_handle, None):
			connection.encrypted = encrypted
			connection.authenticated = authenticated
			connection.bonded = bonded
			connection.key_size = key_size
			if encrypted and connection._pair_event:
				connection._pair_event.set()
	elif event == _IRQ_SET_SECRET:
		sec_type, key, value = data
		key = sec_type, bytes(key)
		value = bytes(value) if value else None
		log_info("set secret:", key, value)
		if value is None:
			if key not in _secrets:
				return False
			del _secrets[key]
		else:
			_secrets[key] = value
		_modified = True
		schedule(_save_secrets, None)
		return True
	elif event == _IRQ_GET_SECRET:
		sec_type, index, key = data
		log_info("get secret:", sec_type, index, bytes(key) if key else None)
		if key is None:
			i = 0
			for (t, _key), value in _secrets.items():
				if t == sec_type:
					if i == index:
						return value
					i += 1
			return None
		else:
			key = sec_type, bytes(key)
			return _secrets.get(key, None)
	elif event == _IRQ_PASSKEY_ACTION:
		conn_handle, action, passkey = data
		log_info("passkey action", conn_handle, action, passkey)
def _security_shutdown():
	global _secrets, _modified, _path
	_secrets = {}
	_modified = False
	_path = None
register_irq_handler(_security_irq, _security_shutdown)
async def pair(
	connection,
	bond=True,
	le_secure=True,
	mitm=False,
	io=_IO_CAPABILITY_NO_INPUT_OUTPUT,
	timeout_ms=20000,
):
	ble.config(bond=bond, le_secure=le_secure, mitm=mitm, io=io)
	with connection.timeout(timeout_ms):
		connection._pair_event = asyncio.ThreadSafeFlag()
		ble.gap_pair(connection._conn_handle)
		await connection._pair_event.wait()