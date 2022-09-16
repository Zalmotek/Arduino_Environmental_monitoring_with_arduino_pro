import bluetooth
log_level = 1
def log_error(*args):
	if log_level > 0:
		print("[aioble] E:", *args)
def log_warn(*args):
	if log_level > 1:
		print("[aioble] W:", *args)
def log_info(*args):
	if log_level > 2:
		print("[aioble] I:", *args)
class GattError(Exception):
	def __init__(self, status):
		self._status = status
def ensure_active():
	if not ble.active():
		try:
			from .security import load_secrets
			load_secrets()
		except:
			pass
		ble.active(True)
def config(*args, **kwargs):
	ensure_active()
	return ble.config(*args, **kwargs)
_irq_handlers = []
_shutdown_handlers = []
def register_irq_handler(irq, shutdown):
	if irq:
		_irq_handlers.append(irq)
	if shutdown:
		_shutdown_handlers.append(shutdown)
def stop():
	ble.active(False)
	for handler in _shutdown_handlers:
		handler()
def ble_irq(event, data):
	log_info(event, data)
	for handler in _irq_handlers:
		result = handler(event, data)
		if result is not None:
			return result
ble = bluetooth.BLE()
ble.irq(ble_irq)