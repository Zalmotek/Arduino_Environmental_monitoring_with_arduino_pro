from micropython import const
import uasyncio as asyncio
from .core import ble, log_error, register_irq_handler
from .device import DeviceConnection
_IRQ_L2CAP_ACCEPT = const(22)
_IRQ_L2CAP_CONNECT = const(23)
_IRQ_L2CAP_DISCONNECT = const(24)
_IRQ_L2CAP_RECV = const(25)
_IRQ_L2CAP_SEND_READY = const(26)
_listening = False
def _l2cap_irq(event, data):
	if event not in (
		_IRQ_L2CAP_CONNECT,
		_IRQ_L2CAP_DISCONNECT,
		_IRQ_L2CAP_RECV,
		_IRQ_L2CAP_SEND_READY,
	):
		return
	if connection := DeviceConnection._connected.get(data[0], None):
		if channel := connection._l2cap_channel:
			if channel._cid is not None and channel._cid != data[1]:
				return
			if event == _IRQ_L2CAP_CONNECT:
				_, channel._cid, _, channel.our_mtu, channel.peer_mtu = data
			elif event == _IRQ_L2CAP_DISCONNECT:
				_, _, psm, status = data
				channel._status = status
				channel._cid = None
				connection._l2cap_channel = None
			elif event == _IRQ_L2CAP_RECV:
				channel._data_ready = True
			elif event == _IRQ_L2CAP_SEND_READY:
				channel._stalled = False
			channel._event.set()
def _l2cap_shutdown():
	global _listening
	_listening = False
register_irq_handler(_l2cap_irq, _l2cap_shutdown)
class L2CAPDisconnectedError(Exception):
	pass
class L2CAPConnectionError(Exception):
	pass
class L2CAPChannel:
	def __init__(self, connection):
		if not connection.is_connected():
			raise ValueError("Not connected")
		if connection._l2cap_channel:
			raise ValueError("Already has channel")
		connection._l2cap_channel = self
		self._connection = connection
		self.our_mtu = 0
		self.peer_mtu = 0
		self._cid = None
		self._status = 0
		self._stalled = False
		self._data_ready = False
		self._event = asyncio.ThreadSafeFlag()
	def _assert_connected(self):
		if self._cid is None:
			raise L2CAPDisconnectedError
	async def recvinto(self, buf, timeout_ms=None):
		self._assert_connected()
		with self._connection.timeout(timeout_ms):
			while not self._data_ready:
				await self._event.wait()
				self._assert_connected()
		self._assert_connected()
		n = ble.l2cap_recvinto(self._connection._conn_handle, self._cid, buf)
		self._data_ready = ble.l2cap_recvinto(self._connection._conn_handle, self._cid, None) > 0
		return n
	def available(self):
		self._assert_connected()
		return self._data_ready
	async def send(self, buf, timeout_ms=None):
		self._assert_connected()
		offset = 0
		chunk_size = min(self.our_mtu * 2, self.peer_mtu)
		mv = memoryview(buf)
		while offset < len(buf):
			if self._stalled:
				await self.flush(timeout_ms)
			self._stalled = not ble.l2cap_send(
				self._connection._conn_handle,
				self._cid,
				mv[offset : offset + chunk_size],
			)
			offset += chunk_size
	async def flush(self, timeout_ms=None):
		self._assert_connected()
		with self._connection.timeout(timeout_ms):
			while self._stalled:
				await self._event.wait()
				self._assert_connected()
	async def disconnect(self, timeout_ms=1000):
		if self._cid is None:
			return
		ble.l2cap_disconnect(self._connection._conn_handle, self._cid)
		await self.disconnected(timeout_ms)
	async def disconnected(self, timeout_ms=1000):
		with self._connection.timeout(timeout_ms):
			while self._cid is not None:
				await self._event.wait()
	async def __aenter__(self):
		return self
	async def __aexit__(self, exc_type, exc_val, exc_traceback):
		await self.disconnect()
async def accept(connection, psn, mtu, timeout_ms):
	global _listening
	channel = L2CAPChannel(connection)
	if not _listening:
		ble.l2cap_listen(psn, mtu)
		_listening = True
	with connection.timeout(timeout_ms):
		await channel._event.wait()
		return channel
async def connect(connection, psn, mtu, timeout_ms):
	if _listening:
		raise ValueError("Can't connect while listening")
	channel = L2CAPChannel(connection)
	with connection.timeout(timeout_ms):
		ble.l2cap_connect(connection._conn_handle, psn, mtu)
		await channel._event.wait()
		if channel._cid is not None:
			return channel
		else:
			raise L2CAPConnectionError(channel._status)