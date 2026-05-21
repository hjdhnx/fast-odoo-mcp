"""Tests for managed Odoo connection lifecycle."""

from unittest.mock import Mock, patch

import pytest

from fast_odoo_mcp.config import OdooConfig
from fast_odoo_mcp.connection_manager import ConnectionManager
from fast_odoo_mcp.odoo_connection import OdooConnectionError


@pytest.fixture
def config():
    return OdooConfig(url="http://localhost:8069", api_key="test-key", database="test_db")


def test_ensure_connected_reuses_ready_connection(config):
    manager = ConnectionManager(config)
    connection = Mock()
    connection.is_connected = True
    connection.is_authenticated = True
    access_controller = Mock()
    manager.connection = connection
    manager.access_controller = access_controller

    first = manager.ensure_connected()
    second = manager.ensure_connected()

    assert first == (connection, access_controller)
    assert second == (connection, access_controller)


def test_call_with_retry_reconnects_once(config):
    manager = ConnectionManager(config)
    operation = Mock(side_effect=[OdooConnectionError("lost"), "ok"])

    with patch.object(manager, "reconnect", return_value=(Mock(), Mock())) as reconnect:
        result = manager.call_with_retry("test_operation", operation)

    assert result == "ok"
    reconnect.assert_called_once()
    assert manager.retry_count == 1
    assert manager.operation_count == 1
    assert manager.last_error == "lost"


def test_close_disconnects_and_clears_pool(config):
    manager = ConnectionManager(config)
    connection = Mock()
    performance_manager = Mock()
    manager.connection = connection
    manager.access_controller = Mock()
    manager.performance_manager = performance_manager

    manager.close()

    connection.disconnect.assert_called_once()
    performance_manager.connection_pool.clear.assert_called_once()
    performance_manager.clear_all_caches.assert_called_once()
    assert manager.connection is None
    assert manager.access_controller is None
    assert manager.performance_manager is None
