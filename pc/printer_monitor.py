"""Bounded asynchronous discovery; a local spooler failure never blocks heartbeats."""
from concurrent.futures import ThreadPoolExecutor
import time

class PrinterMonitor:
    def __init__(self,discover):
        self.discover=discover;self.pool=ThreadPoolExecutor(max_workers=1)
        self.future=None;self.next_scan=0;self.names=None;self.warning='Actualizando impresoras de esta PC.'
    def poll(self):
        if self.future is not None and self.future.done():
            try:self.names=self.future.result();self.warning=''
            except Exception as error:self.names=None;self.warning=str(error)[:500]
            self.future=None;self.next_scan=time.monotonic()+30
        if self.future is None and time.monotonic()>=self.next_scan:self.future=self.pool.submit(self.discover)
        return self.names,self.warning
    def close(self):self.pool.shutdown(wait=False,cancel_futures=True)
