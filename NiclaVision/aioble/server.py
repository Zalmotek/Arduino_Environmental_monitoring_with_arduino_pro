from micropython import const
from collections import deque
import bluetooth
import uasyncio as asyncio
from .core import (
	ensure_active,
	ble,
	log_info,
	log_error,
	log_warn,
	register_irq_handler,
)
from .device import DeviceConnection, DeviceTimeout
_registered_characteristics = {}
_IRQ_GATTS_WRITE = const(3)
_IRQ_GATTS_READ_REQUEST = const(4)
_IRQ_GATTS_INDICATE_DONE = const(20)
_FLAG_READ = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)
_FLAG_INDICATE = const(0x0020)
_FLAG_READ_ENCRYPTED = const(0x0200)
_FLAG_READ_AUTHENTICATED = const(0x0400)
_FLAG_READ_AUTHORIZED = const(0x0800)
_FLAG_WRITE_ENCRYPTED = const(0x1000)
_FLAG_WRITE_AUTHENTICATED = const(0x2000)
_FLAG_WRITE_AUTHORIZED = const(0x4000)
_FLAG_WRITE_CAPTURE = const(0x10000)
_FLAG_DESC_READ = const(1)
_FLAG_DESC_WRITE = const(2)
_WRITE_CAPTURE_QUEUE_LIMIT = const(10)
def _server_irq(event, data):
	if event == _IRQ_GATTS_WRITE:
		conn_handle, attr_handle = data
		Characteristic._remote_write(conn_handle, attr_handle)
	elif event == _IRQ_GATTS_READ_REQUEST:
		conn_handle, attr_handle = data
		return Characteristic._remote_read(conn_handle, attr_handle)
	elif event == _IRQ_GATTS_INDICATE_DONE:
		conn_handle, value_handle, status = data
		Characteristic._indicate_done(conn_handle, value_handle, status)
def _server_shutdown():
	global _registered_characteristics
	_registered_characteristics = {}
register_irq_handler(_server_irq, _server_shutdown)
class Service:
	def __init__(self, uuid):
		self.uuid = uuid
		self.characteristics = []
	def _tuple(self):
		return (self.uuid, tuple(c._tuple() for c in self.characteristics))
class BaseCharacteristic:
	def _register(self, value_handle):
		self._value_handle = value_handle
		_registered_characteristics[value_handle] = self
		if self._initial is not None:
			self.write(self._initial)
			self._initial = None
	def _tuple(self):
		return (self.uuid, self.flags)
	def read(self):
		if self._value_handle is None:
			return self._initial or b""
		else:
			return ble.gatts_read(self._value_handle)
	def write(self, data, send_update=False):
		if self._value_handle is None:
			self._initial = data
		else:
			ble.gatts_write(self._value_handle, data, send_update)
	async def written(self, timeout_ms=None):
		if not self._write_event:
			raise ValueError()
		if len(self._write_queue) <= 1:
			with DeviceTimeout(None, timeout_ms):
				await self._write_event.wait()
		return self._write_queue.popleft()
	def on_read(self, connection):
		return 0
	def _remote_write(conn_handle, value_handle):
		if characteristic := _registered_characteristics.get(value_handle, None):
			wake = len(characteristic._write_queue) == 0
			conn = DeviceConnection._connected.get(conn_handle, None)
			q = characteristic._write_queue
			if characteristic.flags & _FLAG_WRITE_CAPTURE:
				data = characteristic.read()
				q.append((conn, data))
			else:
				q.append(conn)
			if wake:
				characteristic._write_event.set()
	def _remote_read(conn_handle, value_handle):
		if characteristic := _registered_characteristics.get(value_handle, None):
			return characteristic.on_read(DeviceConnection._connected.get(conn_handle, None))
class Characteristic(BaseCharacteristic):
	def __init__(
		self,
		service,
		uuid,
		read=False,
		write=False,
		write_no_response=False,
		notify=False,
		indicate=False,
		initial=None,
		capture=False,
	):
		service.characteristics.append(self)
		self.descriptors = []
		flags = 0
		if read:
			flags |= _FLAG_READ
		if write or write_no_response:
			flags |= (_FLAG_WRITE if write else 0) | (
				_FLAG_WRITE_NO_RESPONSE if write_no_response else 0
			)
			if capture:
				flags |= _FLAG_WRITE_CAPTURE
			self._write_event = asyncio.ThreadSafeFlag()
			self._write_queue = deque((), _WRITE_CAPTURE_QUEUE_LIMIT if capture else 1)
		if notify:
			flags |= _FLAG_NOTIFY
		if indicate:
			flags |= _FLAG_INDICATE
			self._indicate_connection = None
			self._indicate_event = asyncio.ThreadSafeFlag()
			self._indicate_status = None
		self.uuid = uuid
		self.flags = flags
		self._value_handle = None
		self._initial = initial
	def notify(self, connection, data=None):
		if not (self.flags & _FLAG_NOTIFY):
			raise ValueError("Not supported")
		ble.gatts_notify(connection._conn_handle, self._value_handle, data)
	async def indicate(self, connection, timeout_ms=1000):
		if not (self.flags & _FLAG_INDICATE):
			raise ValueError("Not supported")
		if self._indicate_connection is not None:
			raise ValueError("In progress")
		if not connection.is_connected():
			raise ValueError("Not connected")
		self._indicate_connection = connection
		self._indicate_status = None
		try:
			with connection.timeout(timeout_ms):
				ble.gatts_indicate(connection._conn_handle, self._value_handle)
				await self._indicate_event.wait()
				if self._indicate_status != 0:
					raise GattError(self._indicate_status)
		finally:
			self._indicate_connection = None
	def _indicate_done(conn_handle, value_handle, status):
		if characteristic := _registered_characteristics.get(value_handle, None):
			if connection := DeviceConnection._connected.get(conn_handle, None):
				if not characteristic._indicate_connection:
					return
				assert connection == characteristic._indicate_connection
				characteristic._indicate_status = status
				characteristic._indicate_event.set()
class BufferedCharacteristic(Characteristic):
	def __init__(self, service, uuid, max_len=20, append=False):
		super().__init__(service, uuid, read=True)
		self._max_len = max_len
		self._append = append
	def _register(self, value_handle):
		super()._register(value_handle)
		ble.gatts_set_buffer(value_handle, self._max_len, self._append)
class Descriptor(BaseCharacteristic):
	def __init__(self, characteristic, uuid, read=False, write=False, initial=None):
		characteristic.descriptors.append(self)
		flags = 0
		if read:
			flags |= _FLAG_DESC_READ
		if write:
			self._write_connection = None
			self._write_event = asyncio.ThreadSafeFlag()
			flags |= _FLAG_DESC_WRITE
		self.uuid = uuid
		self.flags = flags
		self._value_handle = None
		self._initial = initial
def register_services(*services):
	ensure_active()
	_registered_characteristics.clear()
	handles = ble.gatts_register_services(tuple(s._tuple() for s in services))
	for i in range(len(services)):
		service_handles = handles[i]
		service = services[i]
		n = 0
		for characteristic in service.characteristics:
			characteristic._register(service_handles[n])
			n += 1
			for descriptor in characteristic.descriptors:
				descriptor._register(service_handles[n])
				n += 1