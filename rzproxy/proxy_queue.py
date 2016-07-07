#!/usr/bin/env python
import time
import mysql.connector


class ProxyQueue(object):
    def __init__(self, host="localhost", port=3306, database='RzProxy',
                 user="root", passwd=None):
        self.database_name = database
        self.conn = mysql.connector.connect(user=user,
                                            password=passwd,
                                            host=host,
                                            port=port,
                                            autocommit=True)
        if database not in [x[0] for x in self._execute('show databases')]:
            self._execute('CREATE DATABASE {}'.format(database))
        self.conn.database = database
        self._execute('''CREATE TABLE IF NOT EXISTS proxy_pool (
            `proxy` varchar(20) PRIMARY KEY,
            `weight` double(16, 4),
            `updatetime` double(16, 4)
            )ENGINE=InnoDB CHARSET=utf8''')

    @property
    def best_proxy(self):
        result_cur = self._execute(
            "SELECT proxy FROM proxy_pool GROUP BY weight DESC LIMIT 1")
        return result_cur.fetchone()[0]

    @property
    def last_updatetime(self):
        result_cur = self._execute("SELECT updatetime FROM proxy_pool \
                                  GROUP BY updatetime DESC LIMIT 1")
        result = result_cur.fetchone()
        if result:
            return result[0]
        else:
            # no data in the table
            return 0

    @property
    def setup_cache(self):
        cache = {}
        result_list = self._execute("select proxy, weight from proxy_pool")
        for result in result_list.fetchall():
            cache[result[0]] = result[1]
        return cache

    def get(self, key):
        result_cur = self._execute(
            "SELECT weight from proxy_pool WHERE proxy='{}'".format(key))
        result = result_cur.fetchone()[0]
        return result

    def set(self, key, value, now=time.time()):
        # when the proxy is checked
        self._execute('''INSERT INTO proxy_pool(proxy, weight, updatetime)
            values ("{0}", {1}, {2}) ON DUPLICATE KEY UPDATE \
            weight={1}, updatetime={2}'''.format(key, value, now))

    def remove(self, key):
        self._execute("DELETE FROM proxy_pool WHERE proxy='{}'".format(key))

    def _update(self, key, value):
        # not change the updatetime
        self._execute(
                "UPDATE proxy_pool SET weight={} WHERE proxy='{}'"
                .format(value, key))

    def reduce_weight(self, key):
        current_value = self.get(key)
        self._update(key, current_value * 0.8)

    def add_weight(self, key):
        current_value = self.get(key)
        self._update(key, current_value / 0.8)

    def _execute(self, sql_query, values=[]):
        dbcur = self._dbcur()
        dbcur.execute(sql_query, values)
        return dbcur

    def _dbcur(self):
        try:
            if self.conn.unread_result:
                self.conn.get_rows()
            return self.conn.cursor()
        except (mysql.connector.OperationalError,
                mysql.connector.InterfaceError):
            self.conn.ping(reconnect=True)
            self.conn.database = self.database_name
            return self.conn.cursor()
