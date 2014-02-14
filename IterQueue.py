import Queue as tQueue
from Queue import Empty, Full
import itertools
from time import time as _time

_threading = tQueue._threading
Thread = _threading.Thread
Condition = _threading.Condition

class Closed(Exception):
    "Exception raised by closed queue"
    pass

def _QueueMaker(base, name=None):
    if not name:
        name = "%s%s" % ("Iter", base.__name__)

    class _IterQueue(base):
        """
        This class provides an iterable queue
        The iteration can "finish" by closing the Queue or by initializing it
          with an iterable that exhausts. Otherwise it is an "infinite
          iterator"

        The queue object itself acts as an iterable, but the standard `get`
          method can be used as well. You can have multiple consumers all using
          the same queue object as an iterable

        Attempts to `put` to a closed queue will raise the `Closed` exception.

        Attempts to `get` from an *empty* closed queue will raise `StopIteration`

        Blocked `put`s and `get`s on a queue which is subsequently closed will
          also raise the `Closed` and `StopIteration` exception under the same
          circumstances. An iteration blocked in the `next` call will also receive
          `StopIteration` and therefore end the iterating loop
        """
        def __init__(self, iterable=None, *args, **kwargs):
            """
            Can be initialized with an iterable with the kwarg `iterable=` this
              causes `produce` to be called with the iterable and `close` set
              to True

            """
            base.__init__(self, *args, **kwargs)
            assert not hasattr(self, '_closed')
            self._closed = False
            self._iters = None
            self._iter_close = False
            self.iter_cond = Condition(self.mutex)

            if iterable:
                self.produce(iterable, close=True)

        def produce(self, iterable, close=False):
            """
            Produces all items from the iterable
            Returns immediately, "threaded" `put`s for free!

            Take care that `maxsize` of the queue is reasonable for the
              iterables. Particularly that it is not 0 (infinite) when adding
              large or infinite iterables

            If `maxsize` is 0 and the queue has an iterable, then the entire
              iterable is consumed and put into the queue at once. If you are
              using a large or infinite generator then you should set maxsize
              to some finite non-zero value.

            If `maxsize` is not 0 then the iterable will be consumed as long as
              the queue is not full. Every time a `get` is called, then, one
              more item will be consumed from the iterable to refill the queue
              in steady state.

            If `close` then the queue will close itself once all iterables
              added by this method are exhausted. Whether the queue will close
              itself depends on the `close` value of the *last* call to this
              method.

            A note on self closing queues
              The queue still allows you to `put` to it, though once the
              iterable is exhausted the queue will close itself, causing all
              puts after that to fail with exception `Closed`. Using put on
              such a queue is then a great way to create race conditions. It is
              not enthusiastically recommended.

            Raises `Closed` exception if the queue is already closed.
            """

            self.iter_cond.acquire()
            try:
                if not self._iters:
                    self._iters = iter(iterable)
                else:
                    self._iters = itertools.chain(self._iters, iter(iterable))
                self._iter_close = close
                self.iter_cond.notify()
            finally:
                self.iter_cond.release()

            def add_thread():
                while True:
                    self.iter_cond.acquire()
                    try:
                        while not self._iters:
                            if self._closed:
                                return
                            self.iter_cond.wait()
                        item = next(self._iters)
                    except StopIteration:
                        if self._iter_close:
                            self._closed = True
                            return
                        else:
                            # wait for another iterator to be added
                            continue
                    finally:
                        self.iter_cond.release()
                    # now add the item to the q
                    self.put(item)

            if not hasattr(self, "_add_thread"):
                self._add_thread = Thread(target=add_thread, name="add_thread")
                self._add_thread.setDaemon(True)
                self._add_thread.start()

        def close(self):
            """Close the queue.

            This will prevent further `put`s, and only allow `get`s
              until the contents are depleted.

            `put`s and `get`s which are prevented raise `Closed` and
              `StopIteration` respectively

            Calling `close` will also cause exceptions to be raised in blocked
              `get`s or `put`s and iterations as though they had just been called.
            """
            self.mutex.acquire()
            try:
                if not self._closed:
                    self._closed = True
                    self.not_empty.notify_all()
                    self.not_full.notify_all()
                    self.iter_cond.notify_all()
            finally:
                self.mutex.release()

        def closed(self):
            try:
                self.mutex.acquire()
                n = self._closed
            finally:
                self.mutex.release()
            return n

        def put(self, item, block=True, timeout=None):
            self.not_full.acquire()
            try:
                if self._closed:
                    raise Closed
                if self.maxsize > 0:
                    if not block:
                        if self._qsize() == self.maxsize:
                            raise Full
                    elif timeout is None:
                        while self._qsize() == self.maxsize:
                            if self._closed:
                                raise Closed
                            self.not_full.wait()
                    elif timeout < 0:
                        raise ValueError("'timeout' must be a positive number")
                    else:
                        endtime = _time() + timeout
                        while self._qsize() == self.maxsize:
                            if self._closed:
                                raise Closed
                            remaining = endtime - _time()
                            if remaining <= 0.0:
                                raise Full
                            self.not_full.wait(remaining)
                self._put(item)
                self.unfinished_tasks += 1
                self.not_empty.notify()
            finally:
                self.not_full.release()

        def get(self, block=True, timeout=None):
            self.not_empty.acquire()
            try:
                if not block:
                    if not self._qsize():
                        if self._closed:
                            raise StopIteration
                        else:
                            raise Empty
                elif timeout is None:
                    while not self._qsize():
                        if self._closed:
                            raise StopIteration
                        self.not_empty.wait()
                elif timeout < 0:
                    raise ValueError("'timeout' must be a positive number")
                else:
                    endtime = _time() + timeout
                    while not self._qsize():
                        if self._closed:
                            raise StopIteration
                        remaining = endtime - _time()
                        if remaining <= 0.0:
                            raise Empty
                        self.not_emtpy.wait(remaining)
                item = self._get()
                self.not_full.notify()
                return item
            finally:
                self.not_empty.release()

        def join(self, block=True, timeout=None):
            self.all_tasks_done.acquire()
            try:
                if not block:
                    if self.unfinished_tasks:
                        raise Full
                elif timeout is None:
                    while self.unfinished_tasks:
                        self.all_tasks_done.wait()
                elif timeout < 0:
                    raise ValueError("'timeout' must be a positive number")
                else:
                    endtime = _time() + timeout
                    while self.unfinished_tasks:
                        remaining = endtime - _time()
                        if remaining <= 0.0:
                            raise Full
                        self.all_tasks_done.wait(remaining)
            finally:
                self.all_tasks_done.release()

        # Be an iterator!!! YEAH!
        def __iter__(self):
            return self

        def __next__(self):
            try:
                return self.get()
            except Empty:
                raise StopIteration

        def next(self):
            return self.__next__()

    _IterQueue.__name__ = name
    return _IterQueue

Queue = _QueueMaker(tQueue.Queue)
PriorityQueue = _QueueMaker(tQueue.PriorityQueue)
LifoQueue = _QueueMaker(tQueue.LifoQueue)
