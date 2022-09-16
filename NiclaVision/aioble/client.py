from micropython import const
from collections import deque
import uasyncio as asyncio
import struct
import bluetooth
from .core import ble, GattError, register_irq_handler
from .device import DeviceConnection
_IRQ_GATTC_SERVICE_RESULT = const(9)
_IRQ_GATTC_SERVICE_DONE = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE = const(12)
_IRQ_GATTC_DESCRIPTOR_RESULT = const(13)
_IRQ_GATTC_DESCRIPTOR_DONE = const(14)
_IRQ_GATTC_READ_RESULT = const(15)
_IRQ_GATTC_READ_DONE = const(16)
_IRQ_GATTC_WRITE_DONE = const(17)
_IRQ_GATTC_NOTIFY = const(18)
_IRQ_GATTC_INDICATE = const(19)
_CCCD_UUID = const(0x2902)
_CCCD_NOTIFY = const(1)
_CCCD_INDICATE = const(2)
_FLAG_READ = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)
_FLAG_INDICATE = const(0x0020)
def _client_irq(event, data):
	if event == _IRQ_GATTC_SERVICE_RESULT:
		conn_handle, start_handle, end_handle, uuid = data
		ClientDiscover._discover_result(
			conn_handle, start_handle, end_handle, bluetooth.UUID(uuid)
		)
	elif event == _IRQ_GATTC_SERVICE_DONE:
		conn_handle, status = data
		ClientDiscover._discover_done(conn_handle, status)
	elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
		conn_handle, def_handle, value_handle, properties, uuid = data
		ClientDiscover._discover_result(
			conn_handle, def_handle, value_handle, properties, bluetooth.UUID(uuid)
		)
	elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
		conn_handle, status = data
		ClientDiscover._discover_done(conn_handle, status)
	elif event == _IRQ_GATTC_DESCRIPTOR_RESULT:
		conn_handle, dsc_handle, uuid = data
		ClientDiscover._discover_result(conn_handle, dsc_handle, bluetooth.UUID(uuid))
	elif event == _IRQ_GATTC_DESCRIPTOR_DONE:
		conn_handle, status = data
		ClientDiscover._discover_done(conn_handle, status)
	elif event == _IRQ_GATTC_READ_RESULT:
		conn_handle, value_handle, char_data = data
		ClientCharacteristic._read_result(conn_handle, value_handle, bytes(char_data))
	elif event == _IRQ_GATTC_READ_DONE:
		conn_handle, value_handle, status = data
		ClientCharacteristic._read_done(conn_handle, value_handle, status)
	elif event == _IRQ_GATTC_WRITE_DONE:
		conn_handle, value_handle, status = data
		ClientCharacteristic._write_done(conn_handle, value_handle, status)
	elif event == _IRQ_GATTC_NOTIFY:
		conn_handle, value_handle, notify_data = data
		ClientCharacteristic._on_notify(conn_handle, value_handle, bytes(notify_data))
	elif event == _IRQ_GATTC_INDICATE:
		conn_handle, value_handle, indicate_data = data
		ClientCharacteristic._on_indicate(conn_handle, value_handle, bytes(indicate_data))
register_irq_handler(_client_irq, None)
class ClientDiscover:
	def __init__(self, connection, disc_type, parent, timeout_ms, *args):
		self._connection = connection
		self._queue = []
		self._status = None
		self._event = asyncio.ThreadSafeFlag()
		self._disc_type = disc_type
		self._parent = parent
		self._timeout_ms = timeout_ms
		self._args = args
	async def _start(self):
		if self._connection._discover:
			raise ValueError("Discovery in progress")
		self._connection._discover = self
		self._disc_type._start_discovery(self._parent, *self._args)
	def __aiter__(self):
		return self
	async def __anext__(self):
		if self._connection._discover != self:
			await self._start()
		while True:
			while self._queue:
				return self._disc_type(self._parent, *self._queue.pop())
			if self._status is not None:
				self._connection._discover = None
				raise StopAsyncIteration
			await self._event.wait()
	def _discover_result(conn_handle, *args):
		if connection := DeviceConnection._connected.get(conn_handle, None):
			if discover := connection._discover:
				discover._queue.append(args)
				discover._event.set()
	def _discover_done(conn_handle, status):
		if connection := DeviceConnection._connected.get(conn_handle, None):
			if discover := connection._discover:
				discover._status = status
				discover._event.set()
class ClientService:
	def __init__(self, connection, start_handle, end_handle, uuid):
		self.connection = connection
		self._start_handle = start_handle
		self._end_handle = end_handle
		self.uuid = uuid
	def __str__(self):
		return "Service: {} {} {}".format(self._start_handle, self._end_handle, self.uuid)
	async def characteristic(self, uuid, timeout_ms=2000):
		result = None
		async for characteristic in self.characteristics(uuid, timeout_ms):
			if not result and characteristic.uuid == uuid:
				result = characteristic
		return result
	def characteristics(self, uuid=None, timeout_ms=2000):
		return ClientDiscover(self.connection, ClientCharacteristic, self, timeout_ms, uuid)
	def _start_discovery(connection, uuid=None):
		ble.gattc_discover_services(connection._conn_handle, uuid)
