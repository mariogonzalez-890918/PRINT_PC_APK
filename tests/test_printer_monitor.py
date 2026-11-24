from concurrent.futures import Future
from pathlib import Path
import sys
import unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from printer_monitor import PrinterMonitor

class MonitorTest(unittest.TestCase):
    def test_pending_scan_never_waits_or_reports_empty_list(self):
        future=Future();pool=MagicMock();pool.submit.return_value=future
        with patch('printer_monitor.ThreadPoolExecutor',return_value=pool):
            monitor=PrinterMonitor(lambda:[])
            self.assertEqual(None,monitor.poll()[0]);self.assertEqual(None,monitor.poll()[0])
            self.assertEqual(1,pool.submit.call_count)
            future.set_result(['bixo'])
            self.assertEqual((['bixo'],''),monitor.poll());monitor.close()
    def test_failed_scan_is_warning_and_successful_empty_scan_removes_old_queues(self):
        future=Future();pool=MagicMock();pool.submit.return_value=future
        with patch('printer_monitor.ThreadPoolExecutor',return_value=pool):
            monitor=PrinterMonitor(lambda:[]);monitor.poll();future.set_exception(RuntimeError('spooler unavailable'))
            self.assertEqual((None,'spooler unavailable'),monitor.poll())
            monitor.next_scan=0;other=Future();other.set_result([]);pool.submit.return_value=other
            monitor.poll();self.assertEqual(([],''),monitor.poll());monitor.close()
