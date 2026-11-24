"""Minimal local Windows queue enumeration; no per-printer RPC or driver queries."""
import ctypes
from ctypes import wintypes
import json
import sys

class PRINTER_INFO_4(ctypes.Structure):
    _fields_=[('pPrinterName',wintypes.LPWSTR),('pServerName',wintypes.LPWSTR),('Attributes',wintypes.DWORD)]

def enumerate_queues():
    spool=ctypes.WinDLL('winspool.drv',use_last_error=True)
    enum=spool.EnumPrintersW
    enum.argtypes=[wintypes.DWORD,wintypes.LPWSTR,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.POINTER(wintypes.DWORD)]
    enum.restype=wintypes.BOOL
    needed=wintypes.DWORD();count=wintypes.DWORD()
    result=enum(6,None,4,None,0,ctypes.byref(needed),ctypes.byref(count))
    error=ctypes.get_last_error()
    if not result and error!=122:raise ctypes.WinError(error)
    if needed.value==0:return []
    for _ in range(3):
        size=needed.value
        if size>16*1024*1024:raise ValueError('La lista de impresoras supera el tamaño permitido.')
        buffer=ctypes.create_string_buffer(size)
        if enum(6,None,4,buffer,size,ctypes.byref(needed),ctypes.byref(count)):
            if count.value*ctypes.sizeof(PRINTER_INFO_4)>size:raise ValueError('Respuesta de impresoras inválida.')
            rows=ctypes.cast(buffer,ctypes.POINTER(PRINTER_INFO_4))
            names=[rows[i].pPrinterName for i in range(count.value) if rows[i].pPrinterName]
            return sorted(set(names),key=str.casefold)
        error=ctypes.get_last_error()
        if error!=122:raise ctypes.WinError(error)
    raise ValueError('La lista de impresoras cambió durante la consulta. Intenta nuevamente.')

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:print(json.dumps({'printers':enumerate_queues()},ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False));sys.exit(1)