class BaseClientCharacteristic:
	def _register_with_connection(self):
		self._connection()._characteristics[self._value_handle] = self
	def _find(conn_handle, value_handle):
		if connection := DeviceConnection._connected.get(conn_handle, None):
			if characteristic := connection._characteristics.get(value_handle, None):
				return characteristic
			else:
				return None
	def _check(self, flag):
		if not (self.properties & flag):
			raise ValueError("Unsupported")
	async def read(self, timeout_ms=1000):
		self._check(_FLAG_READ)
		self._register_with_connection()
		self._read_status = None
		self._read_event = self._read_event or asyncio.ThreadSafeFlag()
		ble.gattc_read(self._connection()._conn_handle, self._value_handle)
		with self._connection().timeout(timeout_ms):
			while self._read_status is None:
				await self._read_event.wait()
			if self._read_status != 0:
				raise GattError(self._read_status)
			return self._read_data
	def _read_result(conn_handle, value_handle, data):
		if characteristic := ClientCharacteristic._find(conn_handle, value_handle):
			characteristic._read_data = data
			characteristic._read_event.set()
	def _read_done(conn_handle, value_handle, status):
		if characteristic := ClientCharacteristic._find(conn_handle, value_handle):
			characteristic._read_status = status
			characteristic._read_event.set()
	async def write(self, data, response=False, timeout_ms=1000):
		self._check(_FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)
		if (
			response is None
			and (self.properties & _FLAGS_WRITE)
			and not (self.properties & _FLAG_WRITE_NO_RESPONSE)
		):
			response = True
		if response:
			self._register_with_connection()
			self._write_status = None
			self._write_event = self._write_event or asyncio.ThreadSafeFlag()
		ble.gattc_write(self._connection()._conn_handle, self._value_handle, data, response)
		if response:
			with self._connection().timeout(timeout_ms):
				await self._write_event.wait()
				if self._write_status != 0:
					raise GattError(self._write_status)
	def _write_done(conn_handle, value_handle, status):
		if characteristic := ClientCharacteristic._find(conn_handle, value_handle):
			characteristic._write_status = status
			characteristic._write_event.set()
class ClientCharacteristic(BaseClientCharacteristic):
	def __init__(self, service, def_handle, value_handle, properties, uuid):
		self.service = service
		self.connection = service.connection
		self._def_handle = def_handle
		self._value_handle = value_handle
		self.properties = properties
		self.uuid = uuid
		if properties & _FLAG_READ:
			self._read_event = None
			self._read_data = None
			self._read_status = None
		if (properties & _FLAG_WRITE) or (properties & _FLAG_WRITE_NO_RESPONSE):
			self._write_event = None
			self._write_status = None
		if properties & _FLAG_NOTIFY:
			self._notify_event = asyncio.ThreadSafeFlag()
			self._notify_queue = deque((), 1)
		if properties & _FLAG_INDICATE:
			self._indicate_event = asyncio.ThreadSafeFlag()
			self._indicate_queue = deque((), 1)
	def __str__(self):
		return "Characteristic: {} {} {} {}".format(
			self._def_handle, self._value_handle, self.properties, self.uuid
		)
	def _connection(self):
		return self.service.connection
	async def descriptor(self, uuid, timeout_ms=2000):
		result = None
		async for descriptor in self.descriptors(timeout_ms):
			if not result and descriptor.uuid == uuid:
				result = descriptor
		return result
	def descriptors(self, timeout_ms=2000):
		return ClientDiscover(self.connection, ClientDescriptor, self, timeout_ms)
	def _start_discovery(service, uuid=None):
		ble.gattc_discover_characteristics(
			service.connection._conn_handle,
			service._start_handle,
			service._end_handle,
			uuid,
		)
	async def _notified_indicated(self, queue, event, timeout_ms):
		self._register_with_connection()
		if len(queue) <= 1:
			with self._connection().timeout(timeout_ms):
				await event.wait()
		return queue.popleft()
	async def notified(self, timeout_ms=None):
		self._check(_FLAG_NOTIFY)
		return await self._notified_indicated(self._notify_queue, self._notify_event, timeout_ms)
	def _on_notify_indicate(self, queue, event, data):
		wake = len(queue) == 0
		queue.append(data)
		if wake:
			event.set()
	def _on_notify(conn_handle, value_handle, notify_data):
		if characteristic := ClientCharacteristic._find(conn_handle, value_handle):
			characteristic._on_notify_indicate(
				characteristic._notify_queue, characteristic._notify_event, notify_data
			)
	async def indicated(self, timeout_ms=None):
		self._check(_FLAG_INDICATE)
		return await self._notified_indicated(
			self._indicate_queue, self._indicate_event, timeout_ms
		)
	def _on_indicate(conn_handle, value_handle, indicate_data):
		if characteristic := ClientCharacteristic._find(conn_handle, value_handle):
			characteristic._on_notify_indicate(
				characteristic._indicate_queue, characteristic._indicate_event, indicate_data
			)
	async def subscribe(self, notify=True, indicate=False):
		self._register_with_connection()
		if cccd := await self.descriptor(bluetooth.UUID(_CCCD_UUID)):
			await cccd.write(struct.pack("<H", _CCCD_NOTIFY * notify + _CCCD_INDICATE * indicate))
		else:
			raise ValueError("CCCD not found")
class ClientDescriptor(BaseClientCharacteristic):
	def __init__(self, characteristic, dsc_handle, uuid):
		self.characteristic = characteristic
		self.uuid = uuid
		self._value_handle = dsc_handle
		self.properties = _FLAG_READ | _FLAG_WRITE_NO_RESPONSE
	def __str__(self):
		return "Descriptor: {} {} {} {}".format(
			self._def_handle, self._value_handle, self.properties, self.uuid
		)
	def _connection(self):
		return self.characteristic.service.connection
	def _start_discovery(characteristic, uuid=None):
		ble.gattc_discover_descriptors(
			characteristic._connection()._conn_handle,
			characteristic._value_handle,
			characteristic._value_handle + 5,
		)