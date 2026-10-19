import json
import time
import types
import unittest
from unittest.mock import Mock, patch
from modules.bambu import Module


class PrinterCommandTests(unittest.TestCase):
    def module(self, control=False):
        m = Module({'id': 'printer', 'serial': 'TEST', 'control_enabled': control})
        m.connected = True
        m.last_msg = time.time()
        m.report = {'gcode_state': 'RUNNING'}
        m.client = Mock()
        return m

    def test_default_monitor_never_publishes_control(self):
        m = self.module()
        for command in ('pause', 'resume', 'stop', 'skip_objects'):
            with self.assertRaisesRegex(RuntimeError, '僅接收狀態'):
                m.action(command)
        m.client.publish.assert_not_called()

    def test_connect_is_subscribe_only(self):
        client = Mock()
        mqtt = types.ModuleType('paho.mqtt.client')
        mqtt.Client = Mock(return_value=client)
        mqtt.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
        parent = types.ModuleType('paho')
        package = types.ModuleType('paho.mqtt')
        parent.mqtt, package.client = package, mqtt
        with patch.dict('sys.modules', {'paho': parent, 'paho.mqtt': package, 'paho.mqtt.client': mqtt}):
            m = Module({'ip': '127.0.0.1', 'serial': 'TEST', 'access_code': 'test'})
            m.start()
            client.on_connect(client, None, None, 0)
        client.subscribe.assert_called_once_with('device/TEST/report')
        client.publish.assert_not_called()

    def test_err_code_without_result_latches_control_off(self):
        m = self.module(True)
        m.pending_command = ('123', 'pause')
        m._handle_payload({'print': {'sequence_id': 0, 'command': 'pause', 'err_code': 84033543}})
        self.assertTrue(m.control_blocked)
        self.assertEqual(m.command_replies['123']['err_code'], 84033543)
        self.assertEqual(m.report['gcode_state'], 'RUNNING')
        self.assertEqual(m.poll()['command_error']['err_code'], 84033543)
        with self.assertRaises(RuntimeError):
            m.action('pause')
        m.client.publish.assert_not_called()

    def test_state_is_not_replaced_by_ack(self):
        m = self.module()
        m._handle_payload({'print': {'command': 'pause', 'gcode_state': 'PAUSE', 'result': 'fail'}})
        self.assertEqual(m.report['gcode_state'], 'RUNNING')
        m._handle_payload({'print': {'command': 'push_status', 'gcode_state': 'PAUSE', 'print_error': 12, 'hms': [{'code': 7}]}})
        data = m.poll()
        self.assertEqual(data['stage'], 'PAUSE')
        self.assertEqual(data['print_error'], 12)
        self.assertEqual(data['hms'], [{'code': 7}])

    def test_error_beats_success_state_and_no_retry(self):
        m = self.module(True)
        def publish(topic, raw, **kwargs):
            data = json.loads(raw)['print']
            self.assertEqual(data['param'], '')
            m._handle_payload({'print': {'command': data['command'], 'sequence_id': data['sequence_id'], 'err_code': 84033543}})
            m.report['gcode_state'] = 'PAUSE'
            return Mock(is_published=lambda: True)
        m.client.publish.side_effect = publish
        with patch('modules.bambu.time.sleep'), self.assertRaisesRegex(RuntimeError, '84033543'):
            m.action('pause')
        self.assertEqual(m.client.publish.call_count, 1)
        self.assertIsNone(m.pending_command)

    def test_unrelated_rejection_is_not_an_ack(self):
        m = self.module(True)
        m.pending_command = ('123', 'pause')
        m._handle_payload({'print': {'command': 'resume', 'sequence_id': '999', 'err_code': 42}})
        self.assertEqual(m.command_replies, {})
        self.assertFalse(m.control_blocked)

    def test_diagnostic_history_is_bounded(self):
        m = self.module()
        for _ in range(50):
            m._handle_payload({'print': {'command': 'pause', 'err_code': 42, 'access_code': 'never expose'}})
        self.assertEqual(len(m.diagnostics), 30)
        self.assertNotIn('access_code', json.dumps(list(m.diagnostics)))


if __name__ == '__main__':
    unittest.main()
