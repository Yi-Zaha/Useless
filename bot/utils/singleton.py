import threading


class Singleton(type):
    _instances = {}
    _lock = threading.Lock()

    def __call__(self, *args, **kwargs):
        if self not in self._instances:
            with self._lock:
                if self not in self._instances:
                    self._instances[self] = super(Singleton, self).__call__(
                        *args, **kwargs
                    )
        return self._instances[self]
