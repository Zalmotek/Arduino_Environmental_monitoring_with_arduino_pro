from micropython import const
import uasyncio as asyncio
import binascii
from .core import ble, register_irq_handler, log_error
_IRQ_MTU_EXCHANGED = const(21)
class DeviceDisconnectedError(Exception):
	pass
def _device_irq(event, data):
	if event == _IRQ_MTU_EXCHANGED:
		conn_handle, mtu = data
		if device := DeviceConnection._connected.get(conn_handle, None):
			device.mtu = mtu
			if device._mtu_event:
				device._mtu_event.set()
register_irq_handler(_device_irq, None)
class DeviceTimeout:
	def __init__(self, connection, timeout_ms):
		self._connection = connection
		self._timeout_ms = timeout_ms
		self._timeout_task = None
		self._task = asyncio.current_task()
		if connection:
			connection._timeouts.append(self)
	async def _timeout_sleep(self):
		try:
			await asyncio.sleep_ms(self._timeout_ms)
		except asyncio.CancelledError:
			return
		self._timeout_task = None
		self._task.cancel()
	def __enter__(self):
		if self._timeout_ms:
			self._timeout_task = asyncio.create_task(self._timeout_sleep())
	def __exit__(self, exc_type, exc_val, exc_traceback):
		if self._connection:
			self._connection._timeouts.remove(self)
		try:
			if exc_type == asyncio.CancelledError:
				if self._timeout_ms and self._timeout_task is None:
					raise asyncio.TimeoutError
				if self._connection and self._connection._conn_handle is None:
					raise DeviceDisconnectedError
				return
		finally:
			if self._timeout_task:
				self._timeout_task.cancel()
class Device:
	def __init__(self, addr_type, addr):
		self.addr_type = addr_type
		self.addr = addr if len(addr) == 6 else binascii.unhexlify(addr.replace(":", ""))
		self._connection = None
	def __eq__(self, rhs):
		return self.addr_type == rhs.addr_type and self.addr == rhs.addr
	def __hash__(self):
		return hash((self.addr_type, self.addr))
	def __str__(self):
		return "Device({}, {}{})".format(
			"ADDR_PUBLIC" if self.addr_type == 0 else "ADDR_RANDOM",
			self.addr_hex(),
			", CONNECTED" if self._connection else "",
		)
	def addr_hex(self):
		return binascii.hexlify(self.addr, ":").decode()
	async def connect(self, timeout_ms=10000):
		if self._connection:
			return self._connection
		from .central import _connect
		await _connect(DeviceConnection(self), timeout_ms)
		self._connection._run_task()
		return self._connection
class DeviceConnection:
	_connected = {}
	def __init__(self, device):
		self.device = device
		device._connection = self
		self.encrypted = False
		self.authenticated = False
		self.bonded = False
		self.key_size = False
		self.mtu = None
		self._conn_handle = None
		self._event = None
		self._mtu_event = None
		self._discover = None
		self._characteristics = {}
		self._task = None
		self._timeouts = []
		self._pair_event = None
		self._l2cap_channel = None
	async def device_task(self):
		assert self._conn_handle is not None
		await self._event.wait()
		del DeviceConnection._connected[self._conn_handle]
		self._conn_handle = None
		self.device._connection = None
		for t in self._timeouts:
			t._task.cancel()
	def _run_task(self):
		self._event = self._event or asyncio.ThreadSafeFlag()
		self._task = asyncio.create_task(self.device_task())
	async def disconnect(self, timeout_ms=2000):
		await self.disconnected(timeout_ms, disconnect=True)
	async def disconnected(self, timeout_ms=60000, disconnect=False):
		if not self.is_connected():
			return
		assert self._task
		if disconnect:
			try:
				ble.gap_disconnect(self._conn_handle)
			except OSError as e:
				log_error("Disconnect", e)
		with DeviceTimeout(None, timeout_ms):
			await self._task
	async def service(self, uuid, timeout_ms=2000):
		result = None
		async for service in self.services(uuid, timeout_ms):
			if not result and service.uuid == uuid:
				result = service
		return result
	def services(self, uuid=None, timeout_ms=2000):
		from .client import ClientDiscover, ClientService
		return ClientDiscover(self, ClientService, self, timeout_ms, uuid)
	async def pair(self, *args, **kwargs):
		from .security import pair
		await pair(self, *args, **kwargs)
	def is_connected(self):
		return self._conn_handle is not None
	def timeout(self, timeout_ms):
		return DeviceTimeout(self, timeout_ms)
	async def exchange_mtu(self, mtu=None):
		if not self.is_connected():
			raise ValueError("Not connected")
		if mtu:
			ble.config(mtu=mtu)
		self._mtu_event = self._mtu_event or asyncio.ThreadSafeFlag()
		ble.gattc_exchange_mtu(self._conn_handle)
		await self._mtu_event.wait()
		return self.mtu
	async def l2cap_accept(self, psm, mtu, timeout_ms=None):
		from .l2cap import accept
		return await accept(self, psm, mtu, timeout_ms)
	async def l2cap_connect(self, psm, mtu, timeout_ms=1000):
		from .l2cap import connect
		return await connect(self, psm, mtu, timeout_ms)
	async def __aenter__(self):
		return self
	async def __aexit__(self, exc_type, exc_val, exc_traceback):
		await self.disconnect()