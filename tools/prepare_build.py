"""Download official build dependencies into an isolated, disposable directory."""
import concurrent.futures
import pathlib
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / '.build'
CACHE.mkdir(exist_ok=True)

def download(url, name):
    target = CACHE / name
    if not target.exists():
        print('Descargando', name, flush=True)
        urllib.request.urlretrieve(url, target)
    return target

def unpack(url, name, dest):
    target = CACHE / dest
    if not target.exists():
        archive = download(url, name)
        target.mkdir()
        with zipfile.ZipFile(archive) as z:
            z.extractall(target)
    return target

def android():
    data = urllib.request.urlopen('https://dl.google.com/android/repository/repository2-1.xml').read()
    root = ET.fromstring(data)
    for path, dest in [('build-tools;35.0.0', 'android-tools'), ('platforms;android-35', 'android-platform')]:
        pkg = next(p for p in root if p.tag.endswith('remotePackage') and p.get('path') == path)
        archives = pkg.find('archives')
        archive = next(a for a in archives if a.findtext('host-os') in ('windows', None))
        name = archive.findtext('complete/url')
        unpack('https://dl.google.com/android/repository/' + name, name, dest)

def runtime():
    unpack('https://www.python.org/ftp/python/3.13.9/python-3.13.9-embed-amd64.zip', 'python.zip', 'python')
    unpack('https://files.sumatrapdfreader.org/software/sumatrapdf/rel/3.6.1/SumatraPDF-3.6.1-64.zip', 'sumatra-direct.zip', 'sumatra')
    urllib.request.urlretrieve('https://raw.githubusercontent.com/sumatrapdfreader/sumatrapdf/3.6.1rel/COPYING', CACHE / 'sumatra' / 'COPYING')
    download('https://bootstrap.pypa.io/get-pip.py', 'get-pip.py')

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor() as pool:
        results = [pool.submit(android), pool.submit(runtime)]
        for result in results:
            result.result()
    print('Dependencias descargadas.', flush=True)
