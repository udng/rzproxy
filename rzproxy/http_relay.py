#!/usr/bin/env python
import socket
import logging
import multiprocessing

from gevent import pool
from gevent import select
from gevent.server import StreamServer
from gevent import monkey
monkey.patch_socket()

BUF_SIZE = 4 * 1024

logger = logging.getLogger(__name__)


class HttpRelayHandler(multiprocessing.Process):
    # pool_count max is 100000
    # ensure the proxy weight is max
    def __init__(self, queue, proxy=("127.0.0.1", 8399), pool_count=100):
        multiprocessing.Process.__init__(self)
        self.proxy = proxy
        self.queue = queue
        self.pool = pool.Pool(pool_count)
        self.cache = None
        self.server = StreamServer(
                proxy, self._handle_connection, spawn=self.pool)

    def _handle_connection(self, local_sock, address):
        if not self.cache:
            self.cache = self.queue.setup_cache
        cache = self.cache
        best_proxy = max(cache, key=cache.get)
        proxy_value = self.cache.get(best_proxy)
        logger.info("proxy is {}, weight is {}"
                    .format(best_proxy, proxy_value))
        self.cache[best_proxy] = proxy_value * 0.5
        ip, port = best_proxy.split(":")
        try:
            remote_sock = self._create_remote_connection((ip, int(port)))
            while True:
                r, w, e = select.select(
                        [local_sock, remote_sock], [], [])
                if local_sock in r:
                    data = local_sock.recv(BUF_SIZE)
                    if remote_sock.send(data) <= 0:
                        break
                if remote_sock in r:
                    data = remote_sock.recv(BUF_SIZE)
                    if local_sock.send(data) <= 0:
                        break
            self.cache[best_proxy] = self.cache[best_proxy] / 0.5
            remote_sock.close()
        except Exception, e:
            # connection refused
            logger.error(e.message)
            self.queue.reduce_weight(best_proxy)

    def setup_cache(self):
        self.cache = self.queue.setup_cache

    def _create_remote_connection(self, proxy):
        remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote_sock.connect(proxy)
        return remote_sock

    def run(self):
        logger.info("Starting local server on {}.".format(self.proxy))
        self.server.serve_forever()
