"""Dedicated UDP socket for the temporary host-only WebRTC diagnostic.

The regular media server is never patched. This overrides candidate gathering
only in the *separate* host-network diagnostic process (one active peer), so
Google Nest can forward a single known UDP port. aiortc/aioice do not expose
a public configuration for choosing the local ICE UDP port.
"""
import asyncio
import ipaddress
import logging
import os
import socket

from aioice import Connection
from aioice import ice as aioice_ice
from aioice.candidate import Candidate, candidate_foundation, candidate_priority
from aioice.ice import StunProtocol, server_reflexive_candidate

UDP_PORT = 3478
_INSTALLED = False
logger = logging.getLogger(__name__)


async def fixed_get_component_candidates(self, component, addresses, timeout=5):
    """Same aioice candidate semantics, but bind IPv4 host sockets to 3478."""
    if component != 1:
        raise RuntimeError("Only one diagnostic ICE component supported")
    candidates = []
    loop = asyncio.get_running_loop()
    protocols = []
    # This is deliberately IPv4-only: port-forwarding is an IPv4 NAT test.
    for address in dict.fromkeys(addresses):
        if ipaddress.ip_address(address).version != 4:
            continue
        try:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: StunProtocol(self), local_addr=(address, UDP_PORT))
        except OSError as error:
            logger.warning("Unable to bind diagnostic UDP %s on %s: %s",
                           UDP_PORT, address, type(error).__name__)
            continue
        sock = transport.get_extra_info("socket")
        if sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF,
                            aioice_ice.turn.UDP_SOCKET_BUFFER_SIZE)
        bound = transport.get_extra_info("sockname")
        protocol.local_candidate = Candidate(
            foundation=candidate_foundation("host", "udp", bound[0]),
            component=component, transport="udp",
            priority=candidate_priority(component, "host"),
            host=bound[0], port=bound[1], type="host")
        candidates.append(protocol.local_candidate)
        protocols.append(protocol)
    if not protocols:
        raise RuntimeError("Dedicated diagnostic UDP port 3478 not available")
    self._protocols += protocols

    if self.stun_server:
        tasks = [asyncio.create_task(
            server_reflexive_candidate(protocol, self.stun_server))
            for protocol in protocols]
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in done:
            if task.cancelled() or task.exception() is not None:
                continue
            candidate, _ = task.result()
            # Explicit inbound NAT mapping is public UDP 3478 -> host UDP 3478.
            # STUN discovers the public IP; the mapping's external port is
            # configured in Google Nest instead of using a transient STUN port.
            candidate.port = UDP_PORT
            candidates.append(candidate)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    return candidates


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    if os.environ.get("YARR_ICE_PROBE_MODE") != "host":
        return
    Connection.get_component_candidates = fixed_get_component_candidates
    _INSTALLED = True
