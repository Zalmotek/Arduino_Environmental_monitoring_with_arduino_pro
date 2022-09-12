from micropython import const
import bluetooth
import struct
import uasyncio as asyncio
from .core import (
	ensure_active,
	ble,
	log_info,
	log_error,
	log_warn,
	register_irq_handler,
)
from .device import Device, DeviceConnection, DeviceTimeout
_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_IRQ_PERIPHERAL_CONNECT = const(7)
_IRQ_PERIPHERAL_DISCONNECT = const(8)
_ADV_IND = const(0)
_ADV_DIRECT_IND = const(1)
_ADV_SCAN_IND = const(2)
_ADV_NONCONN_IND = const(3)
_SCAN_RSP = const(4)
_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID16_INCOMPLETE = const(0x2)
_ADV_TYPE_UUID16_COMPLETE = const(0x3)
_ADV_TYPE_UUID32_INCOMPLETE = const(0x4)
_ADV_TYPE_UUID32_COMPLETE = const(0x5)
_ADV_TYPE_UUID128_INCOMPLETE = const(0x6)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_APPEARANCE = const(0x19)
_ADV_TYPE_MANUFACTURER = const(0xFF)
_active_scanner = None
_connecting = set()
def _central_irq(event, data):
	if event == _IRQ_SCAN_RESULT:
		addr_type, addr, adv_type, rssi, adv_data = data
		if not _active_scanner:
			return
		_active_scanner._queue.append((addr_type, bytes(addr), adv_type, rssi, bytes(adv_data)))
		_active_scanner._event.set()
	elif event == _IRQ_SCAN_DONE:
		if not _active_scanner:
			return
		_active_scanner._done = True
		_active_scanner._event.set()
	elif event == _IRQ_PERIPHERAL_CONNECT:
		conn_handle, addr_type, addr = data
		for d in _connecting:
			if d.addr_type == addr_type and d.addr == addr:
				connection = d._connection
				connection._conn_handle = conn_handle
				connection._event.set()
				break
	elif event == _IRQ_PERIPHERAL_DISCONNECT:
		conn_handle, _, _ = data
		if connection := DeviceConnection._connected.get(conn_handle, None):
			connection._event.set()
def _central_shutdown():
	global _active_scanner, _connecting
	_active_scanner = None
	_connecting = set()
register_irq_handler(_central_irq, _central_shutdown)
async def _cancel_pending():
	if _active_scanner:
		await _active_scanner.cancel()
async def _connect(connection, timeout_ms):
	device = connection.device
	if device in _connecting:
		return
	ensure_active()
	await _cancel_pending()
	_connecting.add(device)
	connection._event = connection._event or asyncio.ThreadSafeFlag()
	try:
		with DeviceTimeout(None, timeout_ms):
			ble.gap_connect(device.addr_type, device.addr)
			await connection._event.wait()
			assert connection._conn_handle is not None
			DeviceConnection._connected[connection._conn_handle] = connection
	finally:
		_connecting.remove(device)
class ScanResult:
	def __init__(self, device):
		self.device = device
		self.adv_data = None
		self.resp_data = None
		self.rssi = None
		self.connectable = False
	def _update(self, adv_type, rssi, adv_data):
		updated = False
		if rssi != self.rssi:
			self.rssi = rssi
			updated = True
		if adv_type in (_ADV_IND, _ADV_NONCONN_IND):
			if adv_data != self.adv_data:
				self.adv_data = adv_data
				self.connectable = adv_type == _ADV_IND
				updated = True
		elif adv_type == _ADV_SCAN_IND:
			if adv_data != self.adv_data and self.resp_data:
				updated = True
			self.adv_data = adv_data
		elif adv_type == _SCAN_RSP and adv_data:
			if adv_data != self.resp_data:
				self.resp_data = adv_data
				updated = True
		return updated
	def __str__(self):
		return "Scan result: {} {}".format(self.device, self.rssi)
	def _decode_field(self, *adv_type):
		for payload in (self.adv_data, self.resp_data):
			if not payload:
				continue
			i = 0
			while i + 1 < len(payload):
				if payload[i + 1] in adv_type:
					yield payload[i + 2 : i + payload[i] + 1]
				i += 1 + payload[i]
	def name(self):
		for n in self._decode_field(_ADV_TYPE_NAME):
			return str(n, "utf-8") if n else ""
	def services(self):
		for u in self._decode_field(_ADV_TYPE_UUID16_INCOMPLETE, _ADV_TYPE_UUID16_COMPLETE):
			yield bluetooth.UUID(struct.unpack("<H", u)[0])
		for u in self._decode_field(_ADV_TYPE_UUID32_INCOMPLETE, _ADV_TYPE_UUID32_COMPLETE):
			yield bluetooth.UUID(struct.unpack("<I", u)[0])
		for u in self._decode_field(_ADV_TYPE_UUID128_INCOMPLETE, _ADV_TYPE_UUID128_COMPLETE):
			yield bluetooth.UUID(u)
	def manufacturer(self, filter=None):
		for u in self._decode_field(_ADV_TYPE_MANUFACTURER):
			if len(u) < 2:
				continue
			m = struct.unpack("<H", u[0:2])[0]
			if filter is None or m == filter:
				yield (m, u[2:])
class scan:
	def __init__(self, duration_ms, interval_us=None, window_us=None, active=False):
		self._queue = []
		self._event = asyncio.ThreadSafeFlag()
		self._done = False
		self._results = set()
		self._duration_ms = duration_ms
		self._interval_us = interval_us or 1280000
		self._window_us = window_us or 11250
		self._active = active
	async def __aenter__(self):
		global _active_scanner
		ensure_active()
		await _cancel_pending()
		_active_scanner = self
		ble.gap_scan(self._duration_ms, self._interval_us, self._window_us, self._active)
		return self
	async def __aexit__(self, exc_type, exc_val, exc_traceback):
		if _active_scanner == self:
			await self.cancel()
	def __aiter__(self):
		assert _active_scanner == self
		return self
	async def __anext__(self):
		global _active_scanner
		if _active_scanner != self:
			raise StopAsyncIteration
		while True:
			while self._queue:
				addr_type, addr, adv_type, rssi, adv_data = self._queue.pop()
				for r in self._results:
					if r.device.addr_type == addr_type and r.device.addr == addr:
						result = r
						break
				else:
					device = Device(addr_type, addr)
					result = ScanResult(device)
					self._results.add(result)
				if result._update(adv_type, rssi, adv_data):
					return result
			if self._done:
				_active_scanner = None
				raise StopAsyncIteration
			await self._event.wait()
	async def cancel(self):
		if self._done:
			return
		ble.gap_scan(None)
		while not self._done:
			await self._event.wait()
		global _active_scanner
		_active_scanner = None