import os
import time

from _adblock import AdBlock
from concurrent.futures import ThreadPoolExecutor
import urllib.request


EASYLIST = (
    "https://easylist.to/easylist/easylist.txt",
    "https://easylist.to/easylist/easyprivacy.txt",
    "https://easylist.to/easylist/fanboy-annoyance.txt"
)


class Adblocker(object):
    def __init__(self, cache_path):
        if not os.path.isdir(cache_path):
            os.makedirs(cache_path)
        self._cache_path = cache_path
        self._urls = {}

    def register_filter_url(self, url, destfile=None):
        if destfile is None:
            destfile = url.rsplit("/", 1)[-1]
        self._urls[url] = os.path.join(self._cache_path, destfile)

    def _download_file(self, url, path):
        headers = {'User-Agent': "Magic Browser"}
        req = urllib.request.Request(url, None, headers)
        with urllib.request.urlopen(req, timeout=5) as conn:
            with open(path, "w") as f:
                data = conn.read()
                f.write(data.decode("utf-8"))

    def _fetch_urls(self):
        to_download = [(url, path) for url, path in self._urls.items()
                       if not os.path.isfile(path)
                       or os.path.getmtime(path) > (time.time() + 3600)]
        if to_download:
            with ThreadPoolExecutor(max_workers=5) as executor:
                for url, path in to_download:
                    executor.submit(self._download_file, url, path)

    def generate_rules(self):
        adblock = AdBlock()
        self._fetch_urls()
        rules = []
        for path in self._urls.values():
            with open(path) as f:
                adblock.parse(f.read())
            print (path)
        return adblock