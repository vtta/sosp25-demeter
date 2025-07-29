import logging
from collections import namedtuple
from http import HTTPStatus

import httpx

LOGGER = logging.getLogger(__name__)


class Resource:
    """An abstraction over a REST path"""

    def __init__(self, api, resource, id_field=None):
        self._api = api
        self.resource = resource
        self.id_field = id_field

    def get(self):
        """Make a GET request"""
        url = self._api.endpoint + self.resource
        res = self._api.session.get(url)
        if res.status_code != HTTPStatus.OK:
            raise RuntimeError(res.text)
        return res

    def request(self, method, path, **kwargs):
        """Make an HTTP request"""
        kwargs = {key: val for key, val in kwargs.items() if val is not None}
        url = self._api.endpoint + path
        res = self._api.session.request(method, url, json=kwargs)
        if res.status_code != HTTPStatus.NO_CONTENT:
            raise RuntimeError(res.text)
        return res

    def put(self, **kwargs):
        """Make a PUT request"""
        LOGGER.debug(f"PUT {self.resource} {kwargs}")
        path = self.resource
        if self.id_field is not None:
            path += "/" + kwargs[self.id_field]
        return self.request("PUT", path, **kwargs)

    def patch(self, **kwargs):
        """Make a PATCH request"""
        path = self.resource
        if self.id_field is not None:
            path += "/" + kwargs[self.id_field]
        return self.request("PATCH", path, **kwargs)


class Api:
    """A simple HTTP client for the cloud-hypervisor API"""

    def __init__(self, api_usocket_path):
        self.socket = api_usocket_path
        self.endpoint = "http://localhost/api/v1"
        self.session = httpx.Client(transport=httpx.HTTPTransport(uds=str(api_usocket_path)), timeout=120)

        vmm = dict(
            ping=Resource(self, "/vmm.ping"),
            shutdown=Resource(self, "/vmm.shutdown"),
        )
        self.vmm = namedtuple("VmmApi", vmm.keys())(*vmm.values())
        vm = dict(
            add_device=Resource(self, "/vm.add-device"),
            add_disk=Resource(self, "/vm.add-disk"),
            add_fs=Resource(self, "/vm.add-fs"),
            add_net=Resource(self, "/vm.add-net"),
            add_pmem=Resource(self, "/vm.add-pmem"),
            add_vdpa=Resource(self, "/vm.add-vdpa"),
            add_sock=Resource(self, "/vm.add-vsock"),
            boot=Resource(self, "/vm.boot"),
            coredump=Resource(self, "/vm.coredump"),
            counters=Resource(self, "/vm.counters"),
            create=Resource(self, "/vm.create"),
            delete=Resource(self, "/vm.delete"),
            info=Resource(self, "/vm.info"),
            pause=Resource(self, "/vm.pause"),
            power_button=Resource(self, "/vm.power-button"),
            reboot=Resource(self, "/vm.reboot"),
            receive_migration=Resource(self, "/vm.receive-migration"),
            remove_device=Resource(self, "/vm.remove-device"),
            resize=Resource(self, "/vm.resize"),
            resize_zone=Resource(self, "/vm.resize-zone"),
            restore=Resource(self, "/vm.restore"),
            resume=Resource(self, "/vm.resume"),
            send_migration=Resource(self, "/vm.send-migration"),
            shutdown=Resource(self, "/vm.shutdown"),
            snapshot=Resource(self, "/vm.snapshot"),
        )
        self.vm = namedtuple("VmApi", vm.keys())(*vm.values())
